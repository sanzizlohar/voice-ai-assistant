"""Brain settings: provider catalog + persistent config (via_llm.json).

Users pick a provider, paste an API key, choose a model — from the
dashboard (POST /api/brain), the CLI (`vai brain`) or plain env vars.
Precedence: env vars > saved config > local Ollama auto-detect.

The API key is stored in plain text next to the project (it is a local
personal tool); GET /api/brain always masks it.
"""
from __future__ import annotations

import json
import os
import urllib.request

PROVIDERS = {
    "ollama": {
        "label": "Ollama (local, free)",
        "base_url": "http://localhost:11434/v1",
        "needs_key": False,
        "models": ["llama3.2", "llama3.1", "qwen2.5", "mistral",
                   "gemma2", "phi3"],
        "hint": "install from ollama.com, then: ollama pull llama3.2",
    },
    "groq": {
        "label": "Groq (free tier, very fast)",
        "base_url": "https://api.groq.com/openai/v1",
        "needs_key": True,
        "models": ["llama-3.3-70b-versatile", "openai/gpt-oss-20b",
                   "moonshotai/kimi-k2-instruct", "gemma2-9b-it"],
        "hint": "free key at console.groq.com",
    },
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "needs_key": True,
        "models": ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini"],
        "hint": "key at platform.openai.com",
    },
    "openrouter": {
        "label": "OpenRouter (100+ models)",
        "base_url": "https://openrouter.ai/api/v1",
        "needs_key": True,
        "models": ["meta-llama/llama-3.1-8b-instruct:free",
                   "google/gemini-2.0-flash-exp:free",
                   "anthropic/claude-3.5-haiku"],
        "hint": "free models available; key at openrouter.ai",
    },
    "custom": {
        "label": "Custom OpenAI-compatible URL",
        "base_url": "",
        "needs_key": False,
        "models": [],
        "hint": "LM Studio, vLLM, together.ai, …",
    },
}


def config_path() -> str:
    """Stable location (independent of the server's cwd) — the brain
    survives restarting the server from any folder."""
    d = os.path.join(os.path.expanduser("~"), ".via")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "brain.json")


def load_config() -> dict | None:
    """Saved dashboard/CLI settings, if any."""
    try:
        with open(config_path(), encoding="utf-8") as fh:
            cfg = json.load(fh)
        return cfg if cfg.get("provider") else None
    except (OSError, json.JSONDecodeError):
        return None


GARBAGE_MODELS = ("", "undefined", "null", "none")


def _provider_for_url(base_url: str, provider: str) -> str:
    """Trust the URL over the dropdown: a groq URL with a key is groq,
    even if the browser sent a mismatched provider value."""
    url = (base_url or "").lower()
    if "api.groq.com" in url:
        return "groq"
    if "api.openai.com" in url:
        return "openai"
    if "openrouter.ai" in url:
        return "openrouter"
    if "localhost:11434" in url or "127.0.0.1:11434" in url:
        return "ollama"
    return provider if provider in PROVIDERS else "custom"


def save_config(provider: str, api_key: str = "", model: str = "",
                base_url: str = "") -> dict:
    provider = _provider_for_url(base_url, provider)
    spec = PROVIDERS[provider]
    model = (model or "").strip()
    if model.lower() in GARBAGE_MODELS:
        model = ""                       # never persist browser garbage
    cfg = {
        "provider": provider,
        "base_url": base_url or spec["base_url"],
        "model": model or (spec["models"][0] if spec["models"] else ""),
        "api_key": (api_key or "").strip(),
    }
    if spec["needs_key"] and not cfg["api_key"]:
        raise ValueError(f"{provider} needs an API key")
    if not cfg["base_url"]:
        raise ValueError("base_url required for custom provider")
    with open(config_path(), "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
    return cfg


def clear_config() -> bool:
    try:
        os.remove(config_path())
        return True
    except OSError:
        return False


BAD_MODEL_PARTS = ("prompt-guard", "guard", "whisper", "tts", "orpheus",
                   "embed", "safeguard", "moderation")
PREFERRED_PARTS = ("llama-3.3", "llama-3.1", "gpt-oss", "kimi", "qwen",
                   "deepseek", "70b", "instruct", "gemma")


def pick_chat_model(models: list) -> str | None:
    """Choose a CHAT model from a provider's /models list — never a
    guard/tts/embed model; prefer well-known chat families."""
    clean = [m for m in models if m and not any(
        bad in m.lower() for bad in BAD_MODEL_PARTS)]
    if not clean:
        return None
    for part in PREFERRED_PARTS:
        for m in clean:
            if part in m.lower():
                return m
    return clean[0]


def engine_from_config(cfg: dict):
    """Build an OpenAICompatLlm from a saved/env config dict."""
    from .openai_compat import OpenAICompatLlm
    return OpenAICompatLlm(cfg.get("base_url", ""),
                           cfg.get("api_key", ""),
                           cfg.get("model", ""))


def probe(engine) -> dict:
    """Cheap reachability check: GET /models with a short timeout."""
    try:
        headers = {"User-Agent": "via"}
        if engine.api_key:
            headers["Authorization"] = f"Bearer {engine.api_key}"
        req = urllib.request.Request(engine.base_url + "/models",
                                     headers=headers)
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            data = json.loads(resp.read().decode())
        models = [m.get("id") for m in data.get("data", []) if m.get("id")]
        return {"ok": True, "models": models[:20]}
    except Exception as exc:  # noqa: BLE001 — status reporting
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:160]}


def resolve() -> tuple:
    """(engine | None, source) — env > saved config > ollama probe."""
    env_base = os.environ.get("VIA_LLM_BASE_URL")
    env_key = os.environ.get("VIA_LLM_API_KEY")
    env_model = os.environ.get("VIA_LLM_MODEL")
    if env_base or env_key or env_model:
        return engine_from_config({
            "base_url": env_base or "https://api.openai.com/v1",
            "api_key": env_key or "",
            "model": env_model or "gpt-4o-mini"}), "env"
    cfg = load_config()
    if cfg:
        if str(cfg.get("model", "")).lower() in ("", "undefined", "null",
                                                "none"):
            models = probe(engine_from_config(cfg)).get("models") or []
            picked = pick_chat_model(models)
            if not picked:
                return None, "none"
            cfg["model"] = picked
            save_config(cfg["provider"], api_key=cfg.get("api_key", ""),
                        model=picked, base_url=cfg.get("base_url", ""))
        return engine_from_config(cfg), cfg["provider"]
    # local ollama probe (0.6 s — boot stays fast)
    try:
        req = urllib.request.Request(
            "http://localhost:11434/v1/models", headers={"User-Agent": "via"})
        with urllib.request.urlopen(req, timeout=0.6) as resp:
            data = json.loads(resp.read().decode())
        models = [m.get("id") for m in data.get("data", []) if m.get("id")]
        return engine_from_config({
            "provider": "ollama",
            "base_url": "http://localhost:11434/v1",
            "model": models[0] if models else "llama3.2"}), "ollama"
    except Exception:
        return None, "none"
