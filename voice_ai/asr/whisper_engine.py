"""OpenAI Whisper ASR adapter (faster-whisper preferred, openai-whisper
fallback). Both are optional at runtime — imported lazily so the pure-
stdlib core never needs them.

    pip install faster-whisper    # CTranslate2, int8 quantized
    pip install ctranslate2==4.4.0  # pin if the newest wheel segfaults
    pip install openai-whisper    # classic PyTorch implementation

Language handling (this is where Indic voices live or die):
* The caller's explicit language always wins (session locked via ?lang=).
* Otherwise Whisper auto-detects. Base's own guess is unreliable for
  short Indic clips (it heard Bengali as "Portuguese"), so when its guess
  is not a language we speak, a tiny model re-checks and we re-decode.
* hi/bn decode with a short native-script ``initial_prompt`` — without
  it Whisper transliterates Hindi to Latin or wanders into other scripts.
* Bengali on CPU-class hardware: base/tiny cannot decode it (garbage) and
  small takes minutes — the adapter sets an honest ``note`` so the UI can
  say so instead of showing gibberish. On stronger hardware set
  ``VIA_WHISPER_MODEL=small`` and Bengali voice works.

Model: env ``VIA_WHISPER_MODEL`` (default ``base``). Beam: env
``VIA_WHISPER_BEAM`` (default 1 = greedy, lowest latency).

The learned hotword vocabulary rides along as ``initial_prompt`` terms.
"""
from __future__ import annotations

import os
import time

from .base import AsrEngine, Hypothesis

SUPPORTED = {"en", "es", "fr", "de", "hi", "bn"}
# short native-script prompts keep hi/bn decoding inside the right script
SCRIPT_PROMPTS = {
    "hi": "यह वाक्य हिन्दी भाषा में लिखा है।",
    "bn": "এই কথা বাংলা ভাষায় লেখা হল।",
}


def _script_ratio(text: str, lo: int, hi: int) -> float:
    """Share of alphabetic chars inside a unicode block (Bengali 0980-09FF,
    Devanagari 0900-097F)."""
    alpha = [c for c in text if c.isalpha()]
    if not alpha:
        return 0.0
    return sum(1 for c in alpha if lo <= ord(c) <= hi) / len(alpha)


class WhisperAsr(AsrEngine):
    def __init__(self, model: str | None = None, beam_size: int | None = None,
                 cpu_threads: int = 0):
        self.model_size = model or os.environ.get("VIA_WHISPER_MODEL", "base")
        self.beam_size = int(beam_size
                             or os.environ.get("VIA_WHISPER_BEAM", "1"))
        self._backend = None
        self._model = None
        self._tiny = None          # cheap second-opinion detector
        self._cpu_threads = cpu_threads or min(8, os.cpu_count() or 4)
        self.name = "whisper"

    # ---------------------------------------------------------------- #
    def warmup(self) -> float:
        if self._model is not None:
            return 0.0
        t0 = time.perf_counter()
        try:
            from faster_whisper import WhisperModel  # type: ignore
            self._backend = "faster-whisper"
            self._model = WhisperModel(
                self.model_size, device="cpu", compute_type="int8",
                cpu_threads=self._cpu_threads)
            self._tiny = WhisperModel(
                "tiny", device="cpu", compute_type="int8",
                cpu_threads=self._cpu_threads)
        except ImportError:
            import whisper  # type: ignore
            self._backend = "openai-whisper"
            self._model = whisper.load_model(self.model_size)
        self.name = f"whisper:{self.model_size}"
        if self._backend == "faster-whisper":
            # JIT both models so the first real user pays ~nothing
            import numpy as np
            z = np.zeros(16000, dtype=np.float32)
            list(self._model.transcribe(z, language="en", beam_size=1)[0])
            list(self._tiny.transcribe(z, language=None, beam_size=1)[0])
        return time.perf_counter() - t0

    # ---------------------------------------------------------------- #
    def _decode(self, audio, language: str | None):
        kwargs = dict(beam_size=self.beam_size, vad_filter=False,
                      condition_on_previous_text=False)
        if language is not None:
            kwargs["language"] = language
            prompt = SCRIPT_PROMPTS.get(language)
            if prompt:
                kwargs["initial_prompt"] = prompt
        segments, info = self._model.transcribe(audio, **kwargs)
        parts, probs = [], []
        for seg in segments:
            parts.append(seg.text.strip())
            probs.append(1.0 - seg.no_speech_prob)
        text = " ".join(p for p in parts if p).strip()
        conf = sum(probs) / len(probs) if probs else 0.0
        detected = getattr(info, "language", None) or language or "en"
        return text, detected, conf

    def _detect_with_tiny(self, audio) -> str:
        """Second opinion with the tiny model (base's guess for short
        Indic clips is often a random European language)."""
        if self._tiny is None:
            return "en"
        segments, info = self._tiny.transcribe(
            audio, language=None, beam_size=1, vad_filter=False,
            condition_on_previous_text=False)
        for _ in segments:  # detection happens with the segments pass
            break
        return getattr(info, "language", "en") or "en"

    def transcribe(self, pcm, sr: int, lang: str | None = None) -> Hypothesis:
        self.warmup()
        t0 = time.perf_counter()
        # faster-whisper needs np.ndarray; both backends require numpy anyway
        import numpy as np
        audio = np.asarray(pcm, dtype=np.float32) / 32768.0
        lang_given = (lang or "").split("-")[0] or None

        note = ""
        if lang_given is not None:
            text, language, conf = self._decode(audio, lang_given)
        else:
            text, language, conf = self._decode(audio, None)
            if language not in SUPPORTED:
                # base guessed a language we don't speak — tiny re-checks
                candidate = self._detect_with_tiny(audio)
                if candidate in SUPPORTED:
                    text, language, conf = self._decode(audio, candidate)

        if language == "bn" and text:
            from ..text.normalize import strip_accents
            ratio = _script_ratio(text, 0x0980, 0x09FF)
            if ratio < 0.3:
                note = ("Bengali speech needs a stronger CPU/model here "
                        "(VIA_WHISPER_MODEL=small) — type mode works fully "
                        "for বাংলা")

        from ..text.normalize import tokenize
        tokens = tokenize(text, (language or "en").split("-")[0])
        audio_s = len(pcm) / (sr or 16000)
        return Hypothesis(
            tokens=tokens, language=language, confidence=round(conf, 3),
            engine=self.name, audio_s=round(audio_s, 3),
            timings={"asr_ms": round((time.perf_counter() - t0) * 1000, 2)},
            note=note)

    def hotword_prompt(self, terms: list[str]) -> str | None:
        prompt = ", ".join(terms[:32])
        return prompt or None
