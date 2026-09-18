"""The assistant pipeline: VAD → ASR → adaptive post-processing →
intent → reply → TTS, with a hard eye on voice-to-voice latency.

Every stage is timed and compared against its budget; the offline engine
answers in well under 300 ms p95 (audio of 1-3 s), which is the
difference between a conversation and a walkie-talkie. Sessions carry a
language prior with hysteresis so mid-conversation detections don't
flicker; replies are cached (identical reply text → ~0 ms TTS).
"""
from __future__ import annotations

import base64
import io
import itertools
import time
from collections import OrderedDict

from .asr.base import get_engine
from .asr.wer import accuracy, confusion_pairs, wer
from .audio.tonecodec import UNK
from .audio.vad import trim_silence
from .audio.wavio import TARGET_SR, resample, write_wav
from .learn.confusion import ConfusionModel
from .learn.tracker import AccuracyTracker
from .learn.vocab import HotwordSet
from .llm.base import LlmAgent, get_llm
from .metrics import EventLog, Metrics
from .nlu.intents import IntentEngine
from .persistence.store import Store
from .text.normalize import LANGUAGES, join_tokens, tokenize
from .tools.actions import ActionCenter
from .tts.base import get_tts

# voice-to-voice latency budget per stage (ms). The offline engine beats
# these by an order of magnitude; Whisper trades some ASR budget for
# quality — the selftest asserts the offline path stays within budget.
BUDGET_MS = {"vad": 15, "asr": 400, "adapt": 10, "nlu": 5, "tts": 150}
TOTAL_BUDGET_MS = 500.0

SESSION_CAP = 500
TTS_CACHE_CAP = 256


def _detect_text_language(text: str, fallback: str = "en") -> str:
    """Best vocabulary coverage across tokenizers picks the language."""
    best, best_score = fallback, -1.0
    for code, language in LANGUAGES.items():
        spoken = language._spoken(tokenize(text, code))
        if not spoken:
            continue
        vocab = language.vocab()
        score = sum(1 for t in spoken if t in vocab) / len(spoken)
        if score > best_score:
            best, best_score = code, score
    return best


class Session:
    def __init__(self, sid: str, language: str = "en",
                 lang_locked: bool = False):
        self.id = sid
        self.language = language
        # a session only locks its language when the user explicitly chose
        # one — otherwise ASR auto-detects every utterance (forcing "en"
        # made Whisper transcribe Bengali/Hindi speech as English)
        self.lang_locked = lang_locked
        self.turns = 0
        self.created = time.time()
        self.history: list = []

    def health(self) -> dict:
        return {"id": self.id, "language": self.language,
                "turns": self.turns,
                "age_s": round(time.time() - self.created, 1)}


class Assistant:
    def __init__(self, asr_engine=None, tts_engine=None,
                 store: Store | None = None, metrics: Metrics | None = None,
                 events: EventLog | None = None, want_tts: bool = True,
                 default_language: str = "en",
                 llm_engine=None, actions=None):
        self.asr = asr_engine or get_engine("auto")
        self.tts = tts_engine if tts_engine is not None else (
            get_tts("auto") if want_tts else None)
        self.store = store or Store()
        self.metrics = metrics or Metrics()
        self.events = events or EventLog()
        self.actions = actions or ActionCenter(events=self.events)
        self.actions.note_sink = self._persist_agent_note
        self.nlu = IntentEngine(actions=self.actions)
        if llm_engine is False:
            self.llm = None            # explicit hermetic/offline mode
        else:
            self.llm = llm_engine if llm_engine is not None else get_llm()
        self.agent = (LlmAgent(self.llm, self.actions)
                      if self.llm is not None else None)
        self.default_language = default_language

        self.confusion = ConfusionModel()
        self.hotwords = HotwordSet()
        self.tracker = AccuracyTracker()
        self._load_learned()

        self._sessions: OrderedDict = OrderedDict()
        self._tts_cache: OrderedDict = OrderedDict()
        self._ids = itertools.count(1)
        self.t0 = time.time()

    # ---------------------------------------------------------------- #
    def _load_learned(self) -> None:
        for lang, lhs, rhs, score, conf in self.store.load_rules("confusion"):
            self.confusion.counts[(lang, lhs, rhs)] = score
            self.confusion.totals[(lang, lhs)] = \
                self.confusion.totals.get((lang, lhs), 0.0) + score
        for lang, term, _rhs, score, _conf in self.store.load_rules("hotword"):
            self.hotwords.boost(lang, term, score)

    def warmup(self) -> dict:
        t0 = time.perf_counter()
        asr_s = self.asr.warmup()
        tts_s = self.tts.warmup() if self.tts else 0.0
        # pre-build language codecs so the first request pays no cold start
        codec = getattr(self.asr, "codec", None)
        if codec:
            for code in LANGUAGES:
                codec(code)
        if self.tts is not None:
            tts_codec = getattr(self.tts, "codec", None)
            if tts_codec:
                for code in LANGUAGES:
                    tts_codec(code)
        return {"asr_s": round(asr_s, 2), "tts_s": round(tts_s, 2),
                "total_s": round(time.perf_counter() - t0, 2)}

    def session(self, sid: str, lang: str | None = None) -> Session:
        sess = self._sessions.get(sid)
        if sess is None:
            if len(self._sessions) >= SESSION_CAP:
                self._sessions.popitem(last=False)
            sess = Session(sid, lang or self.default_language,
                           lang_locked=bool(lang))
            self._sessions[sid] = sess
        else:
            self._sessions.move_to_end(sid)
            if lang:
                sess.language = lang
                sess.lang_locked = True
        return sess

    # ---------------------------------------------------------------- #
    # Main entry: audio → reply (+ audio)
    # ---------------------------------------------------------------- #
    def process(self, pcm, sr: int, session_id: str = "default",
                lang: str | None = None, want_audio: bool = True,
                reference: list[str] | None = None,
                dialect: str = "") -> dict:
        t_total = time.perf_counter()
        stages: dict = {}

        # 1. VAD — trim silence, resample if needed
        t0 = time.perf_counter()
        if sr != TARGET_SR:
            pcm = resample(pcm, sr, TARGET_SR)
            sr = TARGET_SR
        speech, speech_s = trim_silence(pcm, sr)
        stages["vad_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        if not speech:
            self.metrics.inc("utterances.no_speech")
            return {"id": self._next_id(), "error": "no_speech",
                    "stages": stages,
                    "total_ms": round((time.perf_counter() - t_total) * 1000, 2)}

        sess = self.session(session_id, lang)

        # 2. ASR — auto-detect the language unless the user locked one
        t0 = time.perf_counter()
        hyp = self.asr.transcribe(
            speech, sr, lang=sess.language if sess.lang_locked else None)
        stages["asr_ms"] = round((time.perf_counter() - t0) * 1000, 2)

        # language stickiness: keep only languages the assistant speaks —
        # a wrong ASR guess (e.g. 'pt' for a Bengali clip) never overrides
        detected = hyp.language.split("-")[0]
        if detected in LANGUAGES:
            sess.language = detected

        # 3. adaptive post-processing (learned confusions + hotwords)
        t0 = time.perf_counter()
        tokens, fired = self.confusion.apply(hyp.tokens, sess.language)
        tokens, hw_fired = self.hotwords.apply(tokens, sess.language)
        fired = fired + hw_fired
        stages["adapt_ms"] = round((time.perf_counter() - t0) * 1000, 2)

        # 4. reply — agent-first when a brain is connected, local intents
        # otherwise (and as the fallback when the agent fails)
        tools: list = []
        note = hyp.note
        t0 = time.perf_counter()
        intent, slots, reply = self.nlu.handle(
            tokens, sess.language,
            transcript_display=join_tokens(
                [t for t in tokens if t != UNK], sess.language))
        stages["nlu_ms"] = round((time.perf_counter() - t0) * 1000, 2)

        if self.agent is not None:
            question = join_tokens([t for t in hyp.tokens if t != UNK],
                                   sess.language)
            chat = self._maybe_chat(question, sess.language, stages)
            if chat:
                intent, reply = "chat", chat["reply"]
                tools = chat.get("tools", [])
                if chat.get("note"):
                    note = (note + " " + chat["note"]).strip()

        # 5. TTS (cached)
        audio_b64 = self._speak(reply, sess.language, stages, want_audio)

        total_ms = round((time.perf_counter() - t_total) * 1000, 2)
        stages["total_ms"] = total_ms

        utt_id = self._next_id()
        w = wer(reference, tokens) if reference is not None else None
        if w is not None:
            self.tracker.update(sess.language, accuracy(reference, tokens))

        for name, val in stages.items():
            self.metrics.observe(f"pipeline.{name}", val)
        if speech_s:
            self.metrics.observe("pipeline.rtf",
                                 total_ms / 1000.0 / max(speech_s, 1e-6))
        self.metrics.inc("utterances.processed")

        result = {
            "id": utt_id,
            "session_id": session_id,
            "transcript": join_tokens([t for t in hyp.tokens if t != UNK],
                                      sess.language),
            "tokens": tokens,
            "hypothesis_tokens": hyp.tokens,
            "text": join_tokens([t for t in tokens if t != UNK],
                                sess.language),
            "language": sess.language,
            "dialect": dialect,
            "confidence": hyp.confidence,
            "engine": hyp.engine,
            "intent": intent,
            "slots": slots,
            "reply": reply,
            "audio_b64": audio_b64,
            "audio_s": round(speech_s, 3),
            "stages": stages,
            "total_ms": total_ms,
            "rtf": round(total_ms / 1000.0 / max(speech_s, 1e-6), 4),
            "rules_fired": [list(f) for f in fired],
            "tools": tools,
            "wer": round(w, 4) if w is not None else None,
            "budget_ok": total_ms <= TOTAL_BUDGET_MS,
            "note": note,
        }
        sess.turns += 1
        sess.history.append({"id": utt_id, "language": sess.language,
                             "intent": intent, "total_ms": total_ms})
        if self.store:
            self.store.insert_utterance({
                "id": utt_id, "session_id": session_id, "ts": time.time(),
                "lang": sess.language, "audio_ms": round(speech_s * 1000, 1),
                "hypothesis": " ".join(hyp.tokens),
                "final": " ".join(tokens), "intent": intent,
                "reply": reply, "wer": result["wer"],
                "latency_ms": total_ms, "engine": hyp.engine,
                "dialect": dialect})
            self.store.upsert_session(session_id, sess.language, sess.turns)
        self.events.add("info", "pipeline", "utterance",
                        f"{intent} · {result['text'][:48]} · {total_ms:.0f}ms",
                        correlation_id=utt_id)
        return result

    def _speak(self, reply: str, lang: str, stages: dict,
               want_audio: bool = True) -> str | None:
        """Reply text → cached TTS → base64 WAV for the API."""
        if self.tts is None or not want_audio:
            return None
        t0 = time.perf_counter()
        cached = self._tts_cache.get((lang, reply))
        if cached is not None:
            self.metrics.inc("tts.cache_hits")
            pcm_out, sr_out = cached
            stages["tts_ms"] = 0.0
        else:
            pcm_out, sr_out = self.tts.synthesize(reply, lang)
            stages["tts_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            self._tts_cache[(lang, reply)] = (pcm_out, sr_out)
            if len(self._tts_cache) > TTS_CACHE_CAP:
                self._tts_cache.popitem(last=False)
            self.metrics.inc("tts.synths")
        buf = io.BytesIO()
        write_wav(buf, pcm_out, sr_out)
        return base64.b64encode(buf.getvalue()).decode("ascii")

    # ---------------------------------------------------------------- #
    # Type-in path: same adapt → intent → reply pipeline, no ASR
    # ---------------------------------------------------------------- #
    def process_text(self, text: str, session_id: str = "default",
                     lang: str | None = None,
                     want_audio: bool = True) -> dict:
        """Understand typed text with the exact pipeline a voice utterance
        takes after ASR — useful without a mic and for quick testing."""
        t_total = time.perf_counter()
        stages: dict = {}
        sess = self.session(session_id, lang)
        lang = _detect_text_language(text, sess.language)
        sess.language = lang

        t0 = time.perf_counter()
        raw = tokenize(text, lang)
        tokens, fired = self.confusion.apply(raw, lang)
        tokens, hw_fired = self.hotwords.apply(tokens, lang)
        fired = fired + hw_fired
        stages["adapt_ms"] = round((time.perf_counter() - t0) * 1000, 2)

        t0 = time.perf_counter()
        intent, slots, reply = self.nlu.handle(
            tokens, lang, transcript_display=join_tokens(
                [t for t in tokens if t != UNK], lang))
        stages["nlu_ms"] = round((time.perf_counter() - t0) * 1000, 2)

        # agent-first: with a brain connected, every request goes through
        # the agent (tools included); local intent answer stands only as
        # the fallback when the agent fails
        tools: list = []
        if self.agent is not None:
            chat = self._maybe_chat(text, lang, stages)
            if chat:
                intent, reply = "chat", chat["reply"]
                tools = chat.get("tools", [])

        audio_b64 = self._speak(reply, lang, stages, want_audio)
        total_ms = round((time.perf_counter() - t_total) * 1000, 2)
        stages["total_ms"] = total_ms

        utt_id = self._next_id()
        self.metrics.inc("text.utterances")
        for name, val in stages.items():
            self.metrics.observe(f"pipeline.{name}", val)

        sess.turns += 1
        sess.history.append({"id": utt_id, "language": lang,
                             "intent": intent, "total_ms": total_ms})
        if self.store:
            self.store.insert_utterance({
                "id": utt_id, "session_id": session_id, "ts": time.time(),
                "lang": lang, "audio_ms": 0, "hypothesis": " ".join(raw),
                "final": " ".join(tokens), "intent": intent, "reply": reply,
                "wer": None, "latency_ms": total_ms, "engine": "text",
                "dialect": ""})
            self.store.upsert_session(session_id, lang, sess.turns)
        self.events.add("info", "pipeline", "text",
                        f"{intent} · {text[:48]} · {total_ms:.0f}ms",
                        correlation_id=utt_id)
        return {
            "id": utt_id, "session_id": session_id,
            "transcript": text, "tokens": tokens,
            "hypothesis_tokens": raw,
            "text": join_tokens([t for t in tokens if t != UNK], lang),
            "language": lang, "dialect": "", "confidence": 1.0,
            "engine": "text", "audio_s": 0.0, "stages": stages,
            "total_ms": total_ms, "rtf": 0.0,
            "rules_fired": [list(f) for f in fired],
            "tools": tools,
            "wer": None, "budget_ok": total_ms <= TOTAL_BUDGET_MS,
            "intent": intent, "slots": slots, "reply": reply,
            "audio_b64": audio_b64,
        }

    # ---------------------------------------------------------------- #
    # Feedback → continuous learning
    # ---------------------------------------------------------------- #
    def correct(self, utterance_id: str, corrected_text: str) -> dict:
        row = self.store.get_utterance(utterance_id) if self.store else None
        if row is None:
            return {"error": "unknown_utterance_id"}
        hyp_tokens = (row["hypothesis"] or "").split()
        ref_tokens = corrected_text.lower().split()
        lang = (row["lang"] or "en").split("-")[0]

        taken = self.confusion.observe(lang, ref_tokens, hyp_tokens)
        self.hotwords.observe_correction(
            lang, ref_tokens, LANGUAGES[lang].vocab())

        fixed, _ = self.confusion.apply(hyp_tokens, lang)
        fixed, _ = self.hotwords.apply(fixed, lang)
        wer_before = wer(ref_tokens, hyp_tokens)
        wer_after = wer(ref_tokens, fixed)
        learned = [[hw, rw] for hw, rw in confusion_pairs(ref_tokens,
                                                          hyp_tokens)]

        rows = [(l, w, r, c, conf) for l, w, r, c, conf in
                self.confusion.rules()]
        self.store.save_rules("confusion", rows)
        self.store.save_rules("hotword",
                              [(l, term, "", w, 0.0)
                               for l, wmap in self.hotwords.terms.items()
                               for term, w in wmap.items()])
        self.store.insert_feedback(utterance_id, corrected_text)
        self.metrics.inc("feedback.count")
        self.events.add("info", "learn", "feedback",
                        f"{utterance_id}: {len(rows)} active rules, "
                        f"wer {wer_before:.2f}→{wer_after:.2f}",
                        correlation_id=utterance_id)
        return {"utterance_id": utterance_id, "observations": taken,
                "rules_active": len(rows),
                "learned": learned,
                "wer_before": round(wer_before, 4),
                "wer_after": round(wer_after, 4)}

    # ---------------------------------------------------------------- #
    # Brain (LLM): general questions + tool-driven tasks
    # ---------------------------------------------------------------- #
    def _maybe_chat(self, question: str, lang: str, stages: dict) -> dict:
        """Route an unhandled utterance to the LLM agent. Returns
        {"reply", "tools", "note"?} or None when no brain is configured
        (the intent fallback reply stands)."""
        if self.agent is None:
            return None
        t0 = time.perf_counter()
        try:
            out = self.agent.answer(question, lang)
        except Exception as exc:  # noqa: BLE001 — degrade gracefully
            self.events.add("warning", "llm", "chat_failed",
                            f"{type(exc).__name__}: {exc}"[:160])
            return None
        stages["llm_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        self.metrics.inc("llm.chats")
        self.metrics.observe("llm.ms", stages["llm_ms"])
        self.events.add("info", "llm", "chat",
                        f"{question[:40]} → tools={out.get('tools', [])}")
        return out

    def set_llm(self, engine) -> None:
        """Hot-swap the brain (dashboard settings / CLI)."""
        self.llm = engine
        self.agent = (LlmAgent(engine, self.actions)
                      if engine is not None else None)
        self.events.add("info", "llm", "brain_set",
                        engine.name if engine else "no brain")

    def _persist_agent_note(self, text: str) -> None:
        """note_sink for the agent's take_note tool."""
        uid = self._next_id()
        if self.store:
            self.store.insert_utterance({
                "id": uid, "session_id": "agent", "ts": time.time(),
                "lang": self.default_language, "audio_ms": 0,
                "hypothesis": text, "final": text, "intent": "note",
                "reply": "Noted.", "wer": None, "latency_ms": 0,
                "engine": "agent", "dialect": ""})
        self.metrics.inc("notes.agent")
        self.events.add("info", "agent", "note", text[:80],
                        correlation_id=uid)

    # ---------------------------------------------------------------- #
    def _next_id(self) -> str:
        return f"u{next(self._ids):06d}"

    def stats(self) -> dict:
        m = self.metrics.snapshot()
        c = m["counters"]
        return {
            "uptime_s": round(time.time() - self.t0, 1),
            "utterances": (int(c.get("utterances.processed", 0))
                           + int(c.get("text.utterances", 0))),
            "no_speech": int(c.get("utterances.no_speech", 0)),
            "feedback": int(c.get("feedback.count", 0)),
            "tts_cache_hits": int(c.get("tts.cache_hits", 0)),
            "stages": {k: v for k, v in m["histograms"].items()
                       if k.startswith("pipeline.")},
            "learning": {**self.confusion.snapshot(),
                         "hotwords": self.hotwords.snapshot(),
                         "accuracy": self.tracker.snapshot()},
            "engine": {"asr": self.asr.name,
                       "tts": self.tts.name if self.tts else "disabled",
                       "llm": self.llm.name if self.llm else None},
            "sessions": len(self._sessions),
        }
