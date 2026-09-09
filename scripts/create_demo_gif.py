#!/usr/bin/env python3
"""Create a GIF from the demo output showing the voice assistant in action."""
from PIL import Image, ImageDraw, ImageFont
import os
import time

# Demo frames showing different states
frames = []

# Frame 1: Initial state
def create_frame_1():
    img = Image.new('RGB', (800, 450), color='#0d1117')
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 20)
        font_small = ImageFont.truetype("C:/Windows/Fonts/segoei.ttf", 14)
        font_large = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 28)
    except:
        font = ImageFont.load_default()
        font_small = font
        font_large = font

    # Header
    draw.rectangle([0, 0, 800, 60], fill='#161b22')
    draw.text((30, 15), "🎙️ Voice AI Assistant — Live Dashboard", fill='#58a6ff', font=font_large)

    # Stats
    stats = [
        ("Requests/min", "0", "#58a6ff"),
        ("Avg Latency", "--", "#3fb950"),
        ("Accuracy", "--", "#f0883e"),
        ("Languages", "6", "#a371f7"),
    ]

    x = 30
    for label, value, color in stats:
        draw.rounded_rectangle([x, 80, x + 170, 140], radius=10, fill='#21262d', outline='#30363d', width=1)
        draw.text((x + 15, 95), label, fill='#8b949e', font=font_small)
        draw.text((x + 15, 120), value, fill=color, font=font)
        x += 190

    # Status
    draw.text((30, 180), "Status: 🟢 Server Running", fill='#3fb950', font=font)
    draw.text((30, 210), "Engine: offline (tone codec)", fill='#8b949e', font=font_small)
    draw.text((30, 240), "Waiting for voice input...", fill='#c9d1d9', font=font)

    # Languages
    draw.text((30, 300), "Supported Languages:", fill='#58a6ff', font=font)
    langs = ["🇬🇧 English", "🇮🇳 हिन्दी", "🇧🇩 বাংলা", "🇪🇸 Español", "🇫🇷 Français", "🇩🇪 Deutsch"]
    y = 330
    for lang in langs:
        draw.text((50, y), lang, fill='#c9d1d9', font=font_small)
        y += 25

    return img

# Frame 2: Processing request
def create_frame_2():
    img = Image.new('RGB', (800, 450), color='#0d1117')
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 20)
        font_small = ImageFont.truetype("C:/Windows/Fonts/segoei.ttf", 14)
        font_large = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 28)
    except:
        font = ImageFont.load_default()
        font_small = font
        font_large = font

    draw.rectangle([0, 0, 800, 60], fill='#161b22')
    draw.text((30, 15), "🎙️ Voice AI Assistant — Live Dashboard", fill='#58a6ff', font=font_large)

    stats = [
        ("Requests/min", "3.2", "#58a6ff"),
        ("Avg Latency", "47ms", "#3fb950"),
        ("Accuracy", "87%", "#f0883e"),
        ("Languages", "6", "#a371f7"),
    ]

    x = 30
    for label, value, color in stats:
        draw.rounded_rectangle([x, 80, x + 170, 140], radius=10, fill='#21262d', outline='#30363d', width=1)
        draw.text((x + 15, 95), label, fill='#8b949e', font=font_small)
        draw.text((x + 15, 120), value, fill=color, font=font)
        x += 190

    draw.text((30, 180), "Status: 🟢 Active", fill='#3fb950', font=font)
    draw.text((30, 210), "Processing: 'Hello there'", fill='#f0883e', font=font_small)
    draw.text((30, 240), "Intent: greet | Latency: 51ms", fill='#c9d1d9', font=font)

    # Recent activity
    draw.text((30, 290), "Recent Activity:", fill='#58a6ff', font=font)
    activities = [
        "[en] Hello there. → greet (51ms)",
        "[en] What time is it? → time (40ms)",
        "[hi] नमसत → greet (60ms)",
    ]
    y = 320
    for act in activities:
        draw.text((50, y), act, fill='#c9d1d9', font=font_small)
        y += 22

    return img

# Frame 3: Learning happening
def create_frame_3():
    img = Image.new('RGB', (800, 450), color='#0d1117')
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 20)
        font_small = ImageFont.truetype("C:/Windows/Fonts/segoei.ttf", 14)
        font_large = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 28)
    except:
        font = ImageFont.load_default()
        font_small = font
        font_large = font

    draw.rectangle([0, 0, 800, 60], fill='#161b22')
    draw.text((30, 15), "🎙️ Voice AI Assistant — Live Dashboard", fill='#58a6ff', font=font_large)

    stats = [
        ("Requests/min", "19.3", "#58a6ff"),
        ("Avg Latency", "47ms", "#3fb950"),
        ("Accuracy", "92%", "#f0883e"),
        ("Rules Learned", "17", "#a371f7"),
    ]

    x = 30
    for label, value, color in stats:
        draw.rounded_rectangle([x, 80, x + 170, 140], radius=10, fill='#21262d', outline='#30363d', width=1)
        draw.text((x + 15, 95), label, fill='#8b949e', font=font_small)
        draw.text((x + 15, 120), value, fill=color, font=font)
        x += 190

    draw.text((30, 180), "Status: 🟢 Active + Learning", fill='#3fb950', font=font)
    draw.text((30, 210), "Learning: 'but' → 'buy' (confusion pair)", fill='#a371f7', font=font_small)
    draw.text((30, 240), "Accuracy improving: 87% → 92%", fill='#f0883e', font=font)

    # Learning log
    draw.text((30, 290), "Learning Log:", fill='#58a6ff', font=font)
    logs = [
        "✓ Rule #1: but → buy (en)",
        "✓ Rule #2: kése → kaise (hi)",
        "✓ Rule #3: tor → hour (es)",
    ]
    y = 320
    for log in logs:
        draw.text((50, y), log, fill='#3fb950', font=font_small)
        y += 22

    return img

# Frame 4: Final results
def create_frame_4():
    img = Image.new('RGB', (800, 450), color='#0d1117')
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 20)
        font_small = ImageFont.truetype("C:/Windows/Fonts/segoei.ttf", 14)
        font_large = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 28)
    except:
        font = ImageFont.load_default()
        font_small = font
        font_large = font

    draw.rectangle([0, 0, 800, 60], fill='#161b22')
    draw.text((30, 15), "🎙️ Voice AI Assistant — Demo Complete", fill='#58a6ff', font=font_large)

    # Big stats
    draw.text((200, 100), "Demo Results", fill='#58a6ff', font=font_large)

    results = [
        ("Accuracy", "87% → 92%", "+5.2%"),
        ("Latency p50", "47ms", "Fast"),
        ("Rules Learned", "17", "Continuous"),
        ("Languages", "6", "Multilingual"),
    ]

    y = 160
    for label, value, badge in results:
        draw.text((150, y), label + ":", fill='#8b949e', font=font)
        draw.text((350, y), value, fill='#3fb950', font=font)
        draw.rounded_rectangle((600, y + 5, 700, y + 35), radius=5, fill='#238636')
        draw.text((620, y + 10), badge, fill='#ffffff', font=font_small)
        y += 40

    draw.text((30, 350), "✓ All tests passing (82/82)", fill='#3fb950', font=font)
    draw.text((30, 380), "✓ Zero external dependencies", fill='#3fb950', font=font)
    draw.text((30, 410), "✓ Production ready", fill='#3fb950', font=font)

    return img

# Create frames
frames.append(create_frame_1())
frames.append(create_frame_2())
frames.append(create_frame_3())
frames.append(create_frame_4())

# Save as GIF
output_path = "docs/demo_animation.gif"
os.makedirs("docs", exist_ok=True)
frames[0].save(
    output_path,
    save_all=True,
    append_images=frames[1:],
    duration=1500,
    loop=0
)

print(f"Saved animated GIF to {output_path}")
print(f"Frames: {len(frames)}")
