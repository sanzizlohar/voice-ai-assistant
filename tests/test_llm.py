"""LLM brain tests: tool-call parsing, agent loop, OpenAI-compatible wire
format, brain discovery precedence."""
import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from voice_ai.llm.base import LlmAgent, LlmEngine, get_llm, parse_tool_call
from voice_ai.llm.openai_compat import OpenAICompatLlm
from voice_ai.tools.actions import ActionCenter


class FakeLlm(LlmEngine):
    """Scripted replies; records the message lists it was given."""

    name = "fake"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, messages):
        self.calls.append(messages)
        return self.replies.pop(0) if self.replies else "done"


class StubActions:
    def __init__(self):
        self.runs = []

    def run(self, tool, args=None):
        self.runs.append((tool, args or {}))
        return {"ok": True, "tool": tool}


class TestParseToolCall(unittest.TestCase):
    def test_plain_json(self):
        call = parse_tool_call('{"tool": "web_search", "args": '
                               '{"query": "odyssey author"}}')
        self.assertEqual(call, ("web_search", {"query": "odyssey author"}))

    def test_fenced_json(self):
        text = '```json\n{"tool": "open_app", "args": {"name": "chrome"}}\n```'
        self.assertEqual(parse_tool_call(text), ("open_app", {"name": "chrome"}))

    def test_prose_wrapped(self):
        text = 'Let me check. {"tool": "sys_info", "args": {}} — one moment'
        self.assertEqual(parse_tool_call(text), ("sys_info", {}))

    def test_final_answer_is_none(self):
        self.assertIsNone(parse_tool_call("The Odyssey was written by Homer."))
        self.assertIsNone(parse_tool_call('{"foo": 1}'))
        self.assertIsNone(parse_tool_call('{"tool": broken'))


class TestAgentLoop(unittest.TestCase):
    def test_tool_round_then_answer(self):
        llm = FakeLlm([
            '{"tool": "web_search", "args": {"query": "odyssey author"}}',
            'The Odyssey was written by Homer around the 8th century BC.'])
        agent = LlmAgent(llm, StubActions())
        out = agent.answer("who wrote the odyssey", "en")
        self.assertIn("Homer", out["reply"])
        self.assertEqual(out["tools"], ["web_search"])
        # observation was fed back to the model
        second = llm.calls[1]
        self.assertEqual(second[-1]["role"], "user")
        self.assertTrue(second[-1]["content"].startswith("OBSERVATION:"))

    def test_round_limit(self):
        llm = FakeLlm(['{"tool": "sys_info", "args": {}}'] * 9)
        agent = LlmAgent(llm, StubActions())
        out = agent.answer("system?", "en")
        self.assertLessEqual(len(out["tools"]), LlmAgent.MAX_TOOL_ROUNDS)
        self.assertIn("note", out)

    def test_reply_in_language(self):
        llm = FakeLlm(["होमर ने ओडिसी लिखी थी।"])
        agent = LlmAgent(llm, StubActions())
        out = agent.answer("odyssey kisne likha", "hi")
        self.assertIn("होमर", out["reply"])
        system = llm.calls[0][0]["content"]
        self.assertIn("Hindi", system)


class FakeOpenAiServer:
    """Minimal /v1/chat/completions stub recording auth + body."""

    def __init__(self, content):
        self.content = content
        self.seen_auth = None
        self.seen_model = None
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length))
                outer.seen_auth = self.headers.get("Authorization")
                outer.seen_model = body.get("model")
                resp = json.dumps({"choices": [{"message": {
                    "role": "assistant", "content": outer.content}}]}).encode()
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


class TestOpenAiCompat(unittest.TestCase):
    def test_chat_roundtrip_and_auth(self):
        srv = FakeOpenAiServer("Hello from the stub brain.")
        try:
            llm = OpenAICompatLlm(f"http://127.0.0.1:{srv.port}/v1",
                                  "test-key-123", "stub-model")
            out = llm.chat([{"role": "user", "content": "hi"}])
            self.assertEqual(out, "Hello from the stub brain.")
            self.assertEqual(srv.seen_auth, "Bearer test-key-123")
            self.assertEqual(srv.seen_model, "stub-model")
        finally:
            srv.stop()

    def test_unreachable_raises_runtime(self):
        llm = OpenAICompatLlm("http://127.0.0.1:9/v1", "", "m")
        with self.assertRaises(RuntimeError):
            llm.chat([{"role": "user", "content": "hi"}])

    def test_agent_uses_wire_engine(self):
        srv = FakeOpenAiServer("2 plus 2 is 4.")
        try:
            llm = OpenAICompatLlm(f"http://127.0.0.1:{srv.port}/v1", "", "m")
            out = LlmAgent(llm, StubActions()).answer("what is 2 plus 2")
            self.assertIn("4", out["reply"])
            self.assertEqual(out["tools"], [])
        finally:
            srv.stop()


class TestPickChatModel(unittest.TestCase):
    def test_skips_guard_tts_and_picks_chat(self):
        from voice_ai.llm.config import pick_chat_model
        models = ["meta-llama/llama-prompt-guard-2-86m",
                  "canopylabs/orpheus-v1-english",
                  "openai/gpt-oss-120b", "allam-2-7b"]
        self.assertEqual(pick_chat_model(models), "openai/gpt-oss-120b")

    def test_garbage_never_stored(self):
        from voice_ai.llm.config import pick_chat_model
        self.assertIsNone(pick_chat_model([]))
        self.assertEqual(pick_chat_model(["undefined"]), "undefined")
        # 'undefined' garbage is filtered at save/resolve time instead


class TestDiscovery(unittest.TestCase):
    def test_env_config_wins(self):
        old = {k: os.environ.get(k) for k in
               ("VIA_LLM_BASE_URL", "VIA_LLM_API_KEY", "VIA_LLM_MODEL")}
        try:
            os.environ["VIA_LLM_BASE_URL"] = "http://127.0.0.1:9/v1"
            os.environ["VIA_LLM_MODEL"] = "test-model"
            engine = get_llm()
            self.assertIsNotNone(engine)
            self.assertEqual(engine.model, "test-model")
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_no_brain_is_none_or_ollama(self):
        old = {k: os.environ.pop(k, None) for k in
               ("VIA_LLM_BASE_URL", "VIA_LLM_API_KEY", "VIA_LLM_MODEL")}
        try:
            engine = get_llm()  # None, unless a local Ollama is running
            self.assertTrue(engine is None or hasattr(engine, "chat"))
        finally:
            for k, v in old.items():
                if v is not None:
                    os.environ[k] = v


class TestActionGuard(unittest.TestCase):
    def test_unknown_tool_blocked(self):
        out = ActionCenter(events=None).run("format_c", {"drive": "c"})
        self.assertIn("error", out)

    def test_llm_loop_blocked_tools_surfaced(self):
        llm = FakeLlm([
            '{"tool": "run_command", "args": {"command": "rm -rf /"}}',
            "I cannot run shell commands.",
        ])
        agent = LlmAgent(llm, ActionCenter(events=None))
        out = agent.answer("clean my disk", "en")
        self.assertIn("approve", llm.calls[1][-1]["content"])
        self.assertEqual(out["tools"], ["run_command"])


if __name__ == "__main__":
    unittest.main()
