"""Cloud Whisper ASR + agent-mode routing tests (all against local fakes)."""
import array
import json
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from voice_ai.asr.base import get_engine
from voice_ai.asr.cloud_whisper import CloudWhisperAsr, _script_lang
from voice_ai.asr.offline import OfflineCodecAsr
from voice_ai.llm.base import LlmAgent, LlmEngine
from voice_ai.metrics import EventLog
from voice_ai.persistence.store import Store
from voice_ai.pipeline import Assistant
from voice_ai.tts.offline import OfflineTts


class FakeCloud:
    """Multipart /audio/transcriptions stub recording what was sent."""

    def __init__(self, text="এখন সময় তিনটা বাজে", language="bn",
                 fail=False):
        self.text, self.language, self.fail = text, language, fail
        self.last_body = b""
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                outer.last_body = self.rfile.read(length)
                if outer.fail:
                    self.send_response(503)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                resp = json.dumps(
                    {"text": outer.text, "language": outer.language}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever,
                         daemon=True).start()

    def stop(self):
        self.server.shutdown()


class TestScriptLang(unittest.TestCase):
    def test_detects_indic_scripts(self):
        self.assertEqual(_script_lang("এখন সময় তিনটা", "en"), "bn")
        self.assertEqual(_script_lang("अभी समय तीन बजे", "en"), "hi")
        self.assertEqual(_script_lang("what time is it", "en"), "en")


class TestCloudWhisper(unittest.TestCase):
    def test_transcribes_bengali_and_reports_language(self):
        fake = FakeCloud(text="এখন সময় তিনটা বাজে", language="bn")
        try:
            engine = CloudWhisperAsr(
                f"http://127.0.0.1:{fake.port}/v1", "sk-test",
                "whisper-large-v3", local=OfflineCodecAsr())
            pcm = array.array("h", (0,) * 16000)
            hyp = engine.transcribe(pcm, 16000)
            self.assertEqual(hyp.language, "bn")
            self.assertEqual(hyp.tokens, "এখন সময় তিনটা বাজে".split())
            self.assertIn("whisper-large-v3", hyp.engine)
            # the audio went out as a multipart WAV with the model set
            self.assertIn(b"whisper-large-v3", fake.last_body)
            self.assertIn(b"WAVE", fake.last_body)
        finally:
            fake.stop()

    def test_falls_back_to_local_when_cloud_fails(self):
        fake = FakeCloud(fail=True)
        try:
            engine = CloudWhisperAsr(
                f"http://127.0.0.1:{fake.port}/v1", "sk-test", "m",
                local=OfflineCodecAsr())
            pcm = array.array("h", (0,) * 16000)
            hyp = engine.transcribe(pcm, 16000)
            self.assertEqual(hyp.engine, "offline")
            self.assertIn("unreachable", hyp.note)
        finally:
            fake.stop()


class TestAgentRouting(unittest.TestCase):
    """With a brain connected, voice AND text requests go agent-first."""

    class Scripted(LlmEngine):
        name = "fake-brain"

        def __init__(self, replies):
            self.replies = list(replies)
            self.questions = []

        def chat(self, messages):
            self.questions.append(messages[-1]["content"])
            return self.replies.pop(0)

    def _assistant(self, replies):
        llm = self.Scripted(replies)
        a = Assistant(asr_engine=OfflineCodecAsr(),
                      tts_engine=OfflineTts(), llm_engine=llm,
                      store=Store(":memory:"))
        return a, llm

    def test_general_question_routes_to_agent(self):
        a, llm = self._assistant(["The Odyssey was written by Homer."])
        r = a.process_text("who wrote the odyssey", session_id="ag",
                           want_audio=False)
        self.assertEqual(r["intent"], "chat")
        self.assertIn("Homer", r["reply"])
        self.assertEqual(llm.questions[-1], "who wrote the odyssey")

    def test_agent_uses_take_note_tool(self):
        a, llm = self._assistant([
            '{"tool": "take_note", "args": {"text": "meeting tomorrow at 5"}}',
            "Noted — meeting tomorrow at 5."])
        r = a.process_text("note that I have a meeting tomorrow at 5",
                           session_id="ag", want_audio=False)
        self.assertEqual(r["intent"], "chat")
        self.assertEqual(r["tools"], ["take_note"])
        rows = a.store.recent_utterances(10)
        self.assertTrue(any(u["intent"] == "note"
                            and "meeting" in u["final"] for u in rows),
                        "agent note was not persisted")

    def test_agent_gets_time_via_tool(self):
        a, llm = self._assistant([
            '{"tool": "get_time", "args": {}}',
            "It is 10:30 right now."])
        r = a.process_text("what time is it", session_id="ag",
                           want_audio=False)
        self.assertEqual(r["tools"], ["get_time"])
        self.assertIn("10:30", r["reply"])
        observation = llm.questions[1]
        self.assertIn("OBSERVATION:", observation)
        self.assertIn('"time"', observation)

    def test_agent_failure_falls_back_to_local_intent(self):
        class Broken(LlmEngine):
            name = "broken"

            def chat(self, messages):
                raise RuntimeError("provider down")

        a = Assistant(asr_engine=OfflineCodecAsr(),
                      tts_engine=OfflineTts(), llm_engine=Broken(),
                      store=Store(":memory:"))
        r = a.process_text("what time is it", session_id="ag",
                           want_audio=False)
        self.assertEqual(r["intent"], "time",
                         "local intents must cover agent failures")

    def test_no_brain_keeps_local_intents(self):
        a, _ = self._assistant([])  # scripted with no replies
        a.agent = None              # simulate no brain
        r = a.process_text("what time is it", session_id="ag",
                           want_audio=False)
        self.assertEqual(r["intent"], "time")


class TestEngineFactoryCloud(unittest.TestCase):
    def test_custom_cloud_asr_from_env(self):
        old = dict(os.environ) if False else None
        import os
        saved = {k: os.environ.get(k) for k in
                 ("VIA_ASR_BASE_URL", "VIA_ASR_API_KEY", "VIA_ASR_MODEL",
                  "VIA_LLM_BASE_URL", "VIA_LLM_API_KEY", "VIA_LLM_MODEL")}
        fake = FakeCloud()
        try:
            for k in saved.values():
                pass
            os.environ["VIA_ASR_BASE_URL"] = \
                f"http://127.0.0.1:{fake.port}/v1"
            os.environ["VIA_ASR_API_KEY"] = "sk-asr"
            os.environ["VIA_ASR_MODEL"] = "whisper-large-v3"
            engine = get_engine("auto")
            self.assertIn("cloud:whisper-large-v3", engine.name)
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            fake.stop()


if __name__ == "__main__":
    unittest.main()
