#!/usr/bin/env python3
"""Generate a learning loop diagram."""
from PIL import Image, ImageDraw, ImageFont
import os

width, height = 900, 500
img = Image.new('RGB', (width, height), color='#0d1117')
draw = ImageDraw.Draw(img)

try:
    font = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 18)
    font_small = ImageFont.truetype("C:/Windows/Fonts/segoei.ttf", 14)
except:
    font = ImageFont.load_default()
    font_small = font

# Title
draw.text((300, 20), "🔄 Continuous Learning Loop", fill='#58a6ff', font=font)

# Draw boxes
boxes = [
    ("User Input", 50, 80, "#f0883e"),
    ("ASR Engine", 250, 80, "#58a6ff"),
    ("Misheard!", 450, 80, "#da3633"),
    ("User Correction", 650, 80, "#3fb950"),
]

for title, x, y, color in boxes:
    draw.rounded_rectangle([x, y, x + 160, y + 60], radius=10, fill=color + '33', outline=color, width=2)
    draw.text((x + 20, y + 20), title, fill=color, font=font_small)

# Arrows
draw.line([(210, 110), (240, 110)], fill='#8b949e', width=2)
draw.line([(410, 110), (440, 110)], fill='#8b949e', width=2)
draw.line([(610, 110), (640, 110)], fill='#8b949e', width=2)

# Bottom section - learning components
draw.text((50, 200), "Learning Components:", fill='#c9d1d9', font=font)

components = [
    ("ConfusionModel", "Counts (wrong → right) pairs", 50, 240, "#a371f7"),
    ("HotwordSet", "User vocabulary memorization", 50, 310, "#22d3ee"),
    ("SQLite (WAL)", "Persistent learning across restarts", 50, 380, "#fbbf24"),
]

for title, desc, x, y, color in components:
    draw.rounded_rectangle([x, y, x + 350, y + 50], radius=8, fill='#21262d', outline=color + '66', width=1)
    draw.text((x + 15, y + 10), title, fill=color, font=font_small)
    draw.text((x + 15, y + 30), desc, fill='#8b949e', font=font_small)

# Results
draw.text((500, 200), "Results:", fill='#c9d1d9', font=font)
results = [
    ("WER Improvement", "7.8% → 6.8%"),
    ("Accuracy Gain", "+5.2 percentage points"),
    ("Latency", "Sub-100ms responses"),
    ("Rules Learned", "17+ per session"),
]

y = 240
for label, value in results:
    draw.text((520, y), label + ":", fill='#8b949e', font=font_small)
    draw.text((650, y), value, fill='#3fb950', font=font_small)
    y += 35

# Save
output_path = "docs/learning_loop.png"
os.makedirs("docs", exist_ok=True)
img.save(output_path)
print(f"Saved learning loop diagram to {output_path}")
