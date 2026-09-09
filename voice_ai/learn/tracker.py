"""Rolling recognition-accuracy tracking with trend detection.

Only utterances with a known reference (benchmark runs, corrected
transcripts) update the tracker. The trend statistic compares the mean
accuracy of the older half of the window against the newer half — the
number the continuous-learning demo is judged by.
"""
from __future__ import annotations

import time
from collections import deque


class AccuracyTracker:
    def __init__(self, window: int = 500):
        self.window = window
        self._events: deque = deque(maxlen=window)  # (ts, lang, accuracy)

    def update(self, lang: str, accuracy: float) -> None:
        self._events.append((time.time(), lang, max(0.0, min(1.0, accuracy))))

    # ---------------------------------------------------------------- #
    def snapshot(self) -> dict:
        evs = list(self._events)
        if not evs:
            return {"n": 0, "accuracy": None, "trend_pp": 0.0, "by_lang": {},
                    "recent": []}
        accs = [a for _, _, a in evs]
        overall = sum(accs) / len(accs)
        half = len(accs) // 2
        old = accs[:half] or accs
        new = accs[half:] or accs
        trend_pp = (sum(new) / len(new) - sum(old) / len(old)) * 100.0

        by_lang: dict = {}
        for _, lang, a in evs:
            by_lang.setdefault(lang, []).append(a)
        by_lang = {l: round(sum(v) / len(v), 4) for l, v in by_lang.items()}

        return {
            "n": len(evs),
            "accuracy": round(overall, 4),
            "trend_pp": round(trend_pp, 2),
            "by_lang": by_lang,
            "recent": [round(a, 3) for _, _, a in list(evs)[-60:]],
        }
