"""Coqui TTS adapter (optional). Imported lazily — the stdlib core never
needs it.

    pip install TTS          # coqui-ai/TTS
    # multi-speaker/multi-lang models supported; pick via env:
    export VIA_TTS_MODEL=tts_models/en/ljspeech/tacotron2-DDC
"""
from __future__ import annotations

import array
import os
import threading
import time

from .base import TtsEngine

# per-language default Coqui models (en only by default; others fall back
# to the closest available voice)
DEFAULT_MODEL = "tts_models/en/ljspeech/tacotron2-DDC"


class CoquiTts(TtsEngine):
    name = "coqui"

    def __init__(self, model: str | None = None):
        self.model_name = (model or os.environ.get("VIA_TTS_MODEL")
                           or DEFAULT_MODEL)
        self._tts = None
        self._lock = threading.Lock()  # Coqui models are not thread-safe

    def warmup(self) -> float:
        if self._tts is not None:
            return 0.0
        t0 = time.perf_counter()
        from TTS.api import TTS  # type: ignore
        self._tts = TTS(self.model_name)
        self.name = f"coqui:{self.model_name.split('/')[-1]}"
        return time.perf_counter() - t0

    def synthesize(self, text: str, lang: str = "en") -> tuple:
        self.warmup()
        with self._lock:
            wav = self._tts.tts(text, language=lang.split("-")[0]
                                if self._tts.is_multi_lingual else None)
        sr = self._tts.synthesizer.output_sample_rate
        pcm = array.array("h", (int(max(-1.0, min(1.0, v)) * 32767)
                                for v in wav))
        return pcm, sr
