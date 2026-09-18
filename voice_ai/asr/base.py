"""ASR engine interface and registry.

Every engine — the offline tone-codec double, faster-whisper, or
openai-whisper — speaks this same contract, so the pipeline, server and
learning loop are engine-agnostic.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Hypothesis:
    """One recognition result. ``tokens`` are raw lowercase words (the
    codec speaks spelled numbers); ``display`` is the human form."""

    tokens: list[str]
    language: str
    confidence: float = 0.0
    engine: str = "offline"
    audio_s: float = 0.0
    timings: dict = field(default_factory=dict)
    dialect: str = ""
    note: str = ""   # honest quality hint surfaced in the UI (e.g. bn voice)

    @property
    def text(self) -> str:
        return " ".join(self.tokens)

    @property
    def display(self) -> str:
        from ..text.normalize import join_tokens
        return join_tokens(self.tokens, self.language.split("-")[0])


class AsrEngine(ABC):
    name: str = "asr"

    @abstractmethod
    def transcribe(self, pcm, sr: int, lang: str | None = None) -> Hypothesis:
        """Recognize 16-bit mono PCM. ``lang=None`` → auto-detect."""

    def warmup(self) -> float:
        """Optional model load; returns seconds. Default: nothing to do."""
        return 0.0

    def hotword_prompt(self, terms: list[str]) -> str | None:
        """Vocabulary bias hint (Whisper uses it as ``initial_prompt``)."""
        return " ".join(terms[:32]) or None


def detect_language(tokens: list[str], lang_hint: str | None = None) -> str:
    """Cheap post-hoc detection for engines that don't report one: score
    token coverage against each language's vocabulary."""
    if lang_hint:
        return lang_hint.split("-")[0]
    from ..text.normalize import LANGUAGES
    best, best_score = "en", -1.0
    for code, language in LANGUAGES.items():
        vocab = language.vocab()
        known = sum(1 for t in tokens if t in vocab)
        score = known / max(1, len(tokens))
        if score > best_score:
            best, best_score = code, score
    return best


def get_engine(name: str = "auto", **kwargs) -> AsrEngine:
    """Factory. ``auto`` prefers, in order:
    1. a cloud Whisper endpoint (auto-configured from the brain's
       Groq/OpenAI settings — best Bengali/Hindi accuracy, ~1 s)
    2. a local Whisper install
    3. the offline tone-codec engine."""
    name = (name or "auto").lower()
    local = None
    if name in ("auto", "whisper") and _whisper_available():
        from .whisper_engine import WhisperAsr
        local = WhisperAsr(**kwargs)
    if name in ("auto", "whisper"):
        cloud = _cloud_asr_engine()
        if cloud is not None:
            return cloud[0]   # carries the local model as its fallback
        if local is not None:
            return local
        if name == "whisper":
            raise ImportError(
                "no Whisper backend found — install one with:\n"
                "  pip install faster-whisper   (recommended)\n"
                "  pip install openai-whisper   (classic)")
    if name == "offline":
        from .offline import OfflineCodecAsr
        return OfflineCodecAsr(**kwargs)
    if name == "offline" or local is None:
        from .offline import OfflineCodecAsr
        return OfflineCodecAsr(**kwargs)
    return local


def _cloud_asr_engine() -> tuple | None:
    """(CloudWhisperAsr, local_engine) discovery from env or brain config."""
    import os
    from .cloud_whisper import CloudWhisperAsr
    base = os.environ.get("VIA_ASR_BASE_URL")
    key = os.environ.get("VIA_ASR_API_KEY")
    model = os.environ.get("VIA_ASR_MODEL")
    local = None
    if _whisper_available():
        from .whisper_engine import WhisperAsr
        local = WhisperAsr()
    if base or key or model:
        return (CloudWhisperAsr(base or "https://api.openai.com/v1",
                                key or "", model or "whisper-1", local),
                local)
    from ..llm import config as brain
    cfg = brain.load_config()
    if not cfg:
        return None
    provider = cfg.get("provider")
    api_key = cfg.get("api_key", "")
    if provider == "groq" and api_key:
        return (CloudWhisperAsr(cfg["base_url"], api_key,
                                "whisper-large-v3", local), local)
    if provider == "openai" and api_key:
        return (CloudWhisperAsr(cfg["base_url"], api_key,
                                "whisper-1", local), local)
    return None



def _whisper_available() -> bool:
    from importlib.util import find_spec
    return (find_spec("faster_whisper") is not None
            or find_spec("whisper") is not None)


class _NullTimings:
    @staticmethod
    def now() -> float:
        return time.perf_counter()
