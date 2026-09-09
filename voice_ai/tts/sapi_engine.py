"""Windows SAPI TTS adapter: real system voices with zero pip installs.

Speaks replies through the voices already on Windows (Microsoft David /
Zira / Hazel …) by driving PowerShell's ``System.Speech`` in a subprocess
with an encoded command — no quoting pitfalls, no extra dependencies.

Languages without an installed voice (e.g. hi/bn unless the Windows
language pack adds one) fall back to the offline codec engine, so a
reply is always produced. When Coqui TTS is installed it takes priority
in the ``auto`` chain.
"""
from __future__ import annotations

import base64
import os
import subprocess
import tempfile
import threading
import time

from .base import TtsEngine
from .offline import OfflineTts

# languages an English SAPI voice can read acceptably
LATIN_OK = {"en", "es", "fr", "de"}

_PS_TEMPLATE = """
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SetOutputToWaveFile('{wav}')
try {{ $s.SelectVoice('{voice}') }} catch {{ }}
$s.Rate = 0
$s.Speak([System.IO.File]::ReadAllText('{txt}', [System.Text.Encoding]::UTF8))
$s.Dispose()
"""


def _sapi_available() -> bool:
    from shutil import which
    return os.name == "nt" and which("powershell") is not None


class SapiTts(TtsEngine):
    name = "sapi"

    def __init__(self):
        self._voices: dict[str, str] | None = None  # lang -> voice name
        self._lock = threading.Lock()
        self._offline = OfflineTts()  # fallback for unvoiced scripts

    # ---------------------------------------------------------------- #
    def _probe(self) -> dict[str, str]:
        """Installed voices as {language_code: voice_name} (cached)."""
        if self._voices is not None:
            return self._voices
        ps = ("Add-Type -AssemblyName System.Speech\n"
              "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
              "$s.GetInstalledVoices() | ForEach-Object { "
              "$_.VoiceInfo.Culture.TwoLetterISOLanguageName + '|' + "
              "$_.VoiceInfo.Name }")
        enc = base64.b64encode(ps.encode("utf-16-le")).decode("ascii")
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive",
                 "-EncodedCommand", enc],
                capture_output=True, text=True, timeout=30).stdout
        except (OSError, subprocess.TimeoutExpired):
            self._voices = {}
            return self._voices
        voices: dict[str, str] = {}
        for line in out.splitlines():
            line = line.strip()
            if "|" in line:
                lang, name = line.split("|", 1)
                voices.setdefault(lang.lower(), name)
        self._voices = voices
        return self._voices

    def warmup(self) -> float:
        t0 = time.monotonic()
        self._probe()
        try:  # JIT PowerShell + SAPI so the first user reply is fast
            self.synthesize("ok", "en")
        except Exception:
            pass
        return time.monotonic() - t0

    # ---------------------------------------------------------------- #
    def synthesize(self, text: str, lang: str = "en") -> tuple:
        lang = lang.split("-")[0]
        voices = self._probe()
        voice = voices.get(lang) or (voices.get("en") if lang in LATIN_OK
                                     else None)
        if voice is None:
            # no voice for this script (e.g. hi/bn without the language
            # pack) — the codec at least says the words in its own way
            return self._offline.synthesize(text, lang)
        with self._lock:
            return self._speak_windows(text, voice)

    def _speak_windows(self, text: str, voice: str) -> tuple:
        from ..audio.wavio import read_wav
        tmp = tempfile.mkdtemp(prefix="via-sapi-")
        txt_path = os.path.join(tmp, "reply.txt")
        wav_path = os.path.join(tmp, "reply.wav")
        try:
            with open(txt_path, "w", encoding="utf-8") as fh:
                fh.write(text)
            ps = _PS_TEMPLATE.format(wav=wav_path, voice=voice, txt=txt_path)
            enc = base64.b64encode(ps.encode("utf-16-le")).decode("ascii")
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive",
                 "-EncodedCommand", enc],
                capture_output=True, timeout=30, check=True)
            return read_wav(wav_path)
        finally:
            for p in (txt_path, wav_path):
                try:
                    os.remove(p)
                except OSError:
                    pass
            try:
                os.rmdir(tmp)
            except OSError:
                pass
