"""NLU intent tests: multilingual keywords, slots, math, timers."""
import unittest

from voice_ai.nlu.intents import IntentEngine, words_to_number


class TestEnglish(unittest.TestCase):
    def setUp(self):
        self.nlu = IntentEngine()

    def test_math(self):
        intent, slots, reply = self.nlu.handle(
            "what is twelve plus thirty".split(), "en")
        self.assertEqual(intent, "math")
        self.assertEqual(slots["a"], 12)
        self.assertEqual(slots["b"], 30)
        self.assertIn("42", reply)

    def test_math_words(self):
        self.assertEqual(words_to_number("twenty three".split()), 23)
        self.assertEqual(words_to_number("ninety".split()), 90)
        self.assertEqual(words_to_number("five".split()), 5)

    def test_division_by_zero(self):
        intent, slots, reply = self.nlu.handle(
            "what is ten divided by zero".split(), "en")
        self.assertEqual(intent, "math")
        self.assertIn("not allowed", reply)

    def test_timer_slot(self):
        intent, slots, reply = self.nlu.handle(
            "set a timer for five minutes".split(), "en")
        self.assertEqual(intent, "timer")
        self.assertEqual(slots, {"n": 5, "unit": "minutes"})
        self.assertIn("5", reply)

    def test_note_slot(self):
        intent, slots, reply = self.nlu.handle(
            "note buy coffee beans".split(), "en")
        self.assertEqual(intent, "note")
        self.assertEqual(slots["text"], "Buy coffee beans.")

    def test_time_and_weather(self):
        self.assertEqual(self.nlu.handle("what time is it".split(), "en")[0],
                         "time")
        self.assertEqual(self.nlu.handle("how is the weather".split(), "en")[0],
                         "weather")

    def test_fallback_echoes(self):
        intent, slots, reply = self.nlu.handle(
            "tell me a joke".split(), "en", "Tell me a joke")
        self.assertEqual(intent, "fallback")
        self.assertIn("Tell me a joke", reply)


class TestIndic(unittest.TestCase):
    def setUp(self):
        self.nlu = IntentEngine()

    def test_hindi_time(self):
        intent, slots, reply = self.nlu.handle("अभी समय क्या हुआ".split(), "hi")
        self.assertEqual(intent, "time")
        self.assertTrue(reply.startswith("अभी समय"))

    def test_hindi_timer(self):
        intent, slots, reply = self.nlu.handle(
            "पाँच मिनट का टाइमर लगाओ".split(), "hi")
        self.assertEqual(intent, "timer")
        self.assertEqual(slots["n"], 5)
        self.assertEqual(slots["unit"], "minutes")

    def test_hindi_note(self):
        intent, slots, reply = self.nlu.handle(
            "नोट दूध खरीदना है".split(), "hi")
        self.assertEqual(intent, "note")
        self.assertIn("दूध", reply)

    def test_bengali_time(self):
        intent, slots, reply = self.nlu.handle("এখন কয়টা বাজে".split(), "bn")
        self.assertEqual(intent, "time")

    def test_bengali_timer(self):
        intent, slots, reply = self.nlu.handle(
            "পাঁচ মিনিটের টাইমার দাও".split(), "bn")
        self.assertEqual(intent, "timer")
        self.assertEqual(slots["n"], 5)

    def test_spanish_greeting(self):
        intent, _, reply = self.nlu.handle("hola buenas tardes".split(), "es")
        self.assertEqual(intent, "greet")
        self.assertTrue(reply.startswith("Hola"))


if __name__ == "__main__":
    unittest.main()
