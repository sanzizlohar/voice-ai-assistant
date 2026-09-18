"""LLM engine interface, discovery, and the tool-calling agent loop."""
from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod

OLLAMA_BASE = "http://localhost:11434/v1"

SYSTEM_PROMPT = (
    "You are VIA, a voice assistant running on the user's PC. "
    "Answer as if your reply will be SPOKEN aloud: concise, natural, "
    "no markdown, no lists unless asked. Reply in {lang_name}.\n"
    "You may use tools. To call one, reply with ONLY a JSON object: "
    '{{"tool": "<name>", "args": {{...}}}}\n'
    "Tools: web_search {{\"query\": \"...\"}} — search the web; "
    "read_page {{\"url\": \"...\"}} — read a webpage's text; "
    "open_app {{\"name\": \"chrome|notepad|calculator|...\"}} — launch a "
    "PC app; open_url {{\"url\": \"...\"}} — open a website; "
    "sys_info {{}} — CPU/RAM/disk facts; list_dir {{\"path\": \"...\"}} "
    "— list a folder (default: home).\n"
    "After a message starting with OBSERVATION: you may call another "
    "tool or give the final plain-text answer. Never mention the tools."
)

LANG_NAMES = {"en": "English", "hi": "Hindi (Devanagari)",
              "bn": "Bengali", "es": "Spanish", "fr": "French",
              "de": "German"}


class LlmEngine(ABC):
    name: str = "llm"

    @abstractmethod
    def chat(self, messages: list) -> str:
        """messages (OpenAI format) → assistant text."""

    def warmup(self) -> float:
        return 0.0


def parse_tool_call(content: str) -> tuple | None:
    """Extract {\"tool\": ..., \"args\": ...} from a model reply.

    Tolerates markdown fences and prose around the JSON. Returns
    (name, args) or None when the reply is a final answer.
    """
    text = content.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    else:
        # first balanced object (one nesting level) that mentions "tool"
        brace = re.search(r"\{(?:[^{}]|\{[^{}]*\})*\}", text, re.S)
        if brace and "\"tool\"" in brace.group(0):
            text = brace.group(0)
    if "\"tool\"" not in text:
        return None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None
    name = obj.get("tool")
    if not name:
        return None
    return str(name), obj.get("args") or {}


class LlmAgent:
    """ReAct-lite loop: chat → optional tool JSON → observation → answer."""

    MAX_TOOL_ROUNDS = 3

    def __init__(self, engine: LlmEngine, actions):
        self.engine = engine
        self.actions = actions

    def answer(self, question: str, lang: str = "en") -> dict:
        system = SYSTEM_PROMPT.format(
            lang_name=LANG_NAMES.get(lang.split("-")[0], "English"))
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": question}]
        tools: list = []
        for _ in range(self.MAX_TOOL_ROUNDS + 1):
            content = self.engine.chat(messages).strip()
            call = parse_tool_call(content)
            if call is None:
                return {"reply": content or "I have nothing to add.",
                        "tools": tools}
            if len(tools) >= self.MAX_TOOL_ROUNDS:
                return {"reply": content, "tools": tools,
                        "note": "stopped after the tool round limit"}
            name, args = call
            tools.append(name)
            observation = self.actions.run(name, args)
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content":
                             "OBSERVATION: " + json.dumps(observation)[:2400]})
        return {"reply": content, "tools": tools,
                "note": "stopped after the tool round limit"}


def get_llm() -> LlmEngine | None:
    """Discover a brain: env vars > saved via_llm.json (dashboard/CLI)
    > local Ollama probe. Returns None when nothing is available — the
    assistant still works with intents and the tool fast paths."""
    from .config import resolve
    engine, _source = resolve()
    return engine
