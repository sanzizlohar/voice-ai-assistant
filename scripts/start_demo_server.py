#!/usr/bin/env python3
"""Record a GIF demo of the Voice AI Assistant dashboard."""
import subprocess
import time
import os
import sys

# Start the server
print("Starting server...")
server_proc = subprocess.Popen(
    [sys.executable, "-m", "voice_ai.main", "serve", "--port", "8080"],
    cwd="D:/SOMU/voice-ai-assistant",
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE
)

time.sleep(3)  # Wait for server to start

# Check if server is running
try:
    import urllib.request
    response = urllib.request.urlopen("http://localhost:8080/healthz", timeout=2)
    print(f"Server started: {response.status}")
except Exception as e:
    print(f"Server error: {e}")
    server_proc.terminate()
    sys.exit(1)

print("Server is running. Open http://localhost:8080 in your browser.")
print("Take a screenshot or screen recording manually, then close this window.")
print("Press Ctrl+C to stop the server.")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nStopping server...")
    server_proc.terminate()
    print("Done!")
