# -*- coding: utf-8 -*-

import os
import re
import tempfile

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


def _get_voice_for_language(language: str) -> str:
    return TTS_VOICE_MAP.get(language, "en-US-EmmaMultilingualNeural")


def _get_anki_lang(language: str) -> str:
    return ANKI_LANG_MAP.get(language, "en_US")


def _clean_text_for_tts(text: str) -> str:
    """Remove HTML tags and clean text for TTS."""
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


class TTSManager:
    def __init__(self):
        self._tmpdir = tempfile.mkdtemp(prefix="contextflow_tts_")
        self._cache = {}  # cache_key -> audio file path

    def play_cached(self, text: str) -> str | None:
        """Check cache and play if hit. Returns file path on hit, None on miss."""
        config = get_config()
        engine = config.get("tts_engine", "edge_tts")
        text = _clean_text_for_tts(text)
        if not text:
            return ""

        cache_key = f"{engine}:{text}"
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if os.path.exists(cached):
                from aqt.sound import av_player
                av_player.play_file(cached)
                return cached
            else:
                del self._cache[cache_key]
        return None

    def is_anki_native(self) -> bool:
        return get_config().get("tts_engine", "edge_tts") == "anki_native"

    def play_anki_native(self, text: str):
        """Play via Anki native TTS (must be called from main thread)."""
        self._play_anki_native(_clean_text_for_tts(text))

    def generate(self, text: str) -> str | None:
        """Generate audio file (call from background thread). Returns file path or None."""
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
        """Generate audio file with edge-tts, return file path or None."""
        import edge_tts

        config = get_config()
        language = config.get("learning_language", "英语")
        voice = _get_voice_for_language(language)

        tmpfile = os.path.join(self._tmpdir, f"tts_{hash(text) & 0xFFFFFFFF}.mp3")
        communicate = edge_tts.Communicate(text, voice)
        communicate.save_sync(tmpfile)

        if os.path.exists(tmpfile):
            self._cache[cache_key] = tmpfile
            return tmpfile
        return None

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

    def _generate_custom(self, text: str, cache_key: str):
        """Generate audio file from custom URL, return file path or None."""
        import requests

        config = get_config()
        url = config.get("tts_custom_url", "")
        if not url:
            print("ERROR: Custom TTS URL not configured")
            return None

        language = config.get("learning_language", "英语")
        voice = _get_voice_for_language(language)

        resp = requests.post(
            url,
            json={"text": text, "voice": voice, "language": language},
            timeout=30,
        )
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        ext = ".mp3" if "mpeg" in content_type else ".wav"
        tmpfile = os.path.join(self._tmpdir, f"tts_custom_{hash(text) & 0xFFFFFFFF}{ext}")

        with open(tmpfile, "wb") as f:
            f.write(resp.content)

        self._cache[cache_key] = tmpfile
        return tmpfile


# Singleton instance
tts_manager = TTSManager()
