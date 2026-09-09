"""Word error rate and alignment — the yardstick for recognition quality.

``align`` returns the edit script (equal/substitute/insert/delete) between
the reference and hypothesis token lists; the confusion miner consumes the
substitutions, the accuracy tracker consumes the counts.
"""
from __future__ import annotations


def levenshtein(a: list, b: list) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def align(ref: list[str], hyp: list[str]) -> list[tuple[str, str, str]]:
    """Edit script as (op, ref_word, hyp_word) tuples.

    ``ins`` has ref_word="", ``del`` has hyp_word="". Backtracks the same
    DP table :func:`levenshtein` computes (ties prefer substitutions).
    """
    n, m = len(ref), len(hyp)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1,
                           dp[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]))
    ops: list[tuple[str, str, str]] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]):
            op = "equal" if ref[i - 1] == hyp[j - 1] else "sub"
            ops.append((op, ref[i - 1], hyp[j - 1]))
            i, j = i - 1, j - 1
        elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            ops.append(("del", ref[i - 1], ""))
            i -= 1
        else:
            ops.append(("ins", "", hyp[j - 1]))
            j -= 1
    ops.reverse()
    return ops


def wer(ref: str | list[str], hyp: str | list[str]) -> float:
    """Word error rate in [0, ∞); 0.0 for an empty reference."""
    r = ref.split() if isinstance(ref, str) else list(ref)
    h = hyp.split() if isinstance(hyp, str) else list(hyp)
    if not r:
        return 0.0
    return levenshtein(r, h) / len(r)


def accuracy(ref: str | list[str], hyp: str | list[str]) -> float:
    """Recognition accuracy = 1 − WER, clipped to [0, 1] for display."""
    return max(0.0, 1.0 - wer(ref, hyp))


def confusion_pairs(ref: str | list[str],
                    hyp: str | list[str]) -> list[tuple[str, str]]:
    """(hyp_word, ref_word) substitution pairs from the edit script."""
    r = ref.split() if isinstance(ref, str) else list(ref)
    h = hyp.split() if isinstance(hyp, str) else list(hyp)
    return [(hw, rw) for op, rw, hw in align(r, h) if op == "sub"]
