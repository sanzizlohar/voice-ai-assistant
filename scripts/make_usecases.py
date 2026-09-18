#!/usr/bin/env python3
"""Render assets/usecases.png — "what can it do" card strip (Pillow)."""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

W, H = 1720, 760
BG = "#fdf6e3"
PANEL = "#fffdf7"
INK = "#33322e"
DIM = "#6b675c"
DOT = (51, 50, 46, 20)

CARDS = [
    ("VOICE COMMANDS", "#ff5252",
     ["time · spoken math · timers", "notes — all hands-free",
      "answered out loud, instantly"]),
    ("SIX LANGUAGES", "#00b8a0",
     ["English + en-IN dialect", "Hindi · Bengali (native script)",
      "es · fr · de — auto-detected"]),
    ("LEARNS FROM YOU", "#f59e0b",
     ["correct a mishearing once", "the fix fires automatically next time",
      "rules persist across restarts"]),
    ("EXTEND IT", "#7c4dff",
     ["intents are keyword handlers", "wire them to smart-home, IVR,",
      "forms — pipeline already built"]),
]

F = "C:/Windows/Fonts/segoeui.ttf"
FB = "C:/Windows/Fonts/segoeuib.ttf"


def font(size, bold=False):
    return ImageFont.truetype(FB if bold else F, size)


def main():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img, "RGBA")
    for x in range(0, W, 24):
        for y in range(0, H, 24):
            d.ellipse((x, y, x + 2, y + 2), fill=DOT)

    d.text((60, 44), "WHAT CAN IT DO?", font=font(34, True), fill=INK)
    d.text((60, 90), "a mini Siri/Alexa you fully own — speak or type, "
           "it understands, acts and answers in your language",
           font=font(18), fill=DIM)

    cw, ch, gap = 380, 420, 30
    x0, y0 = 60, 160
    for i, (title, accent, lines) in enumerate(CARDS):
        x = x0 + i * (cw + gap)
        r = 26 if i % 2 else 18
        d.rounded_rectangle((x, y0, x + cw, y0 + ch), radius=r,
                            fill=PANEL, outline=INK, width=4)
        d.rounded_rectangle((x + 18, y0 + 24, x + 92, y0 + 98), radius=16,
                            fill=accent)
        d.text((x + 40, y0 + 40), str(i + 1), font=font(30, True), fill="#fffdf7")
        d.text((x + 110, y0 + 38), title, font=font(21, True), fill=INK)
        d.line((x + 24, y0 + 122, x + cw - 24, y0 + 122), fill="#e8e0cc",
               width=2)
        ty = y0 + 150
        for line in lines:
            d.ellipse((x + 28, ty + 8, x + 36, ty + 16), fill=accent)
            d.text((x + 48, ty), line, font=font(16), fill=INK)
            ty += 46
        d.text((x + 24, y0 + ch - 52),
               ("speak:  \u201cwhat time is it\u201d",
                "speak:  \u201cএখন কয়টা বাজে\u201d".replace("এখন কয়টা বাজে", "Bangla · Hindi voice"),
                "teach:  \u201ccoffe\u201d \u2192 \u201ccoffee\u201d",
                "intents.py \u2192 your API")[i],
               font=font(14, True), fill=DIM)

    d.text((60, H - 58), "78+ tests · 500 ms voice-to-voice budget · "
           "stdlib core · Whisper STT · neural voices · Docker/k8s",
           font=font(16, True), fill=DIM)
    img.save("assets/usecases.png")
    print("wrote assets/usecases.png")


if __name__ == "__main__":
    main()
