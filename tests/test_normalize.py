"""Text normalization tests: dialects, Indic scripts, numbers."""
import unittest

from voice_ai.text.normalize import (
    LANGUAGES, join_tokens, spell_number, spell_time, tokenize)


class TestTokenize(unittest.TestCase):
    def test_latin_folding(self):
        self.assertEqual(tokenize("Qué Hora Es", "es"), ["que", "hora", "es"])
        self.assertEqual(tokenize("Météo pluie", "fr"), ["meteo", "pluie"])

    def test_devanagari_matras_preserved(self):
        toks = tokenize("नमस्ते आप कैसे हो", "hi")
        self.assertEqual(toks, ["नमस्ते", "आप", "कैसे", "हो"])

    def test_bengali_preserved(self):
        toks = tokenize("নমস্কার কেমন আছো", "bn")
        self.assertEqual(toks, ["নমস্কার", "কেমন", "আছো"])

    def test_number_words_to_digits(self):
        self.assertEqual(tokenize("twelve plus thirty", "en"),
                         ["12", "plus", "30"])
        self.assertEqual(tokenize("पाँच मिनट", "hi"), ["5", "मिनट"])

    def test_dialect_map(self):
        toks = tokenize("i will prepone the meeting", "en", "en-IN")
        self.assertIn("advance", toks)
        self.assertNotIn("prepone", toks)
        gb = tokenize("the grey colour cheque", "en", "en-GB")
        self.assertEqual(gb, ["the", "gray", "color", "check"])


class TestSpelling(unittest.TestCase):
    def test_english_tens(self):
        self.assertEqual(spell_number("en", 23), "twenty three")
        self.assertEqual(spell_number("en", 90), "ninety")
        self.assertEqual(spell_number("en", 7), "seven")

    def test_indic(self):
        self.assertEqual(spell_number("hi", 5), "पाँच")
        self.assertEqual(spell_number("bn", 5), "পাঁচ")
        self.assertEqual(spell_number("hi", 30), "तीन शून्य")  # digit-wise

    def test_time(self):
        self.assertEqual(spell_time("en", 14, 5), "fourteen five")
        self.assertEqual(spell_time("en", 0, 44), "twelve forty four")
        self.assertEqual(spell_time("hi", 9, 41), "9:41")   # neural-friendly
        self.assertEqual(spell_time("bn", 23, 5), "23:05")

    def test_join_display(self):
        self.assertEqual(join_tokens(["12", "plus", "30"], "en"),
                         "Twelve plus thirty.")
        text = join_tokens(["5", "मिनट"], "hi")
        self.assertIn("पाँच", text)


class TestRegistry(unittest.TestCase):
    def test_vocab_nonempty_all_languages(self):
        for code, language in LANGUAGES.items():
            vocab = language.vocab()
            self.assertGreater(len(vocab), 40, code)
            self.assertFalse(any(w.isdigit() for w in vocab),
                             f"{code}: digit tokens leaked into vocab")

    def test_corpus_tokens_in_vocab(self):
        for code, language in LANGUAGES.items():
            from voice_ai.audio.synth import codec_words
            for phrase in language.corpus:
                for w in codec_words(tokenize(phrase, code), code):
                    self.assertIn(w, language.vocab(),
                                  f"{code}: {w!r} missing from vocab")

    def test_dialect_corpus_tokens_in_vocab(self):
        language = LANGUAGES["en"]
        from voice_ai.audio.synth import codec_words
        for dialect, phrases in language.dialect_corpus.items():
            for phrase in phrases:
                for w in codec_words(tokenize(phrase, "en", dialect), "en"):
                    self.assertIn(w, language.vocab(),
                                  f"{dialect}: {w!r} missing from vocab")


if __name__ == "__main__":
    unittest.main()
