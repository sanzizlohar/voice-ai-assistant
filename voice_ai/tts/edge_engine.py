"""Microsoft Edge neural TTS adapter: native-sounding voices for every
language, including Bengali (bn-BD-NabanitaNeural), Hindi (hi-IN-SwaraNeural)
and English (en-US-AriaNeural). Small pip install, no torch:

    pip install edge-tts miniaudio

Needs internet at reply time (Microsoft's neural service). Any failure —
offline, rate-limited, missing package — falls back per-call to the next
engine in the chain (SAPI voices, then the offline codec), so a reply is
always produced. The engine marks itself down for 5 minutes after a
network failure instead of stalling every reply.
"""
from __future__ import annotations

import array
import os
import subprocess
import sys
import tempfile
import threading
import time

from .base import TtsEngine
from .offline import OfflineTts

VOICES = {
    "en": "en-US-AriaNeural",
    "hi": "hi-IN-SwaraNeural",
    "bn": "bn-BD-NabanitaNeural",
    "es": "es-ES-ElviraNeural",
    "fr": "fr-FR-DeniseNeural",
    "de": "de-DE-KatjaNeural",
}

DOWN_BACKOFF_S = 300  # after a network failure, skip edge for 5 minutes


def _edge_available() -> bool:
    from importlib.util import find_spec
    return (find_spec("edge_tts") is not None
            and find_spec("miniaudio") is not None)


class EdgeTts(TtsEngine):
    name = "edge"

    def __init__(self):
        self._offline = OfflineTts()
        self._lock = threading.Lock()
        self._down_until = 0.0

    def warmup(self) -> float:
        t0 = time.monotonic()
        try:
            self.synthesize("ok", "en")
        except Exception:
            pass
        return time.monotonic() - t0

    # ---------------------------------------------------------------- #
    def synthesize(self, text: str, lang: str = "en") -> tuple:
        lang = lang.split("-")[0]
        voice = VOICES.get(lang)
        if voice is None:
            return self._offline.synthesize(text, lang)
        if time.monotonic() < self._down_until:
            return self._offline.synthesize(text, lang)
        with self._lock:
            try:
                return self._speak_neural(text, voice)
            except Exception:
                self._down_until = time.monotonic() + DOWN_BACKOFF_S
                return self._offline.synthesize(text, lang)

    def _speak_neural(self, text: str, voice: str) -> tuple:
        import miniaudio
        tmp = tempfile.mkdtemp(prefix="via-edge-")
        mp3 = os.path.join(tmp, "reply.mp3")
        try:
            run = subprocess.run(
                [sys.executable, "-m", "edge_tts", "--voice", voice,
                 "--text", text, "--write-media", mp3],
                capture_output=True, timeout=45)
            if (run.returncode != 0 or not os.path.exists(mp3)
                    or os.path.getsize(mp3) < 500):
                detail = run.stderr.decode(errors="replace")[:120]
                raise RuntimeError(f"edge-tts failed: {detail}")
            with open(mp3, "rb") as fh:
                raw = fh.read()
            dec = miniaudio.decode(raw, nchannels=1, sample_rate=22050,
                                   output_format=miniaudio.SampleFormat.SIGNED16)
            pcm = array.array("h", (max(-32768, min(32767, s))
                                    for s in dec.samples))
            return pcm, 22050
        finally:
            try:
                os.remove(mp3)
            except OSError:
                pass
            try:
                os.rmdir(tmp)
            except OSError:
                pass
