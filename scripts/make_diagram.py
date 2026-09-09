#!/usr/bin/env python3
"""Render assets/architecture.png — VIA system diagram (Pillow)."""
from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

W, H = 1720, 1080
BG = "#0b0f14"
PANEL = "#121821"
EDGE = "#2a3648"
INK = "#e5eef7"
DIM = "#8aa0b4"
BLUE = "#60a5fa"
GREEN = "#34d399"
AMBER = "#fbbf24"
VIOLET = "#a78bfa"
CYAN = "#22d3ee"

F = "C:/Windows/Fonts/segoeui.ttf"
FB = "C:/Windows/Fonts/segoeuib.ttf"
INDIC = "C:/Windows/Fonts/Nirmala.ttf"  # Devanagari + Bengali on Windows
INDIC_B = "C:/Windows/Fonts/Nirmalab.ttf"
HAVE_INDIC = os.path.exists(INDIC)


def font(size, bold=False):
    return ImageFont.truetype(FB if bold else F, size)


def ifont(size, bold=False):
    if HAVE_INDIC:
        return ImageFont.truetype(INDIC_B if bold else INDIC, size)
    return font(size, bold)


def box(d, xy, title, lines, accent, title_font=None):
    x, y, w, h = xy
    d.rounded_rectangle((x, y, x + w, y + h), radius=14, fill=PANEL,
                        outline=EDGE, width=2)
    d.rounded_rectangle((x, y, x + 6, y + h), radius=3, fill=accent)
    d.text((x + 20, y + 12), title, font=title_font or font(18, True),
           fill=accent)
    ty = y + 50
    for kind, text in lines:
        d.text((x + 20, ty), text, font=font(15) if kind == "n" else
               ifont(15, kind == "i"), fill=INK)
        ty += 24
    return (x, y, x + w, y + h)


def arrow(d, p1, p2, color=DIM, lw=3):
    d.line((p1[0], p1[1], p2[0], p2[1]), fill=color, width=lw)
    if abs(p2[1] - p1[1]) >= abs(p2[0] - p1[0]):  # vertical
        s = 8 if p2[1] > p1[1] else -8
        d.polygon([(p2[0], p2[1]), (p2[0] - 6, p2[1] - s),
                   (p2[0] + 6, p2[1] - s)], fill=color)
    else:
        s = 9 if p2[0] > p1[0] else -9
        d.polygon([(p2[0], p2[1]), (p2[0] - s, p2[1] - 6),
                   (p2[0] - s, p2[1] + 6)], fill=color)


def main():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.text((40, 30), "VOICE AI ASSISTANT — ARCHITECTURE",
           font=font(28, True), fill=INK)
    d.text((40, 68), "real-time multi-language speech · continuous learning"
           " · production serving · stdlib core, optional Whisper/Coqui",
           font=font(16), fill=DIM)

    n_cols, gap = 5, 24
    pw = (W - 80 - gap * (n_cols - 1)) // n_cols
    xs = [40 + i * (pw + gap) for i in range(n_cols)]

    # ---- row 1: sources & serving ---------------------------------- #
    r1y, r1h = 130, 118
    spw = pw * 2 + gap
    box(d, (xs[0], r1y, spw, r1h), "SPEECH IN",
        [("n", "Browser mic (demo page) · WAV over HTTP"),
         ("n", "synthetic corpus (tests, benchmarks)")], CYAN)
    box(d, (xs[2], r1y, pw, r1h), "LANGUAGES",
        [("n", "en · en-GB · en-IN"), ("n", "es · fr · de"),
         ("n", "Hindi · Bengali (native)")], CYAN)
    box(d, (xs[3], r1y, pw, r1h), "HTTP API",
        [("n", "POST /transcribe · /tts"), ("n", "POST /feedback")], CYAN)
    box(d, (xs[4], r1y, pw, r1h), "LIVE DASHBOARD",
        [("n", "mic capture in browser"), ("n", "latency + learning")], CYAN)

    # ---- row 2: the pipeline ---------------------------------------- #
    r2y, r2h = 330, 210
    box(d, (xs[0], r2y, pw, r2h), "1 · VAD",
        [("n", "energy gate + hysteresis"), ("n", "gap bridging (rhythm)"),
         ("n", "trim leading/trailing"), ("n", "budget ≤ 15 ms")], GREEN)
    box(d, (xs[1], r2y, pw, r2h), "2 · ASR ENGINE",
        [("n", "offline tone codec double"), ("n", "or faster-whisper int8"),
         ("n", "language auto-detect"), ("n", "budget ≤ 400 ms")], BLUE)
    box(d, (xs[2], r2y, pw, r2h), "3 · ADAPTIVE",
        [("n", "confusion model repairs"), ("n", "systematic mishearings"),
         ("n", "hotword fuzzy rewrite"), ("n", "budget ≤ 10 ms")], VIOLET)
    box(d, (xs[3], r2y, pw, r2h), "4 · NLU INTENTS",
        [("n", "time · math · timer"), ("n", "notes · weather · help"),
         ("n", "multilingual templates"), ("n", "budget ≤ 5 ms")], AMBER)
    box(d, (xs[4], r2y, pw, r2h), "5 · REPLY + TTS",
        [("n", "response templates"), ("n", "offline codec / Coqui"),
         ("n", "LRU reply cache"), ("n", "budget ≤ 150 ms")], GREEN)

    for x in xs[:-1]:
        arrow(d, (x + pw, r2y + r2h // 2), (x + pw + gap, r2y + r2h // 2),
              GREEN)
    arrow(d, (xs[0] + spw // 2, r1y + r1h), (xs[0] + pw // 2, r2y), CYAN)
    d.text((xs[0] + spw // 2 + 12, r1y + r1h + 30), "16 kHz mono PCM",
           font=font(13), fill=DIM)

    # banner
    by = r2y + r2h + 22
    d.rounded_rectangle((xs[0], by, xs[4] + pw, by + 42), radius=10,
                        fill=PANEL, outline=EDGE, width=2)
    d.text((xs[0] + 18, by + 9),
           "voice-to-voice budget 500 ms — measured p50 47 ms · RTF 0.0096"
           " (~100x real time) · every stage timed",
           font=font(17, True), fill=GREEN)

    # ---- row 3: continuous learning --------------------------------- #
    r3y, r3h = by + 92, 150
    box(d, (xs[0], r3y, pw, r3h), "FEEDBACK LOOP",
        [("n", "user corrects transcript"), ("n", "WER alignment"),
         ("n", "→ confusion pairs")], VIOLET)
    box(d, (xs[1], r3y, pw, r3h), "LEARNERS",
        [("n", "ConfusionModel (time decay)"), ("n", "HotwordSet (fuzzy)"),
         ("n", "AccuracyTracker trend")], VIOLET)
    box(d, (xs[2], r3y, pw, r3h), "EFFECT",
        [("n", "auto-correct next time"), ("n", "Whisper initial_prompt"),
         ("n", "accuracy up, measured")], VIOLET)
    box(d, (xs[3], r3y, pw, r3h), "PERSISTENCE",
        [("n", "SQLite (WAL)"), ("n", "rules survive restarts"),
         ("n", "sessions · transcripts")], AMBER)
    box(d, (xs[4], r3y, pw, r3h), "OBSERVABILITY",
        [("n", "/metrics Prometheus"), ("n", "per-stage latencies"),
         ("n", "rolling accuracy")], AMBER)

    for x in xs[:3]:
        arrow(d, (x + pw, r3y + r3h // 2), (x + pw + gap, r3y + r3h // 2),
              VIOLET)
    arrow(d, (xs[2] + pw // 2, r3y), (xs[2] + pw // 2, r2y + r2h), VIOLET)
    d.text((xs[2] + pw // 2 + 10, r3y - 24), "rules applied",
           font=font(13), fill=VIOLET)
    arrow(d, (xs[0] + pw // 2 + 60, r3y), (xs[0] + pw // 2 + 60, by + 42),
          DIM)
    d.text((xs[0] + pw // 2 + 70, r3y - 24), "corrections", font=font(13),
           fill=DIM)

    # ---- row 4: deployment ------------------------------------------ #
    r4y = r3y + r3h + 30
    d.rounded_rectangle((xs[0], r4y, xs[4] + pw, r4y + 56), radius=12,
                        fill=PANEL, outline=EDGE, width=2)
    d.text((xs[0] + 20, r4y + 8), "DEPLOYMENT", font=font(16, True),
           fill=CYAN)
    d.text((xs[0] + 160, r4y + 9),
           "Docker + docker-compose (Prometheus included) · Kubernetes"
           " 3 replicas + HPA · /healthz probes · bounded worker queue"
           " (503 backpressure under overload)",
           font=font(15), fill=INK)

    d.text((40, H - 52),
           "offline tone codec = test double for acoustic models (real DSP"
           " in/out, zero model download) — swap in Whisper / Coqui with"
           " --engine whisper · 78 tests · Python 3.9+ stdlib",
           font=font(15), fill=DIM)

    img.save("assets/architecture.png")
    print("wrote assets/architecture.png")


if __name__ == "__main__":
    main()
