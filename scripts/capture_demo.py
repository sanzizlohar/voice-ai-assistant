#!/usr/bin/env python3
"""Generate a demo GIF from the voice assistant output."""
import subprocess
import time
import os

# Run the demo and capture output
result = subprocess.run(
    ["python", "-m", "voice_ai.main", "demo"],
    capture_output=True,
    text=True,
    cwd="D:/SOMU/voice-ai-assistant"
)

# Save the output
with open("docs/demo_output.txt", "w", encoding="utf-8") as f:
    f.write(result.stdout)
    f.write(result.stderr)

print("Demo output saved to docs/demo_output.txt")
print(f"Lines captured: {len(result.stdout.splitlines())}")
