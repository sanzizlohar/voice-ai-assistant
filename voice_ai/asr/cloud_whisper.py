"""Cloud Whisper ASR: OpenAI-compatible audio transcription endpoint.

On CPU-class hardware the local `small` model (needed for good Bengali)
takes minutes — but Groq/OpenAI serve `whisper-large-v3` in ~1 s with
excellent বাংলা/हिन्दी accuracy. When a brain with an audio-capable
provider (groq/openai/custom) is configured, this engine transcribes
through the cloud and falls back to the local model on any failure.

    export VIA_ASR_BASE_URL=https://api.groq.com/openai/v1   # optional
    export VIA_ASR_API_KEY=gsk_...
    export VIA_ASR_MODEL=whisper-large-v3

Discovery (no env): reuses the saved brain config when its provider is
groq (whisper-large-v3) or openai (whisper-1).
"""
from __future__ import annotations

import io
import json
import time
import urllib.error
import urllib.request
import uuid

from .base import AsrEngine, Hypothesis
from ..llm.openai_compat import BROWSER_UA


def _script_lang(text: str, fallback: str) -> str:
    """Language from script shares (Bengali/Devanagari are unambiguous)."""
    alpha = [c for c in text if c.isalpha()]
    if not alpha:
        return fallback or "en"
    bengali = sum(1 for c in alpha if 0x0980 <= ord(c) <= 0x09FF)
    deva = sum(1 for c in alpha if 0x0900 <= ord(c) <= 0x097F)
    if bengali / len(alpha) > 0.3:
        return "bn"
    if deva / len(alpha) > 0.3:
        return "hi"
    return fallback or "en"


def _multipart(fields: dict, filename: str, content: bytes,
               boundary: str) -> bytes:
    parts = []
    for key, value in fields.items():
        parts += [f"--{boundary}".encode(),
                  f'Content-Disposition: form-data; name="{key}"'.encode(),
                  b"", str(value).encode()]
    parts += [f"--{boundary}".encode(),
              f'Content-Disposition: form-data; name="file"; '
              f'filename="{filename}"'.encode(),
              b"Content-Type: audio/wav", b"", content,
              f"--{boundary}--".encode()]
    return b"\r\n".join(parts)


class CloudWhisperAsr(AsrEngine):
    """Cloud transcription with automatic local fallback."""

    def __init__(self, base_url: str, api_key: str, model: str,
                 local: AsrEngine | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.local = local
        self.name = f"cloud:{model}"
        self.timeout = 45.0

    def warmup(self) -> float:
        return self.local.warmup() if self.local else 0.0

    def transcribe(self, pcm, sr: int, lang: str | None = None) -> Hypothesis:
        t0 = time.perf_counter()
        try:
            text, language = self._cloud(pcm, sr, lang)
        except Exception as exc:  # noqa: BLE001 — degrade to local
            if self.local is None:
                raise
            hyp = self.local.transcribe(pcm, sr, lang=lang)
            hyp.note = ("cloud ASR unreachable — used the local model "
                        f"({type(exc).__name__})")
            return hyp
        from ..text.normalize import tokenize
        language = (language or "").split("-")[0] or lang or \
            _script_lang(text, "en")
        tokens = tokenize(text, language)
        audio_s = len(pcm) / (sr or 16000)
        return Hypothesis(
            tokens=tokens, language=language,
            confidence=round(min(1.0, len(text) / 8.0), 2) if text else 0.0,
            engine=self.name, audio_s=round(audio_s, 3),
            timings={"asr_ms": round((time.perf_counter() - t0) * 1000, 2)})

    def _cloud(self, pcm, sr: int, lang: str | None) -> tuple:
        buf = io.BytesIO()
        from ..audio.wavio import write_wav
        write_wav(buf, pcm, sr)
        boundary = "----via" + uuid.uuid4().hex
        fields = {"model": self.model}
        if lang:
            fields["language"] = lang.split("-")[0]
        body = _multipart(fields, "audio.wav", buf.getvalue(), boundary)
        headers = {"Content-Type":
                   f"multipart/form-data; boundary={boundary}",
                   "User-Agent": BROWSER_UA}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(
            self.base_url + "/audio/transcriptions", data=body,
            headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:160]
            raise RuntimeError(f"cloud ASR HTTP {exc.code}: {detail}") from exc
        return (data.get("text") or "").strip(), data.get("language")
