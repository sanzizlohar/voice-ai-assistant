"""Codec unit tests: determinism, roundtrip, noise robustness."""
import unittest

from voice_ai.audio import tonecodec
from voice_ai.audio.synth import Channel, Synthesizer
from voice_ai.text.normalize import LANGUAGES


class TestCodec(unittest.TestCase):
    def test_codes_deterministic_and_clean(self):
        vocab = LANGUAGES["en"].vocab()
        c1, c2 = tonecodec.Codec(vocab), tonecodec.Codec(vocab)
        self.assertEqual(sorted(c1.vocab), sorted(c2.vocab))
        for w in list(c1.vocab)[:50]:
            self.assertEqual(c1.tones_of(w), c2.tones_of(w))
            code = c1.tones_of(w)
            # no two adjacent identical tones (they would merge in render)
            self.assertTrue(all(code[i] != code[i + 1]
                                for i in range(len(code) - 1)))
            self.assertTrue(2 <= len(code) <= 6)

    def test_codes_unique_across_vocab(self):
        for lang in ("en", "hi", "bn"):
            codec = tonecodec.Codec(LANGUAGES[lang].vocab())
            words = [codec.word_of(t) for t in codec._words]
            self.assertEqual(len(set(codec._words)), len(codec.vocab))

    def test_roundtrip_all_languages_clean(self):
        syn = Synthesizer(Channel(error_rate=0.0, snr_db=26.0, seed=1))
        asr = __import__("voice_ai.asr.offline", fromlist=["OfflineCodecAsr"]) \
            .OfflineCodecAsr()
        for lang in LANGUAGES:
            for phrase in LANGUAGES[lang].corpus[:3]:
                pcm, meta = syn.utterance(lang, phrase)
                hyp = asr.transcribe(pcm, tonecodec.SR)
                self.assertEqual(hyp.tokens, meta["words"],
                                 f"{lang}: {phrase!r}")
                self.assertEqual(hyp.language, lang)

    def test_noise_channel_keeps_wer_bounded(self):
        from voice_ai.asr.offline import OfflineCodecAsr
        from voice_ai.asr.wer import wer
        syn = Synthesizer(Channel(error_rate=0.15, snr_db=24.0, seed=9))
        asr = OfflineCodecAsr()
        err = words = 0
        for lang in ("en", "hi"):
            for phrase in LANGUAGES[lang].corpus:
                pcm, meta = syn.utterance(lang, phrase)
                hyp = asr.transcribe(pcm, tonecodec.SR)
                err += wer(meta["words"], hyp.tokens) * len(meta["words"])
                words += len(meta["words"])
        w = err / words
        self.assertGreater(w, 0.01, "channel produced no errors at all")
        self.assertLess(w, 0.35, f"channel too destructive: WER {w:.1%}")

    def test_decode_empty_audio(self):
        codec = tonecodec.Codec(LANGUAGES["en"].vocab())
        groups, confs = tonecodec.extract_tone_groups(tonecodec.array.array("h"))
        self.assertEqual(groups, [])
        self.assertEqual(codec.transcribe_groups(groups), ([], []))


if __name__ == "__main__":
    unittest.main()
