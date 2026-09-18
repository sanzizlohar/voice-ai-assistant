"""Production HTTP API for the voice assistant (stdlib ThreadingHTTPServer).

Endpoints:
    POST /transcribe   audio/wav body (or JSON {audio_b64}) → JSON result
                       query: ?session=&lang=&audio=1 (attach reply WAV)
    POST /tts          {text, lang} → audio/wav
    POST /feedback     {utterance_id, text} → learning summary
    GET  /api/state    full dashboard snapshot
    GET  /metrics      Prometheus text exposition
    GET  /healthz      liveness (503 when saturated)
    GET  /             live demo page (mic capture in the browser)

Concurrency model: recognition runs on a bounded ThreadPoolExecutor with
a bounded work queue — overload answers 503 with Retry-After instead of
queueing unbounded latency. Requests are size-capped; every response
carries CORS headers so the demo page can live anywhere.
"""
from __future__ import annotations

import base64
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .page import PAGE

MAX_BODY = 16 * 1024 * 1024  # 16 MB — ~8 minutes of 16 kHz mono WAV


class Api:
    def __init__(self, assistant, workers: int = 8, queue_size: int = 64):
        self.assistant = assistant
        self.executor = ThreadPoolExecutor(max_workers=workers,
                                           thread_name_prefix="asr")
        self.queue_size = queue_size
        self._in_flight = 0
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- #
    @property
    def saturated(self) -> bool:
        with self._lock:
            return self._in_flight >= self.queue_size

    def submit_recognition(self, pcm, sr, **kwargs):
        """Run process() on the worker pool; raises QueueFull when full."""
        with self._lock:
            if self._in_flight >= self.queue_size:
                raise QueueFull()
            self._in_flight += 1
        try:
            return self.executor.submit(self.assistant.process,
                                        pcm, sr, **kwargs).result()
        finally:
            with self._lock:
                self._in_flight -= 1

    def submit_text(self, text: str, **kwargs):
        """Run process_text() on the worker pool; raises QueueFull."""
        with self._lock:
            if self._in_flight >= self.queue_size:
                raise QueueFull()
            self._in_flight += 1
        try:
            return self.executor.submit(self.assistant.process_text,
                                        text, **kwargs).result()
        finally:
            with self._lock:
                self._in_flight -= 1

    def state(self) -> dict:
        a = self.assistant
        snap = a.stats()
        return {
            **snap,
            "api": {"in_flight": self._in_flight,
                    "queue_size": self.queue_size,
                    "workers": self.executor._max_workers},
            "recent": a.store.recent_utterances(12) if a.store else [],
            "events": a.events.recent(25),
        }


class QueueFull(Exception):
    pass


def make_handler(api: Api):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        # ------------------------------------------------------------ #
        def _cors(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods",
                             "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self._cors()
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj):
            self._send(code, json.dumps(obj).encode(), "application/json")

        def _read_body(self) -> bytes:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                raise ValueError("payload too large")
            return self.rfile.read(length) if length else b""

        # ------------------------------------------------------------ #
        def do_OPTIONS(self):
            self.send_response(204)
            self._cors()
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            path = self.path.split("?")[0]
            api.assistant.metrics.inc("http.requests")
            if path == "/" or path == "/index.html":
                self._send(200, PAGE.encode(), "text/html; charset=utf-8")
            elif path == "/slow":
                # test/capture helper: hold the request open so tools that
                # screenshot at page-load time can wait for async flows
                q = dict(p.split("=", 1) for p in self.path.split("?")[1:]
                         if "=" in p)
                ms = min(int(q.get("ms", "1000") or 1000), 15000)
                time.sleep(ms / 1000.0)
                self._json(200, {"ok": True, "slept_ms": ms})
            elif path == "/healthz":
                if api.saturated:
                    self._json(503, {"ok": False, "reason": "saturated"})
                else:
                    self._json(200, {"ok": True,
                                     "engine": api.assistant.asr.name,
                                     "uptime_s": round(time.time()
                                                       - api.assistant.t0, 1)})
            elif path == "/metrics":
                from ..metrics import prometheus_text
                snap = api.assistant.metrics.snapshot()
                learn = api.assistant.stats()["learning"]
                extra = {"via_learning_rules_active": learn.get("active", 0),
                         "via_learning_rules_total": learn.get("rules", 0),
                         "via_sessions_active": api.assistant.stats()["sessions"]}
                acc = learn.get("accuracy", {})
                if acc and acc.get("accuracy") is not None:
                    extra["via_recognition_accuracy"] = acc["accuracy"]
                self._send(200, prometheus_text(snap, extra).encode(),
                           "text/plain; version=0.0.4")
            elif path == "/api/state":
                self._json(200, api.state())
            else:
                self._json(404, {"error": "not_found"})

        def do_POST(self):
            path = self.path.split("?")[0]
            api.assistant.metrics.inc("http.requests")
            t0 = time.perf_counter()
            try:
                body = self._read_body()
            except ValueError:
                self._json(413, {"error": "payload_too_large"})
                return

            try:
                if path == "/transcribe":
                    self._transcribe(body)
                elif path == "/text":
                    self._text(body)
                elif path == "/tts":
                    self._tts(body)
                elif path == "/feedback":
                    self._feedback(body)
                else:
                    self._json(404, {"error": "not_found"})
            except QueueFull:
                self.send_response(503)
                self.send_header("Retry-After", "1")
                self._cors()
                self.send_header("Content-Length", "0")
                self.end_headers()
            except Exception as exc:  # noqa: BLE001 — API must never 500-dump
                api.assistant.events.add("error", "api", "request_failed",
                                         f"{path}: {type(exc).__name__}: {exc}")
                self._json(500, {"error": "internal",
                                 "detail": type(exc).__name__})
            api.assistant.metrics.observe(
                "http.latency_ms", (time.perf_counter() - t0) * 1000)

        # ------------------------------------------------------------ #
        def _transcribe(self, body):
            q = dict(p.split("=", 1) for p in self.path.split("?")[1:]
                     if "=" in p)
            session = q.get("session", "api")
            lang = q.get("lang") or None
            want_audio = q.get("audio", "1") not in ("0", "false")

            ctype = (self.headers.get("Content-Type") or "").lower()
            if "application/json" in ctype:
                payload = json.loads(body or b"{}")
                wav = base64.b64decode(payload.get("audio_b64", ""))
                lang = payload.get("lang") or lang
                session = payload.get("session", session)
            else:
                wav = body

            if not wav:
                self._json(400, {"error": "empty_body"})
                return
            from ..audio.wavio import read_wav
            pcm, sr = read_wav(wav)

            result = api.submit_recognition(
                pcm, sr, session_id=session, lang=lang,
                want_audio=want_audio)
            code = 200 if "error" not in result else 200  # no_speech is fine
            self._json(code, result)

        def _text(self, body):
            payload = json.loads(body or b"{}")
            text = (payload.get("text") or "").strip()
            if not text:
                self._json(400, {"error": "text_required"})
                return
            result = api.submit_text(
                text, session_id=payload.get("session", "web"),
                lang=payload.get("lang"),
                want_audio=payload.get("audio", "1") != "0")
            self._json(200, result)

        def _tts(self, body):
            payload = json.loads(body or b"{}")
            text = (payload.get("text") or "").strip()
            if not text:
                self._json(400, {"error": "text_required"})
                return
            if not api.assistant.tts:
                self._json(503, {"error": "tts_disabled"})
                return
            pcm, sr = api.assistant.tts.synthesize(
                text, payload.get("lang", "en"))
            import io
            from ..audio.wavio import write_wav
            buf = io.BytesIO()
            write_wav(buf, pcm, sr)
            api.assistant.metrics.inc("tts.direct")
            self._send(200, buf.getvalue(), "audio/wav")

        def _feedback(self, body):
            payload = json.loads(body or b"{}")
            uid = payload.get("utterance_id") or ""
            text = (payload.get("text") or "").strip()
            if not uid or not text:
                self._json(400, {"error": "utterance_id_and_text_required"})
                return
            self._json(200, api.assistant.correct(uid, text))

        def log_message(self, *args):  # keep the console clean
            pass

    return Handler


class Server:
    def __init__(self, assistant, port: int = 8080, workers: int = 8,
                 queue_size: int = 64):
        self.api = Api(assistant, workers=workers, queue_size=queue_size)
        self._server = ThreadingHTTPServer(("0.0.0.0", port),
                                           make_handler(self.api))
        self.port = self._server.server_address[1]

    def serve_forever(self) -> None:
        self._server.serve_forever()

    def shutdown(self) -> None:
        self._server.shutdown()
        self.api.executor.shutdown(wait=False, cancel_futures=True)
