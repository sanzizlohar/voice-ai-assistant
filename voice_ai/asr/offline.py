"""Offline ASR: decodes coded-speech audio with the tone codec.

Deterministic and dependency-free — the whole pipeline (multi-language
detection included) runs and tests without downloading models. Language
auto-detection decodes the tone groups against every language's codec and
keeps the one with the best match rate.
"""
from __future__ import annotations

import time

from ..audio import tonecodec
from ..audio.tonecodec import UNK, extract_tone_groups
from ..text.normalize import LANGUAGES
from .base import AsrEngine, Hypothesis


class OfflineCodecAsr(AsrEngine):
    name = "offline"

    def __init__(self):
        self._codecs: dict[str, tonecodec.Codec] = {}

    def codec(self, lang: str) -> tonecodec.Codec:
        if lang not in self._codecs:
            self._codecs[lang] = tonecodec.Codec(LANGUAGES[lang].vocab())
        return self._codecs[lang]

    def transcribe(self, pcm, sr: int, lang: str | None = None) -> Hypothesis:
        t0 = time.perf_counter()
        groups, confs = extract_tone_groups(pcm)
        t_decode = time.perf_counter()

        # always scan every language; the hinted one gets a prior bonus so
        # sessions are stable but strong evidence still overrides
        hint = (lang or "").split("-")[0] or None
        best_lang, best_words, best_score = hint or "en", [], -1e9
        for code in LANGUAGES:
            codec = self.codec(code)
            words, exact = codec.transcribe_groups(groups)
            # exact code hits identify the language; nearest-match guesses
            # are weak evidence and unknowns count against
            n_exact = sum(1 for e in exact if e)
            n_near = sum(1 for e, w in zip(exact, words)
                         if not e and w != UNK)
            n_unk = sum(1 for w in words if w == UNK)
            score = n_exact - 0.3 * n_near - 1.0 * n_unk
            if hint and code == hint:
                score += 0.6
            if score > best_score:
                best_lang, best_words, best_score = code, words, score

        confidence = (sum(confs) / len(confs)) if confs else 0.0
        audio_s = len(pcm) / (sr or tonecodec.SR)
        return Hypothesis(
            tokens=best_words, language=best_lang, confidence=round(confidence, 3),
            engine=self.name, audio_s=round(audio_s, 3),
            timings={"decode_ms": round((t_decode - t0) * 1000, 2),
                     "match_ms": round((time.perf_counter() - t_decode) * 1000, 2)},
        )
