# -*- coding: utf-8 -*-

import json
import os
import re
import shutil
import subprocess
import sys
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

def _get_voice_for_language(language: str) -> str:
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
        """Generate audio with edge-tts. Returns (bytes, ext) or None."""
        import edge_tts

        config = get_config()
        language = config.get("learning_language", "英语")
        voice = _get_voice_for_language(language)

        communicate = edge_tts.Communicate(text, voice)
        chunks = bytearray()
        for chunk in communicate.stream_sync():
            if chunk["type"] == "audio":
                chunks.extend(chunk["data"])

        if not chunks:
            return None

        audio_data = bytes(chunks)
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
        """Generate audio from custom URL. Returns (bytes, ext) or None."""
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
        audio_data = resp.content

        self._cache[cache_key] = (audio_data, ext)
        return (audio_data, ext)


# Singleton instance
tts_manager = TTSManager()
