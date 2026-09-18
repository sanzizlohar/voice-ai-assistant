"""OpenAI-compatible chat adapter via stdlib urllib — no SDK needed.

Works with Ollama (local), Groq, OpenAI, OpenRouter, LM Studio, vLLM:
anything exposing ``POST {base}/chat/completions``.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from .base import LlmEngine


class OpenAICompatLlm(LlmEngine):
    def __init__(self, base_url: str, api_key: str = "", model: str = ""):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.name = f"llm:{model}" if model else "llm"
        self.timeout = 90.0

    def chat(self, messages: list) -> str:
        t0 = time.perf_counter()
        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "temperature": 0.4,
        }).encode()
        headers = {"Content-Type": "application/json",
                   "User-Agent": "via-assistant"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(
            self.base_url + "/chat/completions", data=payload,
            headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:200]
            raise RuntimeError(f"LLM HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"LLM unreachable at {self.base_url}: "
                               f"{exc}") from exc
        content = (data.get("choices") or [{}])[0].get("message", {}) \
            .get("content", "")
        return content or ""
