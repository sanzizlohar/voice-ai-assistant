"""Pipeline end-to-end tests: recognize → adapt → intent → reply, and the
feedback loop measurably improving a systematic mishearing."""
import unittest

from voice_ai.asr.base import AsrEngine, Hypothesis
from voice_ai.asr.offline import OfflineCodecAsr
from voice_ai.audio.synth import Channel, Synthesizer
from voice_ai.asr.wer import wer
from voice_ai.pipeline import Assistant, TOTAL_BUDGET_MS
from voice_ai.persistence.store import Store
from voice_ai.tts.offline import OfflineTts


class _SpyEngine(AsrEngine):
    """Records the language hint each transcribe call received."""

    name = "spy"

    def __init__(self):
        self.seen = []

    def transcribe(self, pcm, sr, lang=None):
        self.seen.append(lang)
        return Hypothesis(tokens=["অখন", "কয়টা", "বাজে"], language="bn",
                          confidence=0.9, engine=self.name)


class TestLanguageLocking(unittest.TestCase):
    def test_no_locked_language_unless_user_chose_one(self):
        """Regression: an implicit 'en' session used to force Whisper into
        English decoding — Bengali speech came back as English words."""
        spy = _SpyEngine()
        a = Assistant(asr_engine=spy, tts_engine=OfflineTts(),
                      llm_engine=False, store=Store(":memory:"))
        pcm, _ = Synthesizer(Channel(error_rate=0.0)).utterance(
            "en", "hello there")
        r = a.process(pcm, 16000, session_id="langtest")
        self.assertIsNone(spy.seen[-1],
                          "implicit session language must not lock ASR")
        self.assertEqual(r["language"], "bn")   # picked up from hypothesis
        # an explicit language choice DOES lock
        a.process(pcm, 16000, session_id="langtest2", lang="hi")
        self.assertEqual(spy.seen[-1], "hi")


class TestPipeline(unittest.TestCase):
    def setUp(self):
        # hermetic: tests always run on the offline doubles, even when
        # real Whisper/SAPI engines are installed
        self.a = Assistant(asr_engine=OfflineCodecAsr(),
                           tts_engine=OfflineTts(), llm_engine=False,
                           store=Store(":memory:"))
        self.a.warmup()
        self.syn = Synthesizer(Channel(error_rate=0.0, snr_db=26.0, seed=5))

    def test_recognize_and_reply(self):
        pcm, meta = self.syn.utterance("en", "what time is it")
        r = self.a.process(pcm, 16000, session_id="t1",
                           reference=meta["words"])
        self.assertEqual(r["tokens"], meta["words"])
        self.assertEqual(r["intent"], "time")
        self.assertIn("It is", r["reply"])
        self.assertLessEqual(r["total_ms"], TOTAL_BUDGET_MS * 2)
        self.assertTrue(r["budget_ok"])

    def test_multi_language_auto_detect(self):
        for lang, phrase in (("es", "que hora es"),
                             ("hi", "अभी समय क्या हुआ"),
                             ("bn", "এখন কয়টা বাজে")):
            pcm, meta = self.syn.utterance(lang, phrase)
            r = self.a.process(pcm, 16000, session_id="t2",
                               reference=meta["words"])
            self.assertEqual(r["language"], lang, phrase)
            self.assertNotEqual(r["intent"], "fallback", phrase)

    def test_dialect_flows_through(self):
        pcm, meta = self.syn.utterance(
            "en", "note pay the electricity bill", dialect="en-IN")
        r = self.a.process(pcm, 16000, session_id="t3",
                           reference=meta["words"], dialect="en-IN")
        self.assertEqual(r["dialect"], "en-IN")
        self.assertEqual(r["intent"], "note")

    def test_reply_audio_and_cache(self):
        pcm, _ = self.syn.utterance("en", "what time is it")
        r1 = self.a.process(pcm, 16000, session_id="t4")
        self.assertIsNotNone(r1["audio_b64"])
        r2 = self.a.process(pcm, 16000, session_id="t4")
        self.assertEqual(r2["stages"]["tts_ms"], 0.0, "cache miss")

    def test_no_speech(self):
        import array
        r = self.a.process(array.array("h", (0,) * 16000), 16000)
        self.assertEqual(r["error"], "no_speech")

    def test_feedback_improves_systematic_error(self):
        ch = Channel(error_rate=0.95, snr_db=24.0, seed=11)
        syn = Synthesizer(ch)
        phrase = "note buy coffee beans"

        def speak():
            pcm, meta = syn.utterance("en", phrase)
            return meta, self.a.process(pcm, 16000, session_id="learn",
                                        reference=meta["words"])

        meta, r1 = speak()
        before = wer(meta["words"], r1["tokens"])
        if before == 0:  # channel picked a clean seed word — still fine
            self.skipTest("channel produced no systematic error")
        # user corrects it twice (repeats the same utterance)
        for _ in range(2):
            _, r = speak()
            self.a.correct(r["id"], phrase)
        _, r2 = speak()
        after = wer(meta["words"], r2["tokens"])
        self.assertLess(after, before,
                        f"learning did not help: {before:.2f}→{after:.2f}")

    def test_rules_survive_restart(self):
        ch = Channel(error_rate=0.95, snr_db=24.0, seed=12)
        syn = Synthesizer(ch)
        ids = []
        for _ in range(2):
            pcm, meta = syn.utterance("en", "note buy coffee beans")
            r = self.a.process(pcm, 16000, session_id="persist",
                               reference=meta["words"])
            ids.append(r["id"])
            self.a.correct(r["id"], "note buy coffee beans")
        self.assertGreater(len(self.a.confusion.rules()), 0)

        a2 = Assistant(asr_engine=OfflineCodecAsr(), tts_engine=OfflineTts(),
                       llm_engine=False,
                       store=self.a.store)  # new brain, same sqlite
        a2.warmup()
        pcm, meta = syn.utterance("en", "note buy coffee beans")
        r = a2.process(pcm, 16000, session_id="persist2",
                       reference=meta["words"])
        self.assertTrue(r["rules_fired"], "rules lost across restart")


if __name__ == "__main__":
    unittest.main()
