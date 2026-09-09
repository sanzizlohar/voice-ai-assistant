"""Continuous-learning tests: confusion model, hotwords, tracker."""
import unittest

from voice_ai.learn.confusion import ConfusionModel
from voice_ai.learn.tracker import AccuracyTracker
from voice_ai.learn.vocab import HotwordSet
from voice_ai.text.normalize import LANGUAGES


class TestConfusion(unittest.TestCase):
    def test_repeated_confusion_becomes_rule(self):
        m = ConfusionModel()
        m.observe("en", ["note", "buy", "coffee"], ["note", "but", "coffee"])
        self.assertEqual(m.rules(), [])  # one observation is not enough
        m.observe("en", ["note", "buy", "coffee"], ["note", "but", "coffee"])
        rules = m.rules()
        self.assertEqual(rules[0][:3], ("en", "but", "buy"))
        out, fired = m.apply(["note", "but", "coffee"], "en")
        self.assertEqual(out, ["note", "buy", "coffee"])
        self.assertTrue(fired)

    def test_one_off_confusion_does_not_fire(self):
        m = ConfusionModel()
        m.observe("en", ["a", "b"], ["a", "x"])
        out, fired = m.apply(["a", "x"], "en")
        self.assertEqual(out, ["a", "x"])
        self.assertFalse(fired)

    def test_low_confidence_does_not_fire(self):
        m = ConfusionModel()
        # 'x' maps to two different rights → conf 0.5 each
        m.observe("en", ["r1"], ["x"])
        m.observe("en", ["r2"], ["x"])
        out, fired = m.apply(["x"], "en")
        self.assertEqual(out, ["x"])  # conf 0.5 == min_conf… edge
        # strictly below threshold must not fire
        m2 = ConfusionModel()
        m2.observe("en", ["r1"], ["x"])
        m2.observe("en", ["r2"], ["x"])
        m2.observe("en", ["r2"], ["x"])
        out2, _ = m2.apply(["x"], "en")
        self.assertEqual(out2, ["r2"])  # 2/3 evidence wins

    def test_unk_recovery(self):
        m = ConfusionModel()
        for _ in range(2):
            m.observe("en", ["kolkata"], ["<unk>"])
        out, fired = m.apply(["what", "<unk>", "weather"], "en")
        self.assertEqual(out, ["what", "kolkata", "weather"])

    def test_language_isolation(self):
        m = ConfusionModel()
        m.observe("en", ["buy"], ["but"])
        m.observe("en", ["buy"], ["but"])
        out, _ = m.apply(["but"], "hi")
        self.assertEqual(out, ["but"], "rule leaked across languages")


class TestHotwords(unittest.TestCase):
    def test_boost_and_fuzzy_apply(self):
        h = HotwordSet()
        vocab = LANGUAGES["en"].vocab()
        h.observe_correction("en", ["soumen", "kolkata"], vocab)
        h.boost("en", "soumen", 1.0)  # second mention → weight 2
        out, fired = h.apply(["call", "sourmen", "today"], "en")
        self.assertEqual(out, ["call", "soumen", "today"])

    def test_vocab_words_are_not_hotwords(self):
        h = HotwordSet()
        vocab = LANGUAGES["en"].vocab()
        touched = h.observe_correction("en", ["note", "coffee"], vocab)
        self.assertEqual(touched, 0)

    def test_terms_for_prompt(self):
        h = HotwordSet()
        h.boost("en", "zebra", 5)
        self.assertEqual(h.terms_for("en-US"), ["zebra"])


class TestTracker(unittest.TestCase):
    def test_trend_detects_improvement(self):
        t = AccuracyTracker()
        for _ in range(30):
            t.update("en", 0.80)
        for _ in range(30):
            t.update("en", 0.95)
        snap = t.snapshot()
        self.assertAlmostEqual(snap["trend_pp"], 15.0, delta=3.0)
        self.assertGreater(snap["accuracy"], 0.85)

    def test_per_language_split(self):
        t = AccuracyTracker()
        t.update("en", 0.9)
        t.update("hi", 0.7)
        snap = t.snapshot()
        self.assertEqual(snap["by_lang"]["en"], 0.9)
        self.assertEqual(snap["by_lang"]["hi"], 0.7)

    def test_empty(self):
        snap = AccuracyTracker().snapshot()
        self.assertEqual(snap["n"], 0)
        self.assertIsNone(snap["accuracy"])


if __name__ == "__main__":
    unittest.main()
