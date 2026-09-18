#!/usr/bin/env python3
"""Capture assets/demo.gif (+ assets/hero.png) from the LIVE page.

Requires the assistant to be running (python -m voice_ai.main serve) and
Edge or Chrome. Each frame is a real headless-browser screenshot of
http://127.0.0.1:8080/?demo=<cmd>[&teach=<correction>] — the page
auto-runs the command through the full pipeline and renders the result
card. The last three frames tell the continuous-learning story live:
mishear → user teaches twice → the ✨ fix fires automatically.

Note: --virtual-time-budget breaks --screenshot in new headless; use
--timeout=<ms> instead.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

from PIL import Image

BASE = "http://127.0.0.1:8080"
WIDTH, HEIGHT = 820, 1480
FRAME_MS = 2600
ATTEMPTS = 3

FRAMES = [
    ("what time is it", None),
    ("what is twelve plus thirty", None),
    ("set a timer for five minutes", None),
    ("note buy milk tomorrow", None),
    ("এখন কয়টা বাজে", None),
    ("अभी समय क्या हुआ", None),
    ("note buy coffe beans", "note buy coffee beans"),   # teach #1
    ("note buy coffe beans", "note buy coffee beans"),   # teach #2
    ("note buy coffe beans", None),                      # ✨ fix fires
]


def find_browser() -> str:
    for exe in ("msedge.exe", "chrome.exe"):
        path = shutil.which(exe)
        if path:
            return path
    for path in (
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    ):
        if os.path.exists(path):
            return path
    raise SystemExit("no Edge/Chrome found for headless capture")


def wait_server(timeout: float = 20.0) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(f"{BASE}/healthz", timeout=2) as r:
                if r.status == 200:
                    return
        except Exception:
            time.sleep(0.5)
    raise SystemExit(f"server not reachable at {BASE} — start it first")


def shoot(browser: str, url: str, out_png: str) -> bool:
    """One frame, up to ATTEMPTS tries — Edge headless is flaky when
    instances launch back-to-back, so each attempt gets a fresh profile
    and we pause briefly between launches."""
    for attempt in range(ATTEMPTS):
        profile = tempfile.mkdtemp(prefix="via-edge-prof-")
        try:
            subprocess.run(
                [browser, "--headless=new", "--disable-gpu", "--no-first-run",
                 f"--user-data-dir={profile}", "--hide-scrollbars",
                 f"--window-size={WIDTH},{HEIGHT}", "--timeout=45000",
                 f"--screenshot={out_png}", url],
                capture_output=True, timeout=300, check=False)
            if os.path.exists(out_png) and os.path.getsize(out_png) > 10000:
                return True
        finally:
            shutil.rmtree(profile, ignore_errors=True)
        time.sleep(2.0)
    return False


def main() -> int:
    wait_server()
    browser = find_browser()
    out_dir = tempfile.mkdtemp(prefix="via-gif-")
    try:
        pngs = []
        for i, (cmd, teach) in enumerate(FRAMES):
            q = {"demo": cmd, "audio": "0"}  # no voice synth in captures
            if teach:
                q["teach"] = teach
            url = f"{BASE}/?" + urllib.parse.urlencode(q)
            shot = os.path.join(out_dir, f"frame{i}.png")
            if not shoot(browser, url, shot):
                print(f"  frame {i}: capture failed after {ATTEMPTS} tries")
                continue
            pngs.append(shot)
            time.sleep(1.5)  # let Edge fully exit before the next launch
            print(f"  frame {i + 1}/{len(FRAMES)}: {cmd[:34]!r}"
                  + ("  +teach" if teach else ""))
        if len(pngs) < 3:
            raise SystemExit("too few frames captured — is the server up?")

        if pngs[0]:
            shutil.copy(pngs[0], "assets/hero.png")  # full-res still
            print("wrote assets/hero.png")

        frames = []
        for p in pngs:
            img = Image.open(p).convert("RGB")
            img = img.resize((WIDTH // 2, HEIGHT // 2), Image.LANCZOS)
            frames.append(img.quantize(colors=192, method=Image.MEDIANCUT))
        os.makedirs("assets", exist_ok=True)
        frames[0].save("assets/demo.gif", save_all=True,
                       append_images=frames[1:], duration=FRAME_MS, loop=0,
                       optimize=True)
        print(f"wrote assets/demo.gif ({len(frames)} frames, "
              f"{os.path.getsize('assets/demo.gif') // 1024} KB)")
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
