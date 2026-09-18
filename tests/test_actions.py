"""ActionCenter tests: allowlist, audit, launchers, web parsers."""
import unittest

from voice_ai.metrics import EventLog
from voice_ai.tools.actions import ActionCenter, extract_text, parse_ddg


class TestAllowlist(unittest.TestCase):
    def test_base_tools_run(self):
        ac = ActionCenter(events=None)
        out = ac.run("sys_info")
        self.assertIn("os", out)
        self.assertIn("cpu_cores", out)

    def test_shell_blocked_by_default(self):
        ac = ActionCenter(events=None)
        out = ac.run("run_command", {"command": "echo hi"})
        self.assertIn("VIA_SHELL=1", out["error"])

    def test_shell_opt_in(self):
        ac = ActionCenter(events=None, allow_shell=True)
        out = ac.run("run_command", {"command": "echo via-test-123"})
        self.assertEqual(out.get("exit_code"), 0)
        self.assertIn("via-test-123", out.get("stdout", ""))

    def test_unknown_tool(self):
        out = ActionCenter(events=None).run("nope")
        self.assertIn("error", out)


class TestAudit(unittest.TestCase):
    def test_runs_and_blocks_are_logged(self):
        ev = EventLog()
        ac = ActionCenter(events=ev)
        ac.run("sys_info")
        ac.run("run_command", {"command": "echo x"})
        events = ev.recent(10)
        names = [e["event"] for e in events]
        self.assertIn("run_sys_info", names)
        self.assertIn("blocked_run_command", names)


class TestLaunchers(unittest.TestCase):
    def test_open_url_uses_injected_launcher(self):
        seen = []
        ac = ActionCenter(events=None, launcher=seen.append)
        out = ac.run("open_url", {"url": "example.com"})
        self.assertEqual(seen, ["https://example.com"])
        self.assertEqual(out["opened"], "https://example.com")

    def test_open_app_known_alias(self):
        seen = []
        ac = ActionCenter(events=None, launcher=seen.append)
        out = ac.run("open_app", {"name": "notepad"})
        if out.get("opened"):  # notepad exists on Windows
            self.assertEqual(len(seen), 1)
            self.assertIn("notepad", seen[0].lower())
        else:
            self.assertIn("not found", out["error"])

    def test_open_app_unknown(self):
        ac = ActionCenter(events=None, launcher=lambda t: None)
        out = ac.run("open_app", {"name": "zz-not-a-real-app-xyz"})
        self.assertIn("not found", out["error"])


class TestWebParsers(unittest.TestCase):
    DDG_HTML = """
    <div class="result">
      <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fodyssey">
        The Odyssey — Wikipedia</a>
      <a class="result__snippet">Ancient Greek epic attributed to Homer.</a>
    </div>
    <div class="result">
      <a class="result__a" href="https://www.second.org/page">Second hit</a>
      <a class="result__snippet">Another snippet here.</a>
    </div>"""

    def test_parse_ddg_unwraps_redirects(self):
        results = parse_ddg(self.DDG_HTML)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["url"], "https://example.com/odyssey")
        self.assertIn("Odyssey", results[0]["title"])
        self.assertIn("Homer", results[0]["snippet"])
        self.assertIn("Another snippet", results[1]["snippet"])

    def test_extract_text_strips_scripts(self):
        page = ("<html><head><title>My Page</title>"
                "<style>.x{color:red}</style></head><body>"
                "<script>alert(1)</script><p>Hello world of VIA.</p>"
                "</body></html>")
        title, text = extract_text(page)
        self.assertEqual(title, "My Page")
        self.assertIn("Hello world of VIA", text)
        self.assertNotIn("alert", text)
        self.assertNotIn("color:red", text)


if __name__ == "__main__":
    unittest.main()
