#!/usr/bin/env python3
"""Render assets/usecases.png — "what can it do" card strip (Pillow).

Dark minimal style matching the product UI: deep-zinc canvas, hairline
card borders, single-accent dot markers, clean sans typography.
"""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

W, H = 1720, 760
BG = "#09090b"
PANEL = "#101014"
LINE = (255, 255, 255, 22)
INK = "#fafafa"
DIM = "#8f8f98"
DIM2 = "#6b6b74"

CARDS = [
    ("VOICE COMMANDS", "#fb7185",
     ["time · spoken math · timers", "notes — all hands-free",
      "answered out loud, instantly"]),
    ("SIX LANGUAGES", "#2dd4bf",
     ["English + en-IN dialect", "Hindi · Bengali (native script)",
      "es · fr · de — auto-detected"]),
    ("LEARNS FROM YOU", "#f59e0b",
     ["correct a mishearing once", "the fix fires automatically next time",
      "rules persist across restarts"]),
    ("EXTEND IT", "#8b5cf6",
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
    # soft violet glow top-center, matching the web UI
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((W // 2 - 500, -420, W // 2 + 500, 220),
               fill=(139, 92, 246, 46))
    from PIL import ImageFilter
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
    d = ImageDraw.Draw(img, "RGBA")

    d.text((60, 48), "WHAT CAN IT DO?", font=font(34, True), fill=INK)
    d.text((60, 96), "a mini Siri/Alexa you fully own — speak or type, "
           "it understands, acts and answers in your language",
           font=font(18), fill=DIM)

    cw, ch, gap = 380, 420, 30
    x0, y0 = 60, 170
    for i, (title, accent, lines) in enumerate(CARDS):
        x = x0 + i * (cw + gap)
        d.rounded_rectangle((x, y0, x + cw, y0 + ch), radius=20,
                            fill=PANEL, outline=LINE, width=2)
        d.rounded_rectangle((x + 22, y0 + 26, x + 84, y0 + 88), radius=14,
                            fill=accent)
        d.text((x + 42, y0 + 38), str(i + 1), font=font(28, True), fill="#0b0b0e")
        d.text((x + 104, y0 + 40), title, font=font(20, True), fill=INK)
        d.line((x + 24, y0 + 116, x + cw - 24, y0 + 116), fill=LINE, width=2)
        ty = y0 + 146
        for line in lines:
            d.ellipse((x + 28, ty + 8, x + 35, ty + 15), fill=accent)
            d.text((x + 48, ty), line, font=font(16), fill=DIM)
            ty += 48
        d.text((x + 24, y0 + ch - 52),
               ("speak:  \u201cwhat time is it\u201d",
                "speak:  Bangla · Hindi voice",
                "teach:  \u201ccoffe\u201d \u2192 \u201ccoffee\u201d",
                "intents.py \u2192 your API")[i],
               font=font(14, True), fill=DIM2)

    d.text((60, H - 58), "82 tests · 500 ms voice-to-voice budget · "
           "stdlib core · Whisper STT · neural voices · Docker/k8s",
           font=font(16, True), fill=DIM)
    img.save("assets/usecases.png")
    print("wrote assets/usecases.png")


if __name__ == "__main__":
    main()
