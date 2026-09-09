"""Offline TTS: speaks text through the tone codec ("beeper speech").

Same codec the offline ASR decodes, which gives the pipeline a beautiful
roundtrip property for tests: TTS(text) → WAV → ASR == text. Swap in the
Coqui engine for natural voices; nothing else changes.
"""
from __future__ import annotations

import array

from ..audio import tonecodec
from ..audio.tonecodec import SR
from ..text.normalize import LANGUAGES, tokenize
from .base import TtsEngine


class OfflineTts(TtsEngine):
    name = "offline"

    def __init__(self):
        self._codecs: dict[str, tonecodec.Codec] = {}

    def codec(self, lang: str) -> tonecodec.Codec:
        lang = lang.split("-")[0]
        if lang not in self._codecs:
            self._codecs[lang] = tonecodec.Codec(LANGUAGES[lang].vocab())
        return self._codecs[lang]

    def synthesize(self, text: str, lang: str = "en") -> tuple:
        codec = self.codec(lang)
        words = []
        for t in tokenize(text, lang.split("-")[0]):
            if t.isdigit():
                from ..text.normalize import spell_number
                words.extend(spell_number(lang, int(t)).split())
            else:
                words.append(t)
        pcm = array.array(
            "h", (int(max(-32768.0, min(32767.0, v * 32767)))
                  for v in codec.render_words(words)))
        return pcm, SR
