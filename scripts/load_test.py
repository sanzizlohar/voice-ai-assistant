#!/usr/bin/env python3
"""Load test the running assistant: sustained RPS against /transcribe.

    python scripts/load_test.py --rps 20 --duration 30 --concurrency 8

Reports throughput, latency percentiles, error budget and the projected
daily capacity + simulated uptime — the numbers behind the README table.
"""
from __future__ import annotations

import argparse
import io
import json
import pathlib
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from voice_ai.audio.synth import Channel, Synthesizer  # noqa: E402
from voice_ai.audio.wavio import write_wav  # noqa: E402

PHRASES = [("en", "what time is it"), ("en", "note buy coffee beans"),
           ("es", "que hora es"), ("hi", "अभी समय क्या हुआ"),
           ("bn", "এখন কয়টা বাজে"), ("en", "how is the weather")]


def build_payloads(n: int) -> list[bytes]:
    syn = Synthesizer(Channel(error_rate=0.0, snr_db=26.0, seed=1))
    out = []
    for i in range(n):
        lang, phrase = PHRASES[i % len(PHRASES)]
        pcm, _ = syn.utterance(lang, phrase)
        buf = io.BytesIO()
        write_wav(buf, pcm, 16000)
        out.append(buf.getvalue())
    return out


class Worker(threading.Thread):
    def __init__(self, url: str, payloads: list[bytes], stop: threading.Event,
                 results: deque, pace: float | None):
        super().__init__(daemon=True)
        self.url, self.payloads, self.stop = url, payloads, stop
        self.results, self.pace = results, pace
        self.i = 0

    def run(self):
        session = f"load-{threading.get_ident()}"
        next_t = time.perf_counter()
        while not self.stop.is_set():
            if self.pace:
                next_t += 1.0 / self.pace
                delay = next_t - time.perf_counter()
                if delay > 0:
                    time.sleep(delay)
                elif delay < -0.5:  # fell behind: reset pace anchor
                    next_t = time.perf_counter()
            body = self.payloads[self.i % len(self.payloads)]
            self.i += 1
            t0 = time.perf_counter()
            ok = False
            try:
                req = urllib.request.Request(
                    f"{self.url}/transcribe?session={session}&audio=0",
                    data=body, method="POST",
                    headers={"Content-Type": "audio/wav"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    ok = resp.status == 200
                    json.loads(resp.read())
            except Exception:
                ok = False
            self.results.append((time.perf_counter() - t0, ok))


def percentile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = min(len(sorted_vals) - 1, int(round(q / 100 * (len(sorted_vals) - 1))))
    return sorted_vals[idx]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8080")
    ap.add_argument("--rps", type=float, default=20.0,
                    help="target requests/sec (0 = as fast as possible)")
    ap.add_argument("--duration", type=float, default=30.0)
    ap.add_argument("--concurrency", type=int, default=8)
    args = ap.parse_args()

    print(f" loading synthetic payloads…")
    payloads = build_payloads(args.concurrency * 2)
    stop = threading.Event()
    results: deque = deque()
    threads = [Worker(args.url, payloads, stop, results,
                      args.rps / args.concurrency if args.rps else None)
               for _ in range(args.concurrency)]

    print(f" load test → {args.url}  ·  {args.rps or '∞'} rps target"
          f"  ·  {args.concurrency} workers  ·  {args.duration:.0f}s")
    for t in threads:
        t.start()
    t0 = time.time()
    try:
        while time.time() - t0 < args.duration:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    stop.set()
    for t in threads:
        t.join(timeout=10)

    lat = sorted(d for d, ok in results if ok)
    ok = sum(1 for _, o in results if o)
    total = len(results)
    elapsed = time.time() - t0
    uptime = ok / total * 100 if total else 0.0
    print(" " + "─" * 62)
    print(f" requests      {total}   ok {ok}   errors {total - ok}")
    print(f" throughput    {total / elapsed:.1f} req/s sustained")
    if lat:
        print(f" latency ms    p50 {percentile(lat, 50) * 1000:.0f}"
              f"   p95 {percentile(lat, 95) * 1000:.0f}"
              f"   p99 {percentile(lat, 99) * 1000:.0f}"
              f"   max {lat[-1] * 1000:.0f}")
    print(f" uptime        {uptime:.2f}%  (ok/total during the run)")
    if args.rps:
        print(f" daily         ~{args.rps * 86400:,.0f} requests/day"
              f" at this rate")
    print(" " + "─" * 62)
    return 0 if total and uptime >= 99.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
