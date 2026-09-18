"""HTTP API tests: transcribe, tts, feedback, health, metrics, saturation."""
import base64
import io
import json
import threading
import unittest
import urllib.error
import urllib.request

from voice_ai.asr.offline import OfflineCodecAsr
from voice_ai.audio.synth import Channel, Synthesizer
from voice_ai.audio.wavio import write_wav
from voice_ai.metrics import prometheus_text
from voice_ai.persistence.store import Store
from voice_ai.pipeline import Assistant
from voice_ai.server.api import Server
from voice_ai.tts.offline import OfflineTts


class TestApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assistant = Assistant(asr_engine=OfflineCodecAsr(),
                                  tts_engine=OfflineTts(),
                                  llm_engine=False,
                                  store=Store(":memory:"))
        cls.assistant.warmup()
        cls.server = Server(cls.assistant, port=0, workers=2, queue_size=4)
        cls.port = cls.server.port
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()
        cls.syn = Synthesizer(Channel(error_rate=0.0, snr_db=26.0, seed=2))

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def post(self, path, body: bytes, ctype: str):
        req = urllib.request.Request(
            self.url(path), data=body, method="POST",
            headers={"Content-Type": ctype})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def get(self, path):
        try:
            with urllib.request.urlopen(self.url(path), timeout=30) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_transcribe_wav(self):
        pcm, meta = self.syn.utterance("en", "what time is it")
        buf = io.BytesIO()
        write_wav(buf, pcm, 16000)
        status, body = self.post("/transcribe?session=pytest", buf.getvalue(),
                                 "audio/wav")
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertEqual(result["tokens"], meta["words"])
        self.assertEqual(result["intent"], "time")
        self.assertIn("total_ms", result)
        self.assertIsNotNone(result["audio_b64"])

    def test_transcribe_json_b64(self):
        pcm, _ = self.syn.utterance("es", "que hora es")
        buf = io.BytesIO()
        write_wav(buf, pcm, 16000)
        payload = json.dumps({"audio_b64": base64.b64encode(
            buf.getvalue()).decode(), "lang": "es"}).encode()
        status, body = self.post("/transcribe", payload,
                                 "application/json")
        result = json.loads(body)
        self.assertEqual(result["language"], "es")

    def test_feedback_endpoint_learns(self):
        pcm, meta = self.syn.utterance("en", "note buy coffee beans")
        buf = io.BytesIO()
        write_wav(buf, pcm, 16000)
        _, body = self.post("/transcribe?session=pytest2", buf.getvalue(),
                            "audio/wav")
        uid = json.loads(body)["id"]
        status, body = self.post("/feedback", json.dumps(
            {"utterance_id": uid, "text": "note buy coffee beans"}).encode(),
            "application/json")
        self.assertEqual(status, 200)
        out = json.loads(body)
        self.assertIn("rules_active", out)

    def test_text_endpoint(self):
        status, body = self.post("/text", json.dumps(
            {"text": "what is twelve plus thirty", "session": "pytest3"}
        ).encode(), "application/json")
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertEqual(result["intent"], "math")
        self.assertEqual(result["engine"], "text")
        self.assertIn("42", result["reply"])

    def test_text_detects_hindi(self):
        status, body = self.post("/text", json.dumps(
            {"text": "अभी समय क्या हुआ"}).encode(), "application/json")
        result = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(result["language"], "hi")
        self.assertEqual(result["intent"], "time")

    def test_brain_custom_provider_end_to_end(self):
        """Connect a custom OpenAI-compatible brain via the API, verify it
        shows as connected, then chat through it."""
        import json
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        outer = self

        class FakeLLM(BaseHTTPRequestHandler):
            def _send(self, obj):
                body = json.dumps(obj).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):  # probe → /models
                self._send({"data": [{"id": "stub-brain-model"}]})

            def do_POST(self):  # chat → /chat/completions
                self._send({"choices": [{"message": {
                    "role": "assistant",
                    "content": "The Odyssey was written by Homer."}}]})

            def log_message(self, *args):
                pass

        srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeLLM)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            status, body = self.post("/api/brain", json.dumps({
                "provider": "custom",
                "base_url": f"http://127.0.0.1:{srv.server_address[1]}/v1",
                "model": "stub-brain-model",
                "api_key": "sk-test",
            }).encode(), "application/json")
            out = json.loads(body)
            self.assertEqual(status, 200)
            self.assertTrue(out["probe"]["ok"], out)

            status, body = self.get("/api/brain")
            brain = json.loads(body)["current"]
            self.assertEqual(brain["provider"], "custom")
            self.assertEqual(brain["engine_name"], "llm:stub-brain-model")
            self.assertEqual(brain["api_key_masked"], "…test")

            status, body = self.post("/text", json.dumps({
                "text": "who wrote the odyssey",
                "session": "brain-e2e", "audio": "0"}).encode(),
                "application/json")
            result = json.loads(body)
            self.assertEqual(result["intent"], "chat")
            self.assertIn("Homer", result["reply"])
        finally:
            srv.shutdown()
            from voice_ai.llm.config import clear_config
            clear_config()
            outer.assistant.set_llm(None)
            outer.assistant.asr = OfflineCodecAsr()

    def test_tts_endpoint(self):
        status, body = self.post("/tts", json.dumps(
            {"text": "hello there", "lang": "en"}).encode(),
            "application/json")
        self.assertEqual(status, 200)
        self.assertGreater(len(body), 1000)  # a real WAV

    def test_healthz_and_metrics(self):
        status, body = self.get("/healthz")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["ok"])
        status, body = self.get("/metrics")
        self.assertEqual(status, 200)
        text = body.decode()
        self.assertIn("http_requests", text)
        self.assertIn("via_learning", text)

    def test_api_state(self):
        status, body = self.get("/api/state")
        self.assertEqual(status, 200)
        state = json.loads(body)
        self.assertIn("recent", state)
        self.assertIn("learning", state)
        self.assertIn("stages", state)

    def test_demo_page_served(self):
        status, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"Voice AI Assistant", body)

    def test_unknown_route_404(self):
        status, _ = self.get("/nope")
        self.assertEqual(status, 404)

    def test_empty_body_400(self):
        status, _ = self.post("/transcribe", b"", "audio/wav")
        self.assertEqual(status, 400)


class TestPrometheus(unittest.TestCase):
    def test_format(self):
        snap = {"counters": {"http.requests": 3},
                "gauges": {"bus.depth": 0},
                "histograms": {"pipeline.total_ms": {
                    "count": 2, "p50": 100.0, "p95": 200.0, "avg": 150.0}},
                "ts": 0.0}
        text = prometheus_text(snap, {"via_x": 1})
        self.assertIn("# TYPE http_requests counter", text)
        self.assertIn("http_requests 3", text)
        self.assertIn("pipeline_total_ms_p95_ms 200.0", text)
        self.assertIn("via_x 1", text)


if __name__ == "__main__":
    unittest.main()
