"""SQLite store tests: persistence of transcripts, feedback, rules."""
import unittest

from voice_ai.persistence.store import Store


class TestStore(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")

    def test_utterance_roundtrip(self):
        self.store.insert_utterance({
            "id": "u000001", "session_id": "s1", "ts": 123.0, "lang": "en",
            "audio_ms": 2100.0, "hypothesis": "what time is it",
            "final": "what time is it", "intent": "time",
            "reply": "It is noon.", "wer": 0.0, "latency_ms": 120.5,
            "engine": "offline", "dialect": ""})
        row = self.store.get_utterance("u000001")
        self.assertEqual(row["intent"], "time")
        self.assertEqual(row["latency_ms"], 120.5)
        self.assertIsNone(self.store.get_utterance("nope"))

    def test_feedback_and_rules(self):
        self.store.insert_feedback("u1", "corrected text")
        self.assertTrue(self.store.feedback_seen("u1"))
        self.store.save_rules("confusion",
                              [("en", "but", "buy", 2.0, 1.0)])
        rows = self.store.load_rules("confusion")
        self.assertEqual(rows, [("en", "but", "buy", 2.0, 1.0)])

    def test_accuracy_rows_filter_labeled(self):
        self.store.insert_utterance({
            "id": "a", "lang": "en", "wer": 0.25, "ts": 1.0,
            "hypothesis": "x", "final": "y"})
        self.store.insert_utterance({
            "id": "b", "lang": "en", "wer": None, "ts": 2.0,
            "hypothesis": "x", "final": "x"})
        rows = self.store.accuracy_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][2], 0.25)

    def test_sessions_and_counts(self):
        self.store.upsert_session("s1", "hi", 3)
        self.store.upsert_session("s1", "hi", 4)
        self.store.insert_event("info", "pipeline", "utterance", "ok")
        counts = self.store.counts()
        self.assertEqual(counts["sessions"], 1)
        self.assertEqual(counts["events"], 1)
        self.assertEqual(len(self.store.recent_events(5)), 1)


if __name__ == "__main__":
    unittest.main()
