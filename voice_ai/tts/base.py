"""TTS engine interface."""
from __future__ import annotations

from abc import ABC, abstractmethod


class TtsEngine(ABC):
    name: str = "tts"

    @abstractmethod
    def synthesize(self, text: str, lang: str = "en") -> tuple:
        """``text`` → (pcm 16-bit mono samples, sample_rate)."""

    def warmup(self) -> float:
        return 0.0


def get_tts(name: str = "auto", **kwargs) -> TtsEngine:
    """Factory. ``auto`` prefers, in order: Coqui TTS (natural neural
    voices, heavy), Edge neural voices (native hi/bn/en, needs internet,
    light), Windows SAPI (real system voices, offline), then the offline
    codec (runs everywhere)."""
    name = (name or "auto").lower()
    from importlib.util import find_spec
    if name in ("auto", "coqui") and find_spec("TTS") is not None:
        from .coqui_engine import CoquiTts
        return CoquiTts(**kwargs)
    if name in ("auto", "edge"):
        from .edge_engine import _edge_available
        if _edge_available():
            from .edge_engine import EdgeTts
            return EdgeTts(**kwargs)
        if name == "edge":
            raise ImportError("pip install edge-tts miniaudio")
    if name in ("auto", "sapi"):
        from .sapi_engine import _sapi_available, SapiTts
        if _sapi_available():
            return SapiTts(**kwargs)
        if name == "sapi":
            raise ImportError("SAPI voices need Windows + PowerShell")
    if name == "coqui":
        raise ImportError(
            "Coqui TTS not found — install it with:\n"
            "  pip install TTS   (coqui-tts package)")
    if name in ("auto", "offline"):
        from .offline import OfflineTts
        return OfflineTts()
    raise ValueError(f"unknown TTS engine '{name}' (auto/edge/sapi/coqui/offline)")
