"""Coded-speech tone codec: text ↔ audible tone sequences.

The offline engine needs real audio in and real audio out without shipping
a 2 GB speech model, so this module turns words into short sinusoidal
"melodies" (2-4 tones per word from an 8-frequency scale) and decodes them
back with Goertzel filtering. It is a *test double for acoustic models*:
the pipeline (VAD → ASR → adaptation → NLU → TTS) exercises the exact same
code paths the real Whisper/Coqui engines use, with deterministic, seeded
misrecognitions standing in for acoustic-model errors.

Frequencies are spaced ≥ ~30 Hz apart, which 30 ms Goertzel frames resolve
cleanly at 16 kHz even at ~28 dB SNR.
"""
from __future__ import annotations

import array
import hashlib
import math

try:  # optional: vectorized analysis + GIL release under load
    import numpy as _np
except ImportError:  # pragma: no cover
    _np = None

SR = 16_000
FREQS = (196.00, 233.08, 261.63, 293.66, 329.63, 392.00, 440.00, 523.25)
TONES_MIN, TONES_MAX = 2, 4

TONE_MS = 130       # duration of one tone burst
TONE_GAP_MS = 35    # intra-word gap between bursts
WORD_GAP_MS = 90    # gap between words
AMP = 0.55          # tone amplitude

WIN = 480           # analysis window: 30 ms @ 16 kHz
HOP = 160           # analysis hop: 10 ms @ 16 kHz
DOMINANCE = 1.25    # top/second Goertzel power needed to call a tone
MIN_RUN_FRAMES = 5  # a tone must hold ≥ 50 ms
WORD_BREAK_FRAMES = 6  # > 35 ms intra-word gap, < 90 ms inter-word gap

UNK = "<unk>"


def word_tones(word: str, attempt: int = 0) -> tuple[int, ...]:
    """Deterministic tone fingerprint for a word (sha256-based).

    ``attempt`` re-salts the hash — the codec uses it to step past codes
    that collide or contain two adjacent identical tones.
    """
    h = hashlib.sha256(f"{word}#{attempt}".encode("utf-8")).digest()
    n = TONES_MIN + (h[0] % (TONES_MAX - TONES_MIN + 1))
    return tuple(h[i] % len(FREQS) for i in range(1, n + 1))


class Codec:
    """Bidirectional word ↔ tone-sequence map for one vocabulary.

    Codes that collide with an earlier word or contain adjacent identical
    tones (they would render as one merged burst) are re-salted until
    clean and unique. The vocabulary is sorted first, so codes are
    reproducible across processes — learned rules stay valid.
    """

    def __init__(self, vocab):
        self.vocab = sorted({w for w in vocab if w})
        self._tones: dict[str, tuple[int, ...]] = {}
        self._words: dict[tuple[int, ...], str] = {}
        for word in self.vocab:
            attempt = 0
            code = word_tones(word)
            while (self._words.get(code, word) != word
                   or any(code[i] == code[i + 1]
                          for i in range(len(code) - 1))):
                attempt += 1
                code = word_tones(word, attempt)
            self._tones[word] = code
            self._words[code] = word

    def tones_of(self, word: str) -> tuple[int, ...] | None:
        return self._tones.get(word)

    def word_of(self, tones: tuple[int, ...]) -> str | None:
        """Exact code lookup, else the nearest vocab code within one
        corrupted tone — that nearest-match is what produces natural,
        systematic "mishearings" for the learning loop to fix."""
        w = self._words.get(tuple(tones))
        if w is not None:
            return w
        best, best_d = None, 2
        for code, cand in self._words.items():
            if abs(len(code) - len(tones)) > 1:
                continue
            d = _edit_distance(tones, code)
            if d < best_d:
                best, best_d = cand, d
        return best

    def word_of_exact(self, tones: tuple[int, ...]) -> tuple[str | None, bool]:
        """(word, exact) — exact code hits beat nearest matches."""
        w = self._words.get(tuple(tones))
        if w is not None:
            return w, True
        return self.word_of(tones), False

    # ---------------------------------------------------------------- #
    # Synthesis (text → float samples)
    # ---------------------------------------------------------------- #
    def render_words(self, words: list[str]) -> list[float]:
        out: list[float] = []
        for i, w in enumerate(words):
            tones = self._tones.get(w)
            if tones is None:
                continue
            for j, t in enumerate(tones):
                out.extend(_tone_burst(FREQS[t]))
                if j < len(tones) - 1:
                    out.extend(_silence(TONE_GAP_MS))
            out.extend(_silence(WORD_GAP_MS if i < len(words) - 1 else 120))
        return out

    def transcribe_groups(self, groups: list[list[int]]):
        """(words, exact_flags) per tone group."""
        words, exact = [], []
        for g in groups:
            w, is_exact = self.word_of_exact(tuple(g))
            words.append(w or UNK)
            exact.append(is_exact)
        return words, exact


def _tone_burst(freq: float) -> list[float]:
    n = SR * TONE_MS // 1000
    fade = SR * 12 // 1000
    out = []
    for i in range(n):
        if i < fade:
            env = 0.5 - 0.5 * math.cos(math.pi * i / fade)
        elif i > n - fade:
            env = 0.5 - 0.5 * math.cos(math.pi * (n - i) / fade)
        else:
            env = 1.0
        out.append(AMP * env * math.sin(2 * math.pi * freq * i / SR))
    return out


def _silence(ms: int) -> list[float]:
    return [0.0] * (SR * ms // 1000)


def _edit_distance(a, b) -> int:
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def goertzel_power(frame, freq: float, sr: int = SR) -> float:
    """Squared magnitude of ``freq`` in one frame (classic Goertzel)."""
    k = 2.0 * math.cos(2.0 * math.pi * freq / sr)
    s1 = s2 = 0.0
    for x in frame:
        s0 = x + k * s1 - s2
        s2, s1 = s1, s0
    return s1 * s1 + s2 * s2 - k * s1 * s2


def extract_tone_groups(pcm) -> tuple[list[list[int]], list[float]]:
    """Frame the audio and return (word-level tone groups, confidences).

    A frame votes for a frequency when its spectral power dominates the
    runner-up by :data:`DOMINANCE`; equal-index votes separated by ≤2
    quiet frames form one tone run; runs split by > :data:`WORD_BREAK_FRAMES`
    of silence land in different words. Uses a vectorized numpy kernel
    when available, else the pure-Python Goertzel filter bank.
    """
    n_frames = max(0, (len(pcm) - WIN) // HOP + 1)
    if n_frames <= 0:
        return [], []
    if _np is not None:
        votes = _votes_numpy(pcm, n_frames)
    else:
        votes = _votes_pure(pcm, n_frames)
    return _collapse(votes)


def _votes_numpy(pcm, n_frames: int) -> list[int]:
    x = _np.frombuffer(bytes(pcm), dtype=_np.int16).astype(_np.float64) / 32768.0
    frames = _np.lib.stride_tricks.sliding_window_view(x, WIN)[::HOP][:n_frames]
    rms = _np.sqrt((frames * frames).mean(axis=1))
    peak = float(rms.max()) if len(rms) else 0.0
    if peak < 1e-4:
        return [-1] * n_frames
    gate = 0.06 * peak
    active = rms > gate

    idx = _np.arange(WIN)
    freqs = _np.asarray(FREQS)
    cos_t = _np.cos(2.0 * _np.pi * freqs[:, None] * idx[None, :] / SR)
    sin_t = _np.sin(2.0 * _np.pi * freqs[:, None] * idx[None, :] / SR)
    sel = frames[active]
    re = sel @ cos_t.T
    im = sel @ sin_t.T
    pw = re * re + im * im  # single-bin DFT power — same result as Goertzel

    top = pw.argmax(axis=1)
    second = _np.partition(pw, -2, axis=1)[:, -2]
    dom = pw[_np.arange(len(pw)), top] / _np.maximum(second, 1e-12)
    good = dom > DOMINANCE

    votes = [-1] * n_frames
    frame_ids = _np.nonzero(active)[0]
    for f, t in zip(frame_ids[good].tolist(), top[good].tolist()):
        votes[f] = t
    return votes


def _votes_pure(pcm, n_frames: int) -> list[int]:
    norm = [x / 32768.0 for x in pcm]
    rms = []
    for f in range(n_frames):
        frame = norm[f * HOP: f * HOP + WIN]
        rms.append(math.sqrt(sum(x * x for x in frame) / WIN))
    peak = max(rms) or 1.0
    gate = 0.06 * peak
    votes = []
    for f in range(n_frames):
        idx = -1
        if rms[f] > gate:
            seg = norm[f * HOP: f * HOP + WIN]
            p = [goertzel_power(seg, fr) for fr in FREQS]
            top = max(range(len(FREQS)), key=p.__getitem__)
            rest = max(v for i, v in enumerate(p) if i != top) or 1e-12
            if p[top] / rest > DOMINANCE:
                idx = top
        votes.append(idx)
    return votes


def _collapse(votes: list[int]) -> tuple[list[list[int]], list[float]]:
    """votes → tone runs → words (shared by both kernels)."""
    n_frames = len(votes)
    runs: list[tuple[int, int, int]] = []  # (freq_idx, first, last)
    i = 0
    while i < n_frames:
        if votes[i] < 0:
            i += 1
            continue
        idx, last = votes[i], i
        k = i + 1
        while k < n_frames:
            if votes[k] == idx:
                last = k
                k += 1
            elif votes[k] == -1 and k - last <= 2:
                k += 1
            else:
                break
        if last - i + 1 >= MIN_RUN_FRAMES:
            runs.append((idx, i, last))
        i = max(k, i + 1)

    groups: list[list[int]] = []
    lens: list[int] = []
    cur: list[int] = []
    cur_len = 0
    prev_end = -100
    for idx, first, last in runs:
        if cur and first - prev_end > WORD_BREAK_FRAMES:
            groups.append(cur)
            lens.append(cur_len)
            cur, cur_len = [], 0
        cur.append(idx)
        cur_len += last - first + 1
        prev_end = last
    if cur:
        groups.append(cur)
        lens.append(cur_len)

    confs = [min(1.0, ln / max(1, len(g)) / (TONE_MS / 1000 * SR / HOP))
             for g, ln in zip(groups, lens)]
    return groups, confs
