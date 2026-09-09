"""VAD unit tests: silence trimming, gap bridging, span merging."""
import array
import math
import unittest

from voice_ai.audio.vad import detect_speech, trim_silence

SR = 16000


def tone(freq, ms):
    n = SR * ms // 1000
    return array.array("h", (int(0.5 * 32767
                                 * math.sin(2 * math.pi * freq * i / SR))
                             for i in range(n)))


def silence(ms):
    return array.array("h", (0,) * (SR * ms // 1000))


class TestVad(unittest.TestCase):
    def test_trims_leading_and_trailing_silence(self):
        pcm = silence(1000) + tone(300, 500) + silence(1000)
        speech, seconds = trim_silence(pcm, SR)
        self.assertLess(len(speech), 0.7 * SR)
        self.assertGreater(seconds, 0.4)

    def test_bridges_short_gaps(self):
        # two bursts separated by a 100 ms gap (inside BRIDGE_MS=150)
        pcm = silence(800) + tone(300, 300) + silence(100) \
            + tone(400, 300) + silence(800)
        spans = detect_speech(pcm, SR)
        self.assertEqual(len(spans), 1, f"gap not bridged: {spans}")
        a, b = spans[0]
        self.assertGreaterEqual(b - a, 700 * SR // 1000)

    def test_cuts_long_gaps(self):
        pcm = silence(500) + tone(300, 300) + silence(600) \
            + tone(400, 300) + silence(500)
        spans = detect_speech(pcm, SR)
        self.assertEqual(len(spans), 2, f"long gap not cut: {spans}")

    def test_no_duplication_after_merge(self):
        pcm = silence(300) + tone(300, 200) + silence(60) + tone(400, 200)
        spans = detect_speech(pcm, SR)
        total = sum(b - a for a, b in spans)
        self.assertLessEqual(total, len(pcm))

    def test_all_silence_gives_no_spans(self):
        self.assertEqual(detect_speech(silence(1000), SR), [])
        speech, seconds = trim_silence(silence(500), SR)
        self.assertEqual(seconds, 0.0)


if __name__ == "__main__":
    unittest.main()
