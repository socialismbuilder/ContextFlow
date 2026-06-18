# -*- coding: utf-8 -*-

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading

from ..config_manager import get_config

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
    Must be called from a background thread (creates its own event loop)."""
    import asyncio
    import edge_tts
    loop = None
    try:
        loop = asyncio.new_event_loop()
        try:
            voices = loop.run_until_complete(
                asyncio.wait_for(edge_tts.list_voices(), timeout=20)
            )
            return voices
        finally:
            try:
                loop.close()
            except Exception:
                pass
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
    """Remove HTML tags and clean text for TTS."""
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _play_bytes(audio_data: bytes, ext: str = ".mp3") -> str:
    """Write audio bytes to a temp file and play it. Must be called on main thread."""
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
        """Generate audio in background thread. Returns (audio_bytes, ext) or None."""
        config = get_config()
        engine = config.get("tts_engine", "edge_tts")
        text = _clean_text_for_tts(text)
        if not text:
            return None

        cache_key = f"{engine}:{text}"
        try:
            if engine == "edge_tts":
                return self._generate_edge_tts(text, cache_key)
            elif engine == "custom_url":
                return self._generate_custom(text, cache_key)
        except Exception as e:
            print(f"ERROR: TTS generation failed ({engine}): {e}")
        return None

    def _generate_edge_tts(self, text: str, cache_key: str):
        """Generate audio with edge-tts. Returns (bytes, ext) or None.

        关键：edge-tts 的同步接口 stream_sync() 内部用一个无超时的
        ThreadPoolExecutor 运行事件循环。若微软服务器长时间无响应
        （WebSocket keep-alive 挂起），worker 线程会永久阻塞，
        进程退出时无法结束。这里改为独立线程 + 总超时 + 强制关闭事件循环，
        保证线程一定能在超时后返回。
        """
        import asyncio
        import edge_tts

        config = get_config()
        language = config.get("learning_language", "英语")
        voice = _get_voice_for_language(language)

        # edge-tts 单次生成的总超时（秒）。正常一句话几秒即可完成。
        timeout = 30

        async def _collect():
            communicate = edge_tts.Communicate(text, voice)
            chunks = bytearray()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    chunks.extend(chunk["data"])
            return bytes(chunks)

        result_box = {}

        def _runner():
            loop = None
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                audio = loop.run_until_complete(
                    asyncio.wait_for(_collect(), timeout=timeout)
                )
                result_box["audio"] = audio
            except asyncio.TimeoutError:
                print(f"WARNING: edge-tts 生成超时 ({timeout}s)，已取消")
            except Exception as e:
                print(f"WARNING: edge-tts 生成失败: {e}")
            finally:
                # 强制关闭事件循环：会取消所有未完成的任务（包括挂起的 WebSocket），
                # 并等待它们真正退出，避免线程永久阻塞。
                if loop is not None:
                    try:
                        loop.run_until_complete(loop.shutdown_asyncgens())
                    except Exception:
                        pass
                    try:
                        loop.close()
                    except Exception:
                        pass

        # 用独立线程跑事件循环，方便在超时后彻底释放
        t = threading.Thread(target=_runner, daemon=True)
        t.start()
        t.join(timeout=timeout + 10)  # 给清理留余量

        if t.is_alive():
            # 极端情况：连清理都没在时限内完成。线程为 daemon，Python 退出时会被强制回收。
            print("WARNING: edge-tts 生成线程未能在时限内退出（daemon 化）")

        audio_data = result_box.get("audio")
        if not audio_data:
            return None

        self._cache[cache_key] = (audio_data, ".mp3")
        return (audio_data, ".mp3")

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
