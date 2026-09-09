"""Utterance synthesis: multilingual phrase corpora rendered to PCM.

The synthesizer plays the role of a *speaker + telephone channel* for
tests, demos and benchmarks: it renders a phrase with the tone codec,
injects a systematic per-word confusion channel (one corrupted tone per
affected word — deterministic per word, mimicking the phoneme-driven
biases real acoustic models show) plus white noise, and returns the audio
with its ground-truth reference.
"""
from __future__ import annotations

import array
import random

from . import tonecodec
from .wavio import mix_noise
from ..text.normalize import LANGUAGES, spell_number, tokenize


def codec_words(tokens: list[str], lang: str) -> list[str]:
    """Speakable words for tokens — digits expand to spelled numbers."""
    out = []
    for t in tokens:
        if t.isdigit():
            out.extend(spell_number(lang, int(t)).split())
        else:
            out.append(t)
    return out


class Channel:
    """Deterministic corruption applied to the rendered audio."""

    def __init__(self, error_rate: float = 0.10, snr_db: float = 26.0,
                 seed: int = 0):
        self.error_rate = error_rate
        self.snr_db = snr_db
        self.seed = seed

    def corrupt_word(self, codec: tonecodec.Codec, word: str) -> list[int]:
        """Corrupt one word's code deterministically (seeded by the word
        itself, so a word is misheard the same way across utterances)."""
        tones = list(codec.tones_of(word) or ())
        rng = random.Random(f"{self.seed}:{word}")
        if not tones or rng.random() >= self.error_rate:
            return tones
        kind = rng.random()
        pos = rng.randrange(len(tones))
        if kind < 0.5:      # tone shifted one step → near-miss code
            tones[pos] = (tones[pos] + rng.choice((-1, 1))) % len(tonecodec.FREQS)
        elif kind < 0.75:   # tone dropped (short burst / channel loss)
            del tones[pos]
        else:               # tone duplicated (reverberation)
            tones.insert(pos, tones[pos])
        return tones


class Synthesizer:
    """Renders labeled utterances for a language using its codec."""

    def __init__(self, channel: Channel | None = None):
        self.channel = channel or Channel()
        self._codecs: dict[str, tonecodec.Codec] = {}

    def codec(self, lang: str) -> tonecodec.Codec:
        if lang not in self._codecs:
            self._codecs[lang] = tonecodec.Codec(LANGUAGES[lang].vocab())
        return self._codecs[lang]

    def utterance(self, lang: str, phrase: str,
                  dialect: str = "") -> tuple[array.array, dict]:
        """Render ``phrase`` → (pcm16, meta) with ground truth attached."""
        codec = self.codec(lang)
        words = codec_words(tokenize(phrase, lang, dialect), lang)
        codes = [self.channel.corrupt_word(codec, w) for w in words]
        # render the (possibly corrupted) codes — the "spoken" audio
        out: list[float] = []
        for i, code in enumerate(codes):
            for j, t in enumerate(code):
                out.extend(tonecodec._tone_burst(tonecodec.FREQS[t]))
                if j < len(code) - 1:
                    out.extend(tonecodec._silence(tonecodec.TONE_GAP_MS))
            out.extend(tonecodec._silence(
                tonecodec.WORD_GAP_MS if i < len(codes) - 1 else 120))
        pcm = array.array(
            "h", (int(max(-32768.0, min(32767.0, v * 32767))) for v in out))
        pcm = mix_noise(pcm, self.channel.snr_db,
                        random.Random(self.channel.seed))
        return pcm, {"lang": lang, "words": words,
                     "text": " ".join(words), "phrase": phrase}
