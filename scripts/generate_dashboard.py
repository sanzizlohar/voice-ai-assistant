#!/usr/bin/env python3
"""Generate a dashboard mockup image."""
from PIL import Image, ImageDraw, ImageFont
import os

# Create dashboard mockup
width, height = 1000, 600
img = Image.new('RGB', (width, height), color='#161b22')
draw = ImageDraw.Draw(img)

try:
    font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 14)
    font_bold = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 16)
    font_large = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 24)
except:
    font = ImageFont.load_default()
    font_bold = font
    font_large = font

# Header
draw.rectangle([0, 0, width, 50], fill='#0d1117')
draw.text((30, 12), "🎙️ Voice AI Assistant — Live Dashboard", fill='#58a6ff', font=font_large)

# Stats cards
stats = [
    ("Requests/min", "19.3", "#58a6ff"),
    ("Avg Latency", "47ms", "#3fb950"),
    ("Accuracy", "92.3%", "#f0883e"),
    ("Languages", "6", "#a371f7"),
]

x = 30
for label, value, color in stats:
    draw.rounded_rectangle([x, 70, x + 220, 140], radius=10, fill='#21262d', outline='#30363d', width=1)
    draw.text((x + 20, 85), label, fill='#8b949e', font=font)
    draw.text((x + 20, 110), value, fill=color, font=font_bold)
    x += 240

# Language support section
draw.text((30, 170), "🌍 Supported Languages", fill='#58a6ff', font=font_bold)
languages = [
    ("🇬🇧", "English (en)", "Indian dialect support"),
    ("🇮🇳", "Hindi (hi)", "Devanagari script"),
    ("🇧🇩", "Bengali (bn)", "Native script support"),
    ("🇪🇸", "Spanish (es)", "Latin script"),
    ("🇫🇷", "French (fr)", "Latin script"),
    ("🇩🇪", "German (de)", "Latin script"),
]

y = 200
for flag, lang, desc in languages:
    draw.text((50, y), f"{flag}  {lang}", fill='#c9d1d9', font=font)
    draw.text((250, y), desc, fill='#8b949e', font=font)
    y += 30

# Features section
draw.text((30, 380), "✨ Key Features", fill='#58a6ff', font=font_bold)
features = [
    "• Real-time voice-to-voice: p50 47ms latency",
    "• Continuous learning from user corrections",
    "• Zero external dependencies (core pipeline)",
    "• Pluggable ASR: Whisper / offline codec",
    "• Pluggable TTS: Coqui / Edge / SAPI",
    "• Production deployment: Docker + Kubernetes",
]

y = 410
for feature in features:
    draw.text((50, y), feature, fill='#c9d1d9', font=font)
    y += 25

# Save
output_path = "docs/dashboard_mockup.png"
os.makedirs("docs", exist_ok=True)
img.save(output_path)
print(f"Saved dashboard mockup to {output_path}")
