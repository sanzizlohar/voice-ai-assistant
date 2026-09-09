"""TTS engine tests: offline synthesis + roundtrip through the ASR."""
import unittest

from voice_ai.asr.offline import OfflineCodecAsr
from voice_ai.tts.base import get_tts
from voice_ai.tts.offline import OfflineTts


class TestOfflineTts(unittest.TestCase):
    def test_produces_audio(self):
        tts = OfflineTts()
        pcm, sr = tts.synthesize("what time is it", "en")
        self.assertGreater(len(pcm), 16000)  # > 1 s of audio
        self.assertEqual(sr, 16000)

    def test_roundtrip_tts_to_asr(self):
        """What the assistant says, it must be able to hear back."""
        tts, asr = OfflineTts(), OfflineCodecAsr()
        for lang, text in (("en", "what time is it"),
                           ("hi", "अभी समय क्या हुआ")):
            pcm, sr = tts.synthesize(text, lang)
            hyp = asr.transcribe(pcm, sr)
            self.assertEqual(hyp.tokens, text.lower().split(), f"{lang}")

    def test_unknown_fallback_is_not_silent(self):
        tts = OfflineTts()
        pcm_known, _ = tts.synthesize("hello", "en")
        pcm_part, _ = tts.synthesize("hello zzzz", "en")
        self.assertLess(len(pcm_part), len(pcm_known) * 2.5)


class TestFactory(unittest.TestCase):
    def test_auto_gives_real_voice_or_offline(self):
        # auto prefers Coqui (if installed) → Edge neural → SAPI → offline
        tts = get_tts("auto")
        self.assertNotIn("coqui", tts.name.lower())
        self.assertIn(tts.name, ("edge", "sapi", "offline"))

    def test_offline_explicit(self):
        self.assertIsInstance(get_tts("offline"), OfflineTts)

    def test_unknown_raises(self):
        with self.assertRaises(ValueError):
            get_tts("robot")


if __name__ == "__main__":
    unittest.main()
