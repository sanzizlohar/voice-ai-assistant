"""ActionCenter: the assistant's hands — allowlist + consent + audit.

Always allowed (read-only / harmless):
    web_search, read_page, open_url, open_app, open_path, sys_info,
    list_dir, search_files, read_file, clipboard_write

Consent-gated (act on your PC / outside it) — the dashboard shows an
Approve/Deny card and the action only runs when you tap Allow:
    run_command   (arbitrary shell; auto-allowed with VIA_SHELL=1)
    linkedin_share (stages your post: text → clipboard, LinkedIn feed
                    opened — you press Post; honest human-in-the-loop)

Every request/run/deny is audited to the event stream.
"""
from __future__ import annotations

import fnmatch
import html.parser
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) via-assistant/1.0")

BASE_TOOLS = {"web_search", "read_page", "open_url", "open_app", "open_path",
              "sys_info", "list_dir", "search_files", "read_file",
              "clipboard_write"}
CONSENT_TOOLS = {"run_command", "linkedin_share"}

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


# --------------------------------------------------------------------- #
# HTML helpers (stdlib)
# --------------------------------------------------------------------- #
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
                self.results.append(self.cur)  # previous hit, no snippet
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
    """Executes allowlisted tools; consent-gates powerful ones; audits all."""

    def __init__(self, events=None, launcher=None, allow_shell: bool | None
                 = None):
        self.events = events
        self._launch = launcher or self._default_launch
        self.allow_shell = (os.environ.get("VIA_SHELL", "") == "1"
                            if allow_shell is None else allow_shell)
        self._pending: dict = {}      # consent_id -> {tool, args, ts}
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- #
    # dispatch + consent
    # ---------------------------------------------------------------- #
    def run(self, tool: str, args: dict | None = None) -> dict:
        args = args or {}
        if tool in BASE_TOOLS:
            pass
        elif tool in CONSENT_TOOLS:
            auto = (tool == "run_command" and self.allow_shell)
            if not auto:
                return self._request_consent(tool, args)
        else:
            self._audit("blocked", tool, args)
            return {"error": f"unknown tool '{tool}'"}
        return self.execute(tool, args)

    def execute(self, tool: str, args: dict) -> dict:
        """Run an already-approved tool call (used by consent flow too)."""
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

    def _request_consent(self, tool: str, args: dict) -> dict:
        cid = f"c{int(time.time() * 1000) % 10 ** 10}"
        with self._lock:
            self._pending[cid] = {"id": cid, "tool": tool, "args": args,
                                  "ts": time.time()}
            while len(self._pending) > 20:       # keep the list bounded
                self._pending.pop(next(iter(self._pending)))
        self._audit("consent_requested", tool, args)
        return {"needs_consent": True, "consent_id": cid,
                "message": (f"about to run '{tool}' on your PC — approve it "
                            "on the dashboard (Allow/Deny)")}

    def pending_list(self) -> list:
        with self._lock:
            return sorted(self._pending.values(), key=lambda c: c["ts"])

    def resolve_consent(self, consent_id: str, allow: bool) -> dict:
        with self._lock:
            item = self._pending.pop(consent_id, None)
        if item is None:
            return {"error": "unknown or already-handled consent id"}
        if not allow:
            self._audit("denied", item["tool"], item["args"])
            return {"denied": True, "tool": item["tool"]}
        self._audit("approved", item["tool"], item["args"])
        return {"approved": True, "tool": item["tool"],
                "result": self.execute(item["tool"], item["args"])}

    def _audit(self, kind: str, tool: str, args: dict) -> None:
        if self.events:
            level = ("warning" if kind in ("blocked", "consent_requested")
                     else "info")
            self.events.add(level, "tools", f"{kind}_{tool}", str(args)[:160])

    @staticmethod
    def _default_launch(target: str) -> None:
        """Fire-and-forget: app launches must never block a request."""
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

        threading.Thread(target=go, daemon=True, name="via-launch").start()

    # ---------------------------------------------------------------- #
    # clipboard + social staging (Windows: PowerShell; POSIX: xclip*)
    # ---------------------------------------------------------------- #
    @staticmethod
    def _copy_clipboard(text: str) -> None:
        if os.name == "nt":
            ps = f"Set-Clipboard -Value '{text.replace("'", "''")}'"
            enc = ps.encode("utf-16-le").hex()
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive",
                 "-EncodedCommand", enc],
                capture_output=True, timeout=15, check=False)
        else:
            for cmd in (["xclip", "-selection", "clipboard"],
                        ["wl-copy"]):
                if shutil.which(cmd[0]):
                    subprocess.run(cmd, input=text.encode(),
                                   check=False, timeout=10)
                    return

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

    def _tool_open_path(self, path: str = "") -> dict:
        path = os.path.expandvars(path or "").strip()
        if not path or not os.path.exists(path):
            return {"error": f"path not found: {path or '(empty)'}"}
        self._launch(path)
        return {"opened": path}

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
        names = sorted(os.listdir(path))
        dirs = [n for n in names if os.path.isdir(os.path.join(path, n))]
        files = [n for n in names if n not in dirs]
        return {"path": path, "folders": dirs[:15], "files": files[:25]}

    def _tool_search_files(self, query: str = "", path: str = "",
                           limit: int = 25) -> dict:
        root = os.path.expandvars(path or os.path.expanduser("~"))
        pattern = f"*{query.lower()}*" if query else "*"
        hits, t0 = [], time.time()
        for dirpath, dirnames, filenames in os.walk(root):
            if time.time() - t0 > 3.0:
                hits.append({"note": "search truncated (3 s limit)"})
                break
            dirnames[:] = [d for d in dirnames
                           if not d.startswith((".", "$"))]
            for f in filenames:
                if fnmatch.fnmatch(f.lower(), pattern):
                    hits.append({"name": f, "path": os.path.join(dirpath, f)})
                    if len(hits) >= limit:
                        return {"matches": hits}
        return {"matches": hits}

    def _tool_read_file(self, path: str = "") -> dict:
        path = os.path.expandvars(path or "").strip()
        if not path or not os.path.isfile(path):
            return {"error": f"file not found: {path or '(empty)'}"}
        if os.path.getsize(path) > 200_000:
            return {"error": "file too large (>200 KB) — open it instead"}
        with open(path, "rb") as fh:
            raw = fh.read()
        if b"\x00" in raw[:1024]:
            return {"error": "binary file — cannot show as text"}
        return {"path": path, "text": raw.decode("utf-8",
                                                 errors="replace")[:4000]}

    def _tool_clipboard_write(self, text: str = "") -> dict:
        text = text or ""
        if not text:
            return {"error": "text required"}
        self._copy_clipboard(text)
        return {"copied": len(text), "preview": text[:120]}

    # ---------------------------------------------------------------- #
    # consent-gated actions
    # ---------------------------------------------------------------- #
    def _tool_run_command(self, command: str = "") -> dict:
        out = subprocess.run(command, shell=True, capture_output=True,
                             text=True, timeout=30)
        return {"exit_code": out.returncode,
                "stdout": out.stdout[:2000],
                "stderr": out.stderr[:1000]}

    def _tool_linkedin_share(self, text: str = "") -> dict:
        """Honest human-in-the-loop posting: stage, never auto-post.
        Copies the text to the clipboard and opens LinkedIn's feed with
        the share box — the user reviews and presses Post themselves."""
        text = (text or "").strip()
        if not text:
            return {"error": "post text required"}
        try:
            self._copy_clipboard(text)
        except Exception:
            pass
        self._launch("https://www.linkedin.com/feed/?shareActive=true")
        return {"staged": True,
                "preview": text[:200],
                "how": "post text is on your clipboard and LinkedIn's "
                       "share box is open — paste, review, press Post"}
