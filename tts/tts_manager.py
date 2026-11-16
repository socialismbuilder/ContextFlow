# -*- coding: utf-8 -*-

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from collections import deque

from ..config_manager import get_config
from .. import loop_utils

# Edge TTS 的常驻事件循环：所有 edge-tts 生成共用同一个后台 loop 线程，
# 不再每句话 new_event_loop + 新线程 + 新建环。
# 背景：Windows 上频繁创建 ProactorEventLoop 一旦 socketpair 失败，
# 会留下半成品 loop，在 Anki 退出时炸出
# "'ProactorEventLoop' object has no attribute '_ssock'"（见 loop_utils 注释）。
_tts_loop = None  # asyncio.AbstractEventLoop | None
_tts_loop_lock = threading.Lock()


def _get_tts_loop():
    """获取（或首次创建）常驻 TTS 事件循环；创建失败返回 None。

    线程安全：多路请求（预取线程 + Web 端并发）可能同时进来。
    """
    global _tts_loop
    with _tts_loop_lock:
        loop = _tts_loop
        if loop is not None and not loop.is_closed():
            return loop
        loop = loop_utils.safe_new_loop("ContextFlow TTS")
        if loop is None:
            _tts_loop = None
            return None
        threading.Thread(
            target=_run_tts_loop, args=(loop,), name="ContextFlowTTSLoop", daemon=True
        ).start()
        _tts_loop = loop
        return loop


def _run_tts_loop(loop):
    """常驻 TTS 事件循环线程的主体：一直 run_forever，退出时收尾关闭。"""
    import asyncio

    asyncio.set_event_loop(loop)
    try:
        loop.run_forever()
    except Exception as e:
        print(f"[ContextFlow TTS] 警告: TTS 事件循环异常退出: {e}")
    finally:
        loop_utils.close_loop(loop, "ContextFlow TTS")


def shutdown_tts_loop() -> None:
    """停止常驻 TTS 事件循环线程（profile 关闭时调用；之后可按需重建）。"""
    global _tts_loop
    with _tts_loop_lock:
        loop = _tts_loop
        _tts_loop = None
    if loop is None or loop.is_closed():
        return
    if loop.is_running():
        loop_utils.stop_loop_threadsafe(loop, "ContextFlow TTS")
    # run_forever 退出后的 shutdown_asyncgens/close 由 _run_tts_loop 的
    # finally 负责，这里不 join：给线程一点收尾时间即可（daemon 线程，
    # 就算没跑完，Anki 退出时 loop 也已被正确 closed，不会留下半成品）。
    threading.Event().wait(0.2)

# Language name -> edge-tts voice mapping
TTS_VOICE_MAP = {
    "英语": "en-US-EmmaMultilingualNeural",
    "日语": "ja-JP-NanamiNeural",
    "韩语": "ko-KR-SunHiNeural",
    "法语": "fr-FR-DeniseNeural",
    "德语": "de-DE-KatjaNeural",
    "西班牙语": "es-ES-ElviraNeural",
    "意大利语": "it-IT-ElsaNeural",
    "葡萄牙语": "pt-BR-FranciscaNeural",
    "俄语": "ru-RU-SvetlanaNeural",
    "阿拉伯语": "ar-SA-HamedNeural",
    "中文": "zh-CN-XiaoxiaoNeural",
    "泰语": "th-TH-PremwadeeNeural",
    "越南语": "vi-VN-HoaiMyNeural",
    "荷兰语": "nl-NL-ColetteNeural",
    "波兰语": "pl-PL-AgnieszkaNeural",
    "土耳其语": "tr-TR-AhmetNeural",
}

# Language name -> Anki TTS language code
ANKI_LANG_MAP = {
    "英语": "en_US",
    "日语": "ja_JP",
    "韩语": "ko_KR",
    "法语": "fr_FR",
    "德语": "de_DE",
    "西班牙语": "es_ES",
    "中文": "zh_CN",
}

# Language name -> preferred macOS say locale candidates
APPLE_LANG_MAP = {
    "英语": ("en_US", "en_GB", "en_AU", "en_"),
    "日语": ("ja_JP", "ja_"),
    "韩语": ("ko_KR", "ko_"),
    "法语": ("fr_FR", "fr_CA", "fr_"),
    "德语": ("de_DE", "de_"),
    "西班牙语": ("es_ES", "es_MX", "es_"),
    "意大利语": ("it_IT", "it_"),
    "葡萄牙语": ("pt_BR", "pt_PT", "pt_"),
    "俄语": ("ru_RU", "ru_"),
    "阿拉伯语": ("ar_001", "ar_XA", "ar_"),
    "中文": ("zh_CN", "zh_HK", "zh_TW", "zh_"),
    "泰语": ("th_TH", "th_"),
    "越南语": ("vi_VN", "vi_"),
    "荷兰语": ("nl_NL", "nl_BE", "nl_"),
    "波兰语": ("pl_PL", "pl_"),
    "土耳其语": ("tr_TR", "tr_"),
    "印地语": ("hi_IN", "hi_"),
}

# Language name -> macOS Spoken Content preference language keys
APPLE_SYSTEM_LANG_MAP = {
    "英语": ("en",),
    "日语": ("ja",),
    "韩语": ("ko",),
    "法语": ("fr",),
    "德语": ("de",),
    "西班牙语": ("es",),
    "意大利语": ("it",),
    "葡萄牙语": ("pt",),
    "俄语": ("ru",),
    "阿拉伯语": ("ar",),
    "中文": ("cmn", "zh"),
    "泰语": ("th",),
    "越南语": ("vi",),
    "荷兰语": ("nl",),
    "波兰语": ("pl",),
    "土耳其语": ("tr",),
    "印地语": ("hi",),
}

# Language name -> Edge TTS locale prefix for voice filtering
LANG_TO_LOCALE_PREFIX = {
    "英语": ("en",),
    "日语": ("ja",),
    "韩语": ("ko",),
    "法语": ("fr",),
    "德语": ("de",),
    "西班牙语": ("es",),
    "意大利语": ("it",),
    "葡萄牙语": ("pt",),
    "俄语": ("ru",),
    "阿拉伯语": ("ar",),
    "中文": ("zh",),
    "泰语": ("th",),
    "越南语": ("vi",),
    "荷兰语": ("nl",),
    "波兰语": ("pl",),
    "土耳其语": ("tr",),
    "印地语": ("hi",),
}

# Module-level cache for the Edge TTS voice list (fetched once per session)
_cached_voice_list: list[dict] = []
_voice_list_lock = threading.Lock()
_voice_list_event = threading.Event()  # set() once the voice list has been fetched


def _fetch_voice_list() -> list[dict]:
    """Fetch the full Edge TTS voice list from Microsoft's API synchronously.
    Must be called from a background thread (creates its own event loop,
    一次性任务，用完即关；loop 创建失败时走 safe_new_loop 的兜底日志)."""
    import asyncio
    import edge_tts
    loop = loop_utils.safe_new_loop("ContextFlow TTS")
    if loop is None:
        return []
    try:
        try:
            voices = loop.run_until_complete(
                asyncio.wait_for(edge_tts.list_voices(), timeout=20)
            )
            return voices
        finally:
            loop_utils.close_loop(loop, "ContextFlow TTS")
    except asyncio.TimeoutError:
        print("WARNING: Fetching Edge TTS voice list timed out")
        return []
    except Exception as e:
        print(f"WARNING: Failed to fetch Edge TTS voice list: {e}")
        return []


def get_voices_for_language(language: str) -> list[dict]:
    """Return Edge TTS voices matching the given language name (e.g. '英语').
    Filters by locale prefix, excludes Deprecated voices.
    Falls back to a single-item list from TTS_VOICE_MAP if no cache available."""
    with _voice_list_lock:
        voices = list(_cached_voice_list)

    prefixes = LANG_TO_LOCALE_PREFIX.get(language, ())
    if not prefixes or not voices:
        default_short = TTS_VOICE_MAP.get(language)
        if default_short:
            return [{"ShortName": default_short, "FriendlyName": default_short, "Locale": "", "Status": "GA"}]
        return []

    filtered = [
        v for v in voices
        if any(v["Locale"].startswith(p) for p in prefixes)
        and v.get("Status") != "Deprecated"
    ]
    filtered.sort(key=lambda v: (0 if v.get("Status") == "GA" else 1, v["ShortName"]))
    return filtered


def ensure_voice_list_loaded():
    """If the voice list hasn't been fetched yet, kick off a background thread.
    Safe to call multiple times."""
    if _voice_list_event.is_set():
        return

    def _load():
        result = _fetch_voice_list()
        with _voice_list_lock:
            _cached_voice_list.clear()
            _cached_voice_list.extend(result)
        _voice_list_event.set()

    threading.Thread(target=_load, daemon=True).start()


def _get_voice_for_language(language: str) -> str:
    config = get_config()
    override = config.get(f"edge_tts_voice_{language}", "")
    if override:
        return override
    return TTS_VOICE_MAP.get(language, "en-US-EmmaMultilingualNeural")


def _get_anki_lang(language: str) -> str:
    return ANKI_LANG_MAP.get(language, "en_US")


def _get_apple_lang_candidates(language: str) -> tuple[str, ...]:
    return APPLE_LANG_MAP.get(language, ("en_US", "en_GB", "en_"))


def _get_apple_system_lang_candidates(language: str) -> tuple[str, ...]:
    return APPLE_SYSTEM_LANG_MAP.get(language, ())


def _get_short_apple_voice_name(voice_name: str) -> str:
    return voice_name.split(" (", 1)[0].strip()


def _normalize_apple_locale(locale: str | None) -> str | None:
    return locale.replace("-", "_") if locale else None


def _clean_text_for_tts(text: str) -> str:
    """Remove HTML tags and clean text for TTS, ensuring it starts from the first word."""
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    # 剥离句首的序号、前导标点、引号、破折号、星号等，确保从第一个真正的单词字符开始读
    text = re.sub(r'^[^\w\s"\'“”‘’]+', '', text).strip()
    text = re.sub(r'^["\'“”‘’`]+', '', text).strip()
    return text


# MP3 (Layer III) 静音帧构造所需表：码率 index 0/15 无效，采样率 index 0b11 无效
_MPEG_L3_BITRATES_V1 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]
_MPEG_L3_BITRATES_LSF = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]
_MPEG_L3_SAMPLE_RATES = {
    0b00: (11025, 12000, 8000),   # MPEG-2.5
    0b10: (22050, 24000, 16000),  # MPEG-2
    0b11: (44100, 48000, 32000),  # MPEG-1
}


def _parse_mp3_frame_header(data: bytes, pos: int):
    """解析 pos 处 4 字节的 MP3 (Layer III) 帧头。

    返回 (帧长[不含padding], 每帧采样数, 每帧时长ms)，非法则返回 None。
    padding 位按 0 计算（构造静音帧时会清掉该位）；Layer I/II 不支持。
    """
    if pos < 0 or pos + 4 > len(data):
        return None
    if data[pos] != 0xFF or (data[pos + 1] & 0xE0) != 0xE0:
        return None
    version = (data[pos + 1] >> 3) & 0x03   # 0b01 为保留值
    layer = (data[pos + 1] >> 1) & 0x03     # 0b01 为 Layer III
    if version == 0b01 or layer != 0b01:
        return None
    bitrate_idx = data[pos + 2] >> 4
    sample_idx = (data[pos + 2] >> 2) & 0x03
    if bitrate_idx in (0, 15) or sample_idx == 0b11:
        return None
    if version == 0b11:
        base, samples_per_frame = 144, 1152
        bitrate = _MPEG_L3_BITRATES_V1[bitrate_idx]
    else:
        base, samples_per_frame = 72, 576
        bitrate = _MPEG_L3_BITRATES_LSF[bitrate_idx]
    sample_rate = _MPEG_L3_SAMPLE_RATES[version][sample_idx]
    length = base * bitrate * 1000 // sample_rate
    if length <= 4:
        return None
    return length, samples_per_frame, samples_per_frame * 1000.0 / sample_rate


def _add_mp3_leading_silence(audio_data: bytes, ms: int = 240) -> bytes:
    """Prepend silent MP3 frames to audio to prevent initial audio clipping by hardware audio devices.

    静音帧头部参数直接复制真实首帧（清掉 padding/CRC 位后按帧长公式填零载荷），
    与原流的版本/码率/采样率/声道严格一致，不改动原音频任何字节；
    找不到合法 MP3 帧头时原样返回。10 帧左右（约 240ms）静音
    足够提前唤醒声卡 DAC 与蓝牙耳机。
    """
    if not audio_data or len(audio_data) < 4:
        return audio_data

    start = 0
    if audio_data[:3] == b"ID3":
        # ID3v2 标签：读 synchsafe 大小并跳过（底部标志位 bit4 为 1 时末尾还有 10 字节 footer）
        if len(audio_data) < 10:
            return audio_data
        tag_size = (
            ((audio_data[6] & 0x7F) << 21)
            | ((audio_data[7] & 0x7F) << 14)
            | ((audio_data[8] & 0x7F) << 7)
            | (audio_data[9] & 0x7F)
        )
        start = 10 + tag_size + (10 if audio_data[5] & 0x10 else 0)
        if start + 8 > len(audio_data):
            return audio_data

    # 找第一个合法帧头。帧头不在数据起点时，额外要求下一帧也是同参数的合法帧，
    # 避免把二进制噪声里的 0xFFEx 误认成同步字（比如标签后的杂散字节）。
    pos = start
    limit = min(len(audio_data) - 4, start + 4096)
    first = None
    while pos <= limit:
        candidate = _parse_mp3_frame_header(audio_data, pos)
        if candidate is not None:
            length = candidate[0]
            if pos == start:
                first = candidate
                break
            second = _parse_mp3_frame_header(audio_data, pos + length)
            if second is not None and second[0] == length and abs(second[2] - candidate[2]) < 0.01:
                first = candidate
                break
        pos += 1
    if first is None:
        return audio_data

    length, _samples, frame_ms = first
    hdr = bytearray(audio_data[pos:pos + 4])
    hdr[1] |= 0x01     # protection=1：静音帧不带 CRC 校验域
    hdr[2] &= 0xFD     # 清 padding 位，帧长与头部声明的参数严格一致
    silent_frame = bytes(hdr) + bytes(length - 4)
    num_frames = max(1, round(ms / frame_ms))
    return audio_data[:pos] + (silent_frame * num_frames) + audio_data[pos:]


def _play_bytes(audio_data: bytes, ext: str = ".mp3") -> str:
    """Write audio bytes to a temp file and play it. Must be called on main thread."""
    if ext.lower() == ".mp3":
        audio_data = _add_mp3_leading_silence(audio_data)

    fd, path = tempfile.mkstemp(suffix=ext)
    try:
        os.write(fd, audio_data)
    finally:
        os.close(fd)

    from aqt.sound import av_player
    av_player.play_file(path)
    return path


class TTSManager:
    def __init__(self):
        self._cache = {}  # cache_key -> (bytes, ext)
        self._apple_voices = None
        self._apple_spoken_content_defaults = None
        self._apple_spoken_content_defaults_mtime = None
        self._apple_process = None

        # 读音预生成：单一后台线程串行消费的 FIFO 队列。
        # 刻意不用线程池——Edge TTS 并发一高就会被微软服务端掐断，
        # 本地 TTS 多路并行显卡也扛不住，串行逐个生成最稳妥。
        # deque+Condition 而非 queue.Queue：需要 front 插队能力
        # （当前卡片马上会被点到的音频要排到待预取单词前面）。
        self._prefetch_deque: deque = deque()
        self._prefetch_cond = threading.Condition()
        self._prefetch_queued: set[str] = set()  # 已入队/生成中的 cache_key，防重复入队
        self._prefetch_lock = threading.Lock()
        self._prefetch_thread: threading.Thread | None = None

    def play_cached(self, text: str) -> str | None:
        """Check cache and play if hit. Returns file path on hit, None on miss."""
        config = get_config()
        engine = config.get("tts_engine", "edge_tts")
        if engine == "apple_tts":
            return None

        text = _clean_text_for_tts(text)
        if not text:
            return ""

        cache_key = f"{engine}:{text}"
        if cache_key in self._cache:
            audio_data, ext = self._cache[cache_key]
            return _play_bytes(audio_data, ext)
        return None

    def is_anki_native(self) -> bool:
        return get_config().get("tts_engine", "edge_tts") == "anki_native"

    def uses_direct_playback(self) -> bool:
        return get_config().get("tts_engine", "edge_tts") in {"anki_native", "apple_tts"}

    def play_direct(self, text: str):
        """Play directly without generating cached audio bytes."""
        config = get_config()
        engine = config.get("tts_engine", "edge_tts")
        text = _clean_text_for_tts(text)
        if not text:
            return

        if engine == "anki_native":
            self._play_anki_native(text)
        elif engine == "apple_tts":
            self._play_apple_tts(text)

    def generate(self, text: str) -> tuple[bytes, str] | None:
        """Generate audio in background thread. Returns (audio_bytes, ext) or None.

        先查内存缓存再生成：Web 端 /api/tts 的每次请求都直接走这里
        （桌面端点朗读前会先查 play_cached，Web 端没有这一步），
        不查缓存的话预生成的读音永远命中不了，每次都重新请求微软服务器。
        """
        config = get_config()
        engine = config.get("tts_engine", "edge_tts")
        text = _clean_text_for_tts(text)
        if not text:
            return None

        cache_key = f"{engine}:{text}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            if engine == "edge_tts":
                return self._generate_edge_tts(text, cache_key)
            elif engine == "custom_url":
                return self._generate_custom(text, cache_key)
        except Exception as e:
            print(f"ERROR: TTS generation failed ({engine}): {e}")
        return None

    # --- 读音预生成（prefetch）---

    def prefetch(self, text: str, front: bool = False) -> None:
        """把文本加入读音预生成队列，由唯一的后台线程串行生成进缓存。

        front=True 时插到队列最前：给"用户马上就可能点到的音频"用
        （如当前卡片的单词和例句），不让它排在成批待预取单词后面。
        复习是逐张卡片进行的，串行生成完全跟得上节奏；
        等真正点到"朗读"时音频已在缓存里，命中即播、零延迟。
        """
        if self.uses_direct_playback():
            return  # anki_native / apple_tts 直接播放，没有可预生成的音频缓存

        text = _clean_text_for_tts(text)
        if not text:
            return

        engine = get_config().get("tts_engine", "edge_tts")
        cache_key = f"{engine}:{text}"

        with self._prefetch_lock:
            if cache_key in self._cache or cache_key in self._prefetch_queued:
                return
            self._prefetch_queued.add(cache_key)
            self._ensure_prefetch_thread()
            # 入队也在锁内，保证任务按入队顺序进队列
            with self._prefetch_cond:
                if front:
                    self._prefetch_deque.appendleft((cache_key, text))
                else:
                    self._prefetch_deque.append((cache_key, text))
                self._prefetch_cond.notify()

    def prefetch_words(self, keywords) -> None:
        """批量预生成后续卡片单词的读音。

        与卡片模板的朗读按钮保持一致：先剔除括号内的释义注释
        （如 bank(银行) -> bank），保证预生成的 cache_key 与实际点击
        朗读时请求的 cache_key 完全相同。
        """
        for keyword in keywords or []:
            if not keyword:
                continue
            word = re.sub(r'[（(].*?[）)]', '', keyword).strip() or keyword
            self.prefetch(word)

    def _ensure_prefetch_thread(self) -> None:
        """确保预生成线程存活（只在 _prefetch_lock 内调用）。"""
        if self._prefetch_thread is not None and self._prefetch_thread.is_alive():
            return
        self._prefetch_thread = threading.Thread(
            target=self._prefetch_worker, name="TTSPrefetch", daemon=True
        )
        self._prefetch_thread.start()

    def _prefetch_worker(self) -> None:
        """串行消费预生成队列的唯一后台线程。"""
        while True:
            with self._prefetch_cond:
                while not self._prefetch_deque:
                    self._prefetch_cond.wait()
                item = self._prefetch_deque.popleft()

            if item is None:  # stop_prefetch 的退出哨兵
                with self._prefetch_lock:
                    self._prefetch_thread = None  # 允许之后重新启动
                break

            cache_key, text = item
            try:
                if cache_key not in self._cache:
                    print(f"DEBUG: TTS 预生成: {text}")
                    self.generate(text)
            except Exception as e:
                print(f"ERROR: TTS prefetch failed: {e}")
            finally:
                # 从"已入队"集合移除：生成失败时下次渲染会自动重试
                with self._prefetch_lock:
                    self._prefetch_queued.discard(cache_key)

        print("DEBUG: TTS prefetch thread stopped.")

    def stop_prefetch(self) -> None:
        """清空预生成队列并让后台线程退出（profile 关闭时调用）。"""
        with self._prefetch_lock:
            self._prefetch_queued.clear()
        with self._prefetch_cond:
            self._prefetch_deque.clear()
            self._prefetch_deque.append(None)  # 退出哨兵
            self._prefetch_cond.notify()

    def _generate_edge_tts(self, text: str, cache_key: str):
        """Generate audio with edge-tts. Returns (bytes, ext) or None.

        生成任务投递到常驻的 TTS 事件循环线程（_get_tts_loop），
        不再每句话 new_event_loop + 新线程。

        超时保护：内层 asyncio.wait_for(timeout) 负责取消挂起的
        WebSocket 任务，loop 本身继续存活，不会被一条无响应的请求拖死；
        外层 fut.result(timeout+5) 再兜一层底，保证调用方（预取线程 /
        Web 端 executor 线程）一定能在时限内返回。
        """
        import asyncio
        import concurrent.futures
        import edge_tts

        config = get_config()
        language = config.get("learning_language", "英语")
        voice = _get_voice_for_language(language)

        # edge-tts 单次生成的总超时（秒）。正常一句话几秒即可完成。
        timeout = 30

        loop = _get_tts_loop()
        if loop is None:
            return None

        async def _collect():
            communicate = edge_tts.Communicate(text, voice)
            chunks = bytearray()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    chunks.extend(chunk["data"])
            return bytes(chunks)

        async def _collect_with_timeout():
            return await asyncio.wait_for(_collect(), timeout=timeout)

        fut = asyncio.run_coroutine_threadsafe(_collect_with_timeout(), loop)
        audio = None
        try:
            audio = fut.result(timeout=timeout + 5)
        except concurrent.futures.TimeoutError:
            # Python 3.11+ 里 concurrent.futures.TimeoutError 与内建
            # TimeoutError 同源，wait_for 的超时也会走到这里
            print(f"WARNING: edge-tts 生成超时 ({timeout}s)，已取消")
            fut.cancel()
        except Exception as e:
            print(f"WARNING: edge-tts 生成失败: {e}")

        if not audio:
            return None

        self._cache[cache_key] = (audio, ".mp3")
        return (audio, ".mp3")

    def _play_anki_native(self, text: str):
        from anki.sound import TTSTag

        config = get_config()
        language = config.get("learning_language", "英语")
        lang = _get_anki_lang(language)

        tag = TTSTag(
            field_text=text,
            lang=lang,
            voices=[],
            speed=1.0,
            other_args={},
        )

        from aqt.sound import av_player
        for player in av_player.players:
            rank = player.rank_for_tag(tag)
            if rank is not None:
                player.play(tag, on_done=lambda: None)
                return

        print("WARNING: No Anki TTS player available for this language")

    def _get_available_apple_voices(self) -> list[tuple[str, str]]:
        if self._apple_voices is not None:
            return self._apple_voices

        say_path = shutil.which("say")
        if not say_path:
            self._apple_voices = []
            return self._apple_voices

        try:
            result = subprocess.run(
                [say_path, "-v", "?"],
                capture_output=True,
                text=True,
                check=True,
            )
        except Exception as e:
            print(f"WARNING: Failed to inspect Apple TTS voices: {e}")
            self._apple_voices = []
            return self._apple_voices

        voices = []
        for line in result.stdout.splitlines():
            match = re.match(r"^(?P<voice>.+?)\s{2,}(?P<locale>[A-Za-z_]+)\s+#", line)
            if match:
                voices.append((match.group("voice").strip(), match.group("locale").strip()))

        self._apple_voices = voices
        return self._apple_voices

    def _load_apple_spoken_content_defaults(self) -> dict[str, dict]:
        if sys.platform != "darwin":
            return {}

        prefs_path = os.path.expanduser("~/Library/Preferences/com.apple.Accessibility.plist")
        if not os.path.exists(prefs_path):
            self._apple_spoken_content_defaults = {}
            self._apple_spoken_content_defaults_mtime = None
            return self._apple_spoken_content_defaults

        try:
            prefs_mtime = os.path.getmtime(prefs_path)
        except OSError:
            prefs_mtime = None

        if (
            self._apple_spoken_content_defaults is not None
            and self._apple_spoken_content_defaults_mtime == prefs_mtime
        ):
            return self._apple_spoken_content_defaults

        self._apple_spoken_content_defaults = {}

        try:
            result = subprocess.run(
                ["plutil", "-convert", "json", "-o", "-", prefs_path],
                capture_output=True,
                text=True,
                check=True,
            )
            prefs = json.loads(result.stdout)
        except Exception as e:
            print(f"WARNING: Failed to read macOS Spoken Content defaults: {e}")
            return self._apple_spoken_content_defaults

        raw_selections = prefs.get("SpokenContentDefaultVoiceSelectionsByLanguage", [])
        if not isinstance(raw_selections, list):
            return self._apple_spoken_content_defaults

        selections = {}
        for index in range(0, len(raw_selections) - 1, 2):
            lang_key = raw_selections[index]
            selection = raw_selections[index + 1]
            if isinstance(lang_key, str) and isinstance(selection, dict):
                selections[lang_key] = selection

        self._apple_spoken_content_defaults = selections
        self._apple_spoken_content_defaults_mtime = prefs_mtime
        return self._apple_spoken_content_defaults

    def _resolve_listed_apple_voice_name(self, voice_name: str, locale_hint: str | None = None) -> str | None:
        if not voice_name:
            return None

        voices = self._get_available_apple_voices()
        normalized_locale = _normalize_apple_locale(locale_hint)
        short_name = voice_name.lower()
        matches = [
            (display_name, locale)
            for display_name, locale in voices
            if _get_short_apple_voice_name(display_name).lower() == short_name
        ]

        if normalized_locale:
            for display_name, locale in matches:
                if locale == normalized_locale:
                    return display_name

            locale_prefix = normalized_locale.split("_", 1)[0]
            for display_name, locale in matches:
                if locale.startswith(locale_prefix):
                    return display_name

        if matches:
            return matches[0][0]
        return None

    def _infer_listed_apple_voice_name(self, locale_hint: str | None, tier: str | None) -> str | None:
        normalized_locale = _normalize_apple_locale(locale_hint)
        if not normalized_locale:
            return None

        voices = self._get_available_apple_voices()
        exact_locale_matches = [(display_name, locale) for display_name, locale in voices if locale == normalized_locale]
        if not exact_locale_matches:
            locale_prefix = normalized_locale.split("_", 1)[0]
            exact_locale_matches = [
                (display_name, locale)
                for display_name, locale in voices
                if locale.startswith(locale_prefix)
            ]

        if not tier:
            if len(exact_locale_matches) == 1:
                return exact_locale_matches[0][0]
            return None

        tier_label = f"({tier.capitalize()})"
        tier_matches = [
            display_name
            for display_name, _locale in exact_locale_matches
            if display_name.endswith(tier_label)
        ]
        if len(tier_matches) == 1:
            return tier_matches[0]
        return None

    def _get_apple_voice_from_system_defaults(self, language: str) -> str | None:
        selections = self._load_apple_spoken_content_defaults()
        if not selections:
            return None

        for candidate in _get_apple_system_lang_candidates(language):
            selection = selections.get(candidate)
            if not selection:
                continue

            voice_id = selection.get("voiceId", "")
            if not voice_id:
                continue

            match = re.search(
                r"^com\.apple\.(?P<family>voice|eloquence)"
                r"(?:\.(?P<tier>premium|enhanced))?"
                r"\.(?P<locale>[A-Za-z]{2,3}(?:-[A-Za-z0-9]+)*)"
                r"\.(?P<voice>[^.]+)$",
                voice_id,
            )
            if match:
                resolved = self._resolve_listed_apple_voice_name(
                    match.group("voice"),
                    match.group("locale"),
                )
                if resolved:
                    return resolved

                inferred = self._infer_listed_apple_voice_name(
                    match.group("locale"),
                    match.group("tier"),
                )
                if inferred:
                    return inferred

                return match.group("voice")

            resolved = self._resolve_listed_apple_voice_name(voice_id.rsplit(".", 1)[-1])
            return resolved or voice_id.rsplit(".", 1)[-1]

        return None

    def _get_apple_voice_for_language(self, language: str) -> str | None:
        system_voice = self._get_apple_voice_from_system_defaults(language)
        if system_voice:
            return system_voice

        voices = self._get_available_apple_voices()

        for candidate in _get_apple_lang_candidates(language):
            for voice, locale in voices:
                if locale == candidate or locale.startswith(candidate):
                    return voice

        return None

    def _stop_apple_tts(self):
        if not self._apple_process:
            return

        try:
            if self._apple_process.poll() is None:
                self._apple_process.terminate()
        except Exception:
            pass
        finally:
            self._apple_process = None

    def _play_apple_tts(self, text: str):
        if sys.platform != "darwin":
            print("WARNING: Apple TTS is only available on macOS")
            return

        say_path = shutil.which("say")
        if not say_path:
            print("WARNING: Apple TTS requires the macOS 'say' command")
            return

        config = get_config()
        language = config.get("learning_language", "英语")
        voice = self._get_apple_voice_for_language(language)

        cmd = [say_path]
        if voice:
            cmd.extend(["-v", voice])
        cmd.append(text)

        # Follow macOS Spoken Content language settings when available, then locale fallback.
        self._stop_apple_tts()
        self._apple_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _generate_custom(self, text: str, cache_key: str):
        """Generate audio from a user-supplied URL template (GET with placeholders).

        用户在配置里填一个带占位符的 URL 模板，朗读时把实际值替换进去再发 GET：
          {text}     -> 要朗读的文本（URL 编码）
          {voice}    -> 人声名（与 Edge TTS 共用 TTS_VOICE_MAP 映射）
          {language} -> 学习语言（如「英语」）

        若 URL 不含任何占位符，则在末尾追加 ?text=<文本>（或 &text=），
        兼容只接受一个 text 参数、speaker 固定的简单接口。
        """
        import requests
        from urllib.parse import quote

        config = get_config()
        template = config.get("tts_custom_url", "")
        if not template:
            print("ERROR: Custom TTS URL not configured")
            return None

        language = config.get("learning_language", "英语")
        voice = _get_voice_for_language(language)

        # 替换占位符；先编码再替换，避免占位符本身被编码
        encoded_text = quote(text)
        url = template.replace("{text}", encoded_text)
        url = url.replace("{voice}", quote(voice))
        url = url.replace("{language}", quote(language))

        # 不含占位符：自动追加 text 参数
        if url == template:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}text={encoded_text}"

        resp = requests.get(url, timeout=30)
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        ext = ".mp3" if "mpeg" in content_type else ".wav"
        audio_data = resp.content

        self._cache[cache_key] = (audio_data, ext)
        return (audio_data, ext)


# Singleton instance
tts_manager = TTSManager()
