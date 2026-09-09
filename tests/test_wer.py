"""WER / alignment unit tests."""
import unittest

from voice_ai.asr.wer import accuracy, align, confusion_pairs, levenshtein, wer


class TestWer(unittest.TestCase):
    def test_perfect(self):
        self.assertEqual(wer("a b c", "a b c"), 0.0)
        self.assertEqual(accuracy("a b c", "a b c"), 1.0)

    def test_known_rates(self):
        self.assertEqual(wer("a b c d", "a b c x"), 0.25)   # 1 sub
        self.assertEqual(wer("a b c d", "a b c"), 0.25)     # 1 del
        self.assertEqual(wer("a b c", "a b x y"), 2 / 3)    # 1 sub + 1 ins
        self.assertEqual(wer("a b c", "x y z"), 1.0)        # 3 subs

    def test_empty_reference(self):
        self.assertEqual(wer("", "anything"), 0.0)

    def test_alignment_ops(self):
        ops = align("a b c".split(), "a x c".split())
        self.assertEqual(ops, [("equal", "a", "a"), ("sub", "b", "x"),
                               ("equal", "c", "c")])

    def test_confusion_pairs(self):
        pairs = confusion_pairs("the cat sat".split(), "the hat sat".split())
        self.assertEqual(pairs, [("hat", "cat")])

    def test_levenshtein(self):
        self.assertEqual(levenshtein([1, 2, 3], [1, 2, 3]), 0)
        self.assertEqual(levenshtein([1, 2], [2, 1]), 2)
        self.assertEqual(levenshtein([], [1]), 1)


if __name__ == "__main__":
    unittest.main()
