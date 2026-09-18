"""ActionCenter implementation: allowlist, launchers, web tools."""
from __future__ import annotations

import html.parser
import os
import platform
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) via-assistant/1.0")

BASE_TOOLS = {"web_search", "read_page", "open_url", "open_app",
              "sys_info", "list_dir"}

# common Windows app resolution: name → candidates (which() name, paths)
APP_ALIASES = {
    "chrome": ["chrome", r"C:\Program Files\Google\Chrome\Application"
               r"\chrome.exe",
               r"C:\Program Files (x86)\Google\Chrome\Application"
               r"\chrome.exe"],
    "edge": ["msedge", r"C:\Program Files (x86)\Microsoft\Edge"
             r"\Application\msedge.exe"],
    "firefox": ["firefox"],
    "notepad": ["notepad"],
    "calculator": ["calc"],
    "calc": ["calc"],
    "paint": ["mspaint"],
    "explorer": ["explorer"],
    "files": ["explorer"],
    "cmd": ["cmd"],
    "terminal": ["wt"],
    "powershell": ["powershell"],
    "code": ["code"],
    "vscode": ["code"],
    "spotify": [r"%APPDATA%\Spotify\Spotify.exe"],
    "word": ["winword"],
    "excel": ["excel"],
}


class _DdgParser(html.parser.HTMLParser):
    """Collects DuckDuckGo HTML results (title/url/snippet)."""

    def __init__(self):
        super().__init__()
        self.results: list = []
        self.cur: dict | None = None
        self.field: str | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "")
        if tag == "a" and "result__a" in cls:
            if self.cur and self.cur["title"]:
                self.results.append(self.cur)  # previous hit had no snippet
            href = a.get("href", "")
            if href.startswith("//duckduckgo.com/l/"):
                qs = urllib.parse.parse_qs(
                    urllib.parse.urlsplit("https:" + href).query)
                href = qs.get("uddg", [href])[0]
            self.cur = {"url": href, "title": "", "snippet": ""}
            self.field = "title"
        elif tag == "a" and "result__snippet" in cls and self.cur:
            self.field = "snippet"

    def handle_data(self, data):
        if self.cur and self.field:
            self.cur[self.field] = self.cur.get(self.field, "") + data

    def handle_endtag(self, tag):
        if tag == "a" and self.cur and self.field == "snippet":
            if self.cur["title"]:
                self.results.append(self.cur)
            self.cur, self.field = None, None


def parse_ddg(html: str, limit: int = 5) -> list:
    p = _DdgParser()
    p.feed(html)
    return p.results[:limit]


class _TextParser(html.parser.HTMLParser):
    """(title, visible text) — scripts/styles/head chrome stripped."""

    SKIP = {"script", "style", "noscript", "svg"}

    def __init__(self):
        super().__init__()
        self.skip = 0
        self.title = ""
        self.chunks: list = []
        self.stack: list = []

    def handle_starttag(self, tag, attrs):
        self.stack.append(tag)
        if tag in self.SKIP:
            self.skip += 1

    def handle_endtag(self, tag):
        while self.stack and self.stack.pop() != tag:
            pass
        if tag in self.SKIP and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if self.skip or not self.stack:
            return
        if self.stack[-1] == "title":
            self.title += data
        else:
            text = " ".join(data.split())
            if len(text) > 1:
                self.chunks.append(text)


def extract_text(html: str, cap: int = 4000) -> tuple:
    p = _TextParser()
    p.feed(html)
    return " ".join(p.title.split()), " ".join(p.chunks)[:cap]


class ActionCenter:
    """Executes allowlisted tools; every run is audited via events."""

    def __init__(self, events=None, launcher=None,
                 allow_shell: bool | None = None):
        self.events = events
        self._launch = launcher or self._default_launch
        self.allow_shell = (os.environ.get("VIA_SHELL", "") == "1"
                            if allow_shell is None else allow_shell)

    # ---------------------------------------------------------------- #
    def run(self, tool: str, args: dict | None = None) -> dict:
        args = args or {}
        allowed = tool in BASE_TOOLS or (tool == "run_command"
                                         and self.allow_shell)
        if not allowed:
            self._audit("blocked", tool, args)
            if tool == "run_command":
                return {"error": "arbitrary shell is disabled — "
                         "set VIA_SHELL=1 to enable"}
            return {"error": f"unknown tool '{tool}'"}
        handler = getattr(self, f"_tool_{tool}", None)
        if handler is None:
            return {"error": f"unknown tool '{tool}'"}
        try:
            result = handler(**args)
        except TypeError as exc:
            result = {"error": f"bad arguments: {exc}"}
        except Exception as exc:  # noqa: BLE001 — surface, never crash
            result = {"error": f"{type(exc).__name__}: {exc}"}
        self._audit("run", tool, args)
        return result

    def _audit(self, kind: str, tool: str, args: dict) -> None:
        if self.events:
            self.events.add("warning" if kind == "blocked" else "info",
                            "tools", f"{kind}_{tool}", str(args)[:160])

    @staticmethod
    def _default_launch(target: str) -> None:
        """Fire-and-forget: app launches must never block a request.
        os.startfile can stall in non-interactive contexts, so the launch
        runs in a daemon thread (exe targets via detached Popen)."""
        import threading

        def go():
            try:
                if os.name == "nt":
                    if target.lower().endswith(".exe"):
                        subprocess.Popen([target], close_fds=True,
                                         creationflags=0x00000008)
                    else:
                        os.startfile(target)  # noqa: S606
                else:
                    subprocess.Popen([target])
            except Exception:
                pass

        threading.Thread(target=go, daemon=True,
                         name="via-launch").start()

    # ---------------------------------------------------------------- #
    # web tools (stdlib only)
    # ---------------------------------------------------------------- #
    def _tool_web_search(self, query: str = "", limit: int = 5) -> dict:
        query = (query or "").strip()
        if not query:
            return {"error": "query required"}
        url = ("https://html.duckduckgo.com/html/?q="
               + urllib.parse.quote(query))
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=10) as resp:
            page = resp.read().decode("utf-8", errors="replace")
        results = parse_ddg(page, limit)
        if not results:
            return {"results": [], "note": "no results parsed"}
        return {"results": results}

    def _tool_read_page(self, url: str = "") -> dict:
        url = (url or "").strip()
        if not url.startswith(("http://", "https://")):
            return {"error": "http(s) url required"}
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=12) as resp:
            page = resp.read().decode("utf-8", errors="replace")
        title, text = extract_text(page)
        return {"url": url, "title": title, "text": text}

    # ---------------------------------------------------------------- #
    # PC tools
    # ---------------------------------------------------------------- #
    def _tool_open_url(self, url: str = "") -> dict:
        url = (url or "").strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        self._launch(url)
        return {"opened": url}

    def _tool_open_app(self, name: str = "") -> dict:
        name = (name or "").strip().lower()
        if not name:
            return {"error": "app name required"}
        target = self.resolve_app(name)
        if target is None:
            return {"opened": False, "error": f"app '{name}' not found"}
        self._launch(target)
        return {"opened": name, "path": target}

    def resolve_app(self, name: str) -> str | None:
        for cand in APP_ALIASES.get(name, [name]):
            cand = os.path.expandvars(cand)
            if os.name == "nt" and "/" not in cand and "\\" not in cand:
                # Windows system apps beat PATH surprises (Git's notepad…)
                for sysdir in (r"C:\Windows\System32", r"C:\Windows"):
                    p = os.path.join(sysdir, cand if cand.endswith(".exe")
                                     else cand + ".exe")
                    if os.path.exists(p):
                        return p
            found = shutil.which(cand)
            if found:
                return found
            if os.path.exists(cand):
                return cand
        return None

    def _tool_sys_info(self) -> dict:
        usage = shutil.disk_usage("C:/" if os.name == "nt" else "/")
        return {
            "os": platform.platform(),
            "machine": platform.machine(),
            "cpu_cores": os.cpu_count(),
            "python": sys.version.split()[0],
            "disk_free_gb": round(usage.free / 1e9, 1),
            "user": os.environ.get("USERNAME")
                    or os.environ.get("USER", ""),
        }

    def _tool_list_dir(self, path: str = "") -> dict:
        path = os.path.expandvars(path or os.path.expanduser("~"))
        return {"path": path, "entries": sorted(os.listdir(path))[:30]}

    def _tool_run_command(self, command: str = "") -> dict:
        if not self.allow_shell:
            return {"error": "shell disabled — set VIA_SHELL=1"}
        out = subprocess.run(command, shell=True, capture_output=True,
                             text=True, timeout=30)
        return {"exit_code": out.returncode,
                "stdout": out.stdout[:2000],
                "stderr": out.stderr[:1000]}
