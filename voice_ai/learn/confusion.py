"""Confusion model: learns systematic mishearings from user corrections.

Every time a user fixes a transcript, the edit script between the
hypothesis and the correction feeds this model. When the same wrong word
keeps mapping to the same right word (count and confidence above
threshold), future transcripts get corrected automatically. Evidence
forgets *with time* (half-life), not with corrections — a burst of
feedback reinforces rules instead of erasing them.
"""
from __future__ import annotations

import time

from ..asr.wer import align

UNK = "<unk>"


class ConfusionModel:
    HALF_LIFE_S = 6 * 3600  # evidence halves every 6h of wall time

    def __init__(self, decay: float = 0.97, min_count: float = 2.0,
                 min_conf: float = 0.5):
        self.min_count = min_count
        self.min_conf = min_conf
        # (lang, wrong, right) -> weighted evidence
        self.counts: dict[tuple, float] = {}
        # (lang, wrong) -> total evidence for the wrong word
        self.totals: dict[tuple, float] = {}
        self._last_t = time.time()

    # ---------------------------------------------------------------- #
    def _forget(self) -> None:
        """Time-based exponential forgetting of all evidence."""
        now = time.time()
        factor = 0.5 ** ((now - self._last_t) / self.HALF_LIFE_S)
        self._last_t = now
        if factor < 0.999:
            for k in self.counts:
                self.counts[k] *= factor
            for k in self.totals:
                self.totals[k] *= factor

    def observe(self, lang: str, ref_tokens: list[str],
                hyp_tokens: list[str]) -> int:
        """Learn from one (correction, hypothesis) pair; returns the number
        of substitution observations taken."""
        self._forget()
        taken = 0
        for op, rw, hw in align(ref_tokens, hyp_tokens):
            if op != "sub" or not hw or not rw or hw == rw:
                continue
            ckey, tkey = (lang, hw, rw), (lang, hw)
            self.counts[ckey] = self.counts.get(ckey, 0.0) + 1.0
            self.totals[tkey] = self.totals.get(tkey, 0.0) + 1.0
            taken += 1
        return taken

    def apply(self, tokens: list[str], lang: str) -> tuple[list[str], list]:
        """Rewrite ``tokens`` using learned rules; returns (tokens, rules).

        A rule fires when its evidence ≥ ``min_count`` and its share of
        all evidence for the wrong word ≥ ``min_conf``. Only one rule per
        position — the strongest.
        """
        out: list[str] = []
        fired: list[tuple] = []
        for t in tokens:
            best, best_c = None, 0.0
            total = self.totals.get((lang, t), 0.0)
            if total >= self.min_count:
                for (l, wrong, right), c in self.counts.items():
                    if l == lang and wrong == t and c >= self.min_count:
                        conf = c / total
                        if conf >= self.min_conf and c > best_c:
                            best, best_c = right, c
            if best:
                out.append(best)
                fired.append((t, best, round(best_c / max(total, 1e-9), 2)))
            else:
                out.append(t)
        return out, fired

    # ---------------------------------------------------------------- #
    def rules(self, lang: str | None = None) -> list:
        """Learned rules sorted by evidence: (lang, wrong, right, count, conf)."""
        rows = []
        for (l, wrong, right), c in self.counts.items():
            if lang and l != lang:
                continue
            if c >= self.min_count:
                rows.append((l, wrong, right, round(c, 2),
                             round(c / max(self.totals.get((l, wrong), 1e-9), 1e-9), 2)))
        rows.sort(key=lambda r: -r[3])
        return rows

    def snapshot(self) -> dict:
        rows = self.rules()
        return {"rules": len(self.counts), "active": len(rows),
                "top": rows[:10]}
