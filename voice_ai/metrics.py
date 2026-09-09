"""Thread-safe metrics registry and bounded event log.

The HTTP dashboard reads from its own thread while worker threads write,
so every structure is guarded by a lock. Also renders a Prometheus text
exposition from the same snapshot.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class EventLog:
    """Bounded ring buffer of structured operational events."""

    def __init__(self, maxlen: int = 500):
        self._items: deque = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def add(self, level: str, stage: str, event: str, detail: str = "",
            **extra) -> None:
        entry = {"ts": time.time(), "level": level, "stage": stage,
                 "event": event, "detail": detail}
        entry.update(extra)
        with self._lock:
            self._items.append(entry)

    def recent(self, n: int = 25) -> list:
        with self._lock:
            items = list(self._items)
        return items[-n:]


class Metrics:
    """Counters, gauges and approximate histograms (bounded samples)."""

    def __init__(self, hist_samples: int = 4096):
        self._lock = threading.RLock()
        self._counters: dict = defaultdict(float)
        self._gauges: dict = {}
        self._hist: dict = defaultdict(lambda: deque(maxlen=hist_samples))

    def inc(self, name: str, value: float = 1) -> None:
        with self._lock:
            self._counters[name] += value

    def gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = float(value)

    def observe(self, name: str, value: float) -> None:
        with self._lock:
            self._hist[name].append(float(value))

    def snapshot(self) -> dict:
        with self._lock:
            counters = dict(self._counters)
            gauges = dict(self._gauges)
            hists = {}
            for key, dq in self._hist.items():
                vals = sorted(dq)
                if not vals:
                    hists[key] = {"count": 0}
                    continue

                def pct(q: float, vals=vals) -> float:
                    idx = min(len(vals) - 1,
                              int(round(q / 100.0 * (len(vals) - 1))))
                    return vals[idx]

                hists[key] = {
                    "count": len(vals),
                    "sum": sum(vals),
                    "min": vals[0],
                    "max": vals[-1],
                    "avg": sum(vals) / len(vals),
                    "p50": pct(50),
                    "p95": pct(95),
                }
        return {"counters": counters, "gauges": gauges,
                "histograms": hists, "ts": time.time()}


def prometheus_text(snapshot: dict, extra_gauges: dict | None = None) -> str:
    """Render a snapshot in the Prometheus text exposition format."""
    lines: list[str] = []

    def emit(name: str, kind: str, help_: str, value) -> None:
        safe = "".join(c if c.isalnum() or c == "_" else "_"
                       for c in name.replace(".", "_"))
        lines.append(f"# HELP {safe} {help_}")
        lines.append(f"# TYPE {safe} {kind}")
        lines.append(f"{safe} {value}")

    for name, val in sorted(snapshot["counters"].items()):
        emit(name, "counter", "cumulative counter", val)
    for name, val in sorted(snapshot["gauges"].items()):
        emit(name, "gauge", "current gauge", val)
    for name, h in sorted(snapshot["histograms"].items()):
        if h.get("count"):
            emit(f"{name}_p50_ms", "gauge", "p50 of observed values (ms)",
                 round(h["p50"], 3))
            emit(f"{name}_p95_ms", "gauge", "p95 of observed values (ms)",
                 round(h["p95"], 3))
            emit(f"{name}_avg_ms", "gauge", "mean of observed values (ms)",
                 round(h["avg"], 3))
    for name, val in sorted((extra_gauges or {}).items()):
        emit(name, "gauge", "application gauge", val)
    return "\n".join(lines) + "\n"
