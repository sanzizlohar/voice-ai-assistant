"""Energy voice-activity detection: finds and trims speech segments.

Adaptive noise floor (20th percentile of frame RMS) with hysteresis
attack/release, 80 ms padding and — critically for natural rhythm —
gaps shorter than :data:`BRIDGE_MS` are *bridged, not cut*: word-internal
pauses survive while leading/trailing silence disappears. Overlapping
padded spans are merged so audio is never duplicated.
"""
from __future__ import annotations

import array
import math

FRAME_MS = 10
ATTACK_DB = 6.0    # open gate 6 dB above the noise floor
RELEASE_DB = 3.0   # stay open until within 3 dB of it
MIN_SPEECH_S = 0.12
PAD_MS = 80
BRIDGE_MS = 150    # gaps shorter than this are kept (word rhythm)


def frame_rms(pcm: array.array, sr: int) -> list[float]:
    n = max(1, sr * FRAME_MS // 1000)
    out = []
    for i in range(0, len(pcm), n):
        chunk = pcm[i:i + n]
        if chunk:
            acc = 0.0
            for s in chunk:
                acc += s * s
            out.append(math.sqrt(acc / len(chunk)) / 32768.0)
    return out


def detect_speech(pcm: array.array, sr: int) -> list[tuple[int, int]]:
    """Speech spans as merged (start_sample, end_sample) tuples."""
    rms = frame_rms(pcm, sr)
    if not rms:
        return []
    floor = sorted(rms)[max(0, len(rms) // 5)]  # ~20th percentile
    hi = floor * (10 ** (ATTACK_DB / 20.0)) + 1e-4
    lo = floor * (10 ** (RELEASE_DB / 20.0)) + 1e-4

    step = sr * FRAME_MS // 1000
    pad = PAD_MS // FRAME_MS
    min_frames = int(MIN_SPEECH_S * 1000 / FRAME_MS)

    raw: list[tuple[int, int]] = []
    open_at, cur_hi = None, False
    for i, r in enumerate(rms):
        if not cur_hi and r > hi:
            cur_hi, open_at = True, i
        elif cur_hi and r < lo:
            cur_hi = False
            if open_at is not None and i - open_at >= min_frames:
                raw.append((max(0, (open_at - pad) * step),
                            min(len(pcm), (i + pad) * step)))
            open_at = None
    if cur_hi and open_at is not None and len(rms) - open_at >= min_frames:
        raw.append((max(0, (open_at - pad) * step), len(pcm)))

    # merge overlaps and bridge short gaps (keeps intra-word pauses)
    bridge = BRIDGE_MS * sr // 1000
    merged: list[list[int]] = []
    for a, b in sorted(raw):
        if merged and a - merged[-1][1] <= bridge:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [(a, b) for a, b in merged]


def trim_silence(pcm: array.array, sr: int) -> tuple[array.array, float]:
    """Return (speech audio, speech_seconds) over detected spans."""
    spans = detect_speech(pcm, sr)
    if not spans:
        return array.array("h"), 0.0
    out = array.array("h")
    for a, b in spans:
        out.extend(pcm[a:b])
    return out, len(out) / sr
