"""Hotword / vocabulary boosting from user corrections.

Words the user teaches that are *outside* the engine vocabulary (names,
jargon, slang) are kept as weighted hotwords. Recognition output within a
small edit distance of a hotword gets rewritten to it, and — for real
Whisper engines — the terms feed ``initial_prompt`` so the acoustic model
itself is biased before decoding even starts.
"""
from __future__ import annotations

STOPWORDS = {
    "a", "an", "and", "the", "to", "of", "for", "is", "it", "in", "on",
    "at", "i", "you", "me", "my", "we", "he", "she", "they", "this",
    "that", "what", "how", "can", "do", "does", "set", "ask", "ask",
}


class HotwordSet:
    def __init__(self, cap: int = 256, min_weight: float = 1.5):
        self.cap = cap
        self.min_weight = min_weight
        self.terms: dict[str, dict[str, float]] = {}  # lang -> term -> weight

    # ---------------------------------------------------------------- #
    def observe_correction(self, lang: str, tokens: list[str],
                           vocab: set) -> int:
        """Add correction tokens that look like user vocabulary (not in the
        engine vocab, not stopword noise). Returns terms added/boosted."""
        touched = 0
        bucket = self.terms.setdefault(lang, {})
        for t in tokens:
            if len(t) < 2 or t in vocab or t in STOPWORDS or t.isdigit():
                continue
            bucket[t] = bucket.get(t, 0.0) + 1.0
            touched += 1
        # evict least-weighted when over capacity
        if len(bucket) > self.cap:
            for term in sorted(bucket, key=bucket.get)[: len(bucket) - self.cap]:
                del bucket[term]
        return touched

    def boost(self, lang: str, term: str, weight: float = 1.0) -> None:
        bucket = self.terms.setdefault(lang, {})
        bucket[term] = bucket.get(term, 0.0) + weight

    # ---------------------------------------------------------------- #
    def apply(self, tokens: list[str], lang: str) -> tuple[list[str], list]:
        """Fuzzy-rewrite tokens toward hotwords (edit distance ≤ max(1,
        len//5)); returns (tokens, fired rules)."""
        bucket = {t: w for t, w in self.terms.get(lang, {}).items()
                  if w >= self.min_weight}
        if not bucket:
            return tokens, []
        out, fired = [], []
        for t in tokens:
            if t in bucket or t.isdigit() or len(t) < 2:
                out.append(t)
                continue
            limit = max(1, len(t) // 5)
            best, best_d = t, limit + 1
            for term in bucket:
                d = _distance(t, term, limit)
                if d is not None and d < best_d:
                    best, best_d = term, d
            if best != t:
                fired.append((t, best, best_d))
            out.append(best)
        return out, fired

    def terms_for(self, lang: str) -> list[str]:
        bucket = self.terms.get(lang.split("-")[0], {})
        ranked = sorted(bucket, key=bucket.get, reverse=True)
        return ranked[:32]

    def snapshot(self) -> dict:
        return {"langs": {l: len(b) for l, b in self.terms.items()},
                "total": sum(len(b) for b in self.terms.values())}


def _distance(a: str, b: str, limit: int) -> int | None:
    """Banded Levenshtein; None once the distance provably exceeds limit."""
    if abs(len(a) - len(b)) > limit:
        return None
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        row_min = i
        for j, cb in enumerate(b, 1):
            v = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            cur.append(v)
            row_min = min(row_min, v)
        if row_min > limit:
            return None
        prev = cur
    return prev[-1] if prev[-1] <= limit else None
