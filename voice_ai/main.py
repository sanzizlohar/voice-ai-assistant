"""VIA command-line interface.

  python -m voice_ai.main demo        multilingual demo + learning loop
  python -m voice_ai.main serve       HTTP API + live web dashboard
  python -m voice_ai.main transcribe  WAV file → text (+ reply audio)
  python -m voice_ai.main synth       text → WAV (offline or Coqui)
  python -m voice_ai.main bench       continuous-learning benchmark
  python -m voice_ai.main stats       accuracy trends + learned rules
  python -m voice_ai.main selftest    CI smoke test (exit code 0/1)
"""
from __future__ import annotations

import argparse
import os
import sys
import time

from .asr.offline import OfflineCodecAsr
from .asr.wer import accuracy, wer
from .audio.synth import Channel, Synthesizer
from .pipeline import BUDGET_MS, TOTAL_BUDGET_MS, Assistant
from .persistence.store import Store
from .text.normalize import LANGUAGES
from .tts.offline import OfflineTts

GREEN = "\033[92m"
AMBER = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _enable_ansi() -> None:
    if os.name == "nt":
        os.system("")


def _c(text: str, code: str) -> str:
    return f"{code}{text}{RESET}" if sys.stdout.isatty() else str(text)


def _asr(args):
    from .asr.base import get_engine
    return get_engine(args.engine)


def build_assistant(args) -> Assistant:
    """serve/transcribe path: real engines when installed (auto)."""
    store = Store(args.db)
    return Assistant(asr_engine=_asr(args), store=store,
                     want_tts=not args.no_tts)


# --------------------------------------------------------------------- #
# demo
# --------------------------------------------------------------------- #
def _phrase_list(spec: str, per_lang: int) -> list:
    """Parse --langs entries: language codes or dialects (en-IN)."""
    out: list = []
    for entry in spec.split(","):
        entry = entry.strip()
        code = entry.split("-")[0]
        if code not in LANGUAGES:
            continue
        if entry in LANGUAGES[code].dialect_corpus:
            phrases = LANGUAGES[code].dialect_corpus[entry]
            out.extend((code, entry, p) for p in phrases[:per_lang])
        else:
            out.extend((code, "", p) for p in LANGUAGES[code].corpus[:per_lang])
    return out


def cmd_demo(args) -> int:
    _enable_ansi()
    # the demo speaks the tone-encoded corpus: keep both engines offline
    # (real Whisper would hear beeps, SAPI is wasted on them)
    a = Assistant(asr_engine=OfflineCodecAsr(), tts_engine=OfflineTts(),
                  llm_engine=False, store=Store(args.db))
    warm = a.warmup()
    if warm["total_s"] > 0.05:
        print(f" engines warmed in {warm['total_s']}s "
              f"(asr {warm['asr_s']}s / tts {warm['tts_s']}s)")

    channel = Channel(error_rate=args.noise, snr_db=24.0, seed=args.seed)
    syn = Synthesizer(channel)
    phrases = _phrase_list(args.langs, args.per_lang)

    print(f"\n {_c('VOICE AI ASSISTANT — LIVE DEMO', BOLD)}"
          f"  (engine={a.asr.name}, injected confusion channel "
          f"{args.noise:.0%})")
    print(f" {'─' * 78}")

    rounds: list = []
    for rnd in (1, 2):
        total_wer = 0.0
        n_words = 0
        passes = 2 if rnd == 1 else 1  # users repeat themselves → rules hit
        for p_i in range(passes):
            for lang, dialect, phrase in phrases:
                pcm, meta = syn.utterance(lang, phrase, dialect)
                r = a.process(pcm, 16000, session_id=f"demo-r{rnd}",
                              reference=meta["words"], dialect=dialect)
                label = f"{lang}-{dialect}" if dialect else lang
                w = wer(meta["words"], r["tokens"])
                total_wer += w * len(meta["words"])
                n_words += len(meta["words"])
                if rnd == 1:
                    # the user corrects every mistake → model learns
                    a.correct(r["id"], " ".join(meta["words"]))
                if p_i == 0 and passes == 1 or (rnd == 2 and p_i == 0) \
                        or (rnd == 1 and p_i == 0):
                    mark = _c("fixed", GREEN) if r["rules_fired"] else ""
                    heard = r["transcript"]
                    if r["text"] != heard:
                        heard = f"{heard} {_c('→ ' + r['text'], GREEN)}"
                    lat = (_c(f"{r['total_ms']:.0f}ms", GREEN)
                           if r["budget_ok"]
                           else _c(f"{r['total_ms']:.0f}ms", RED))
                    print(f" r{rnd} [{label}] {heard[:52]:<52} "
                          f"{r['intent']:<9} {lat}"
                          f"{(' ' + mark) if mark else ''}")
        rounds.append(total_wer / max(n_words, 1))

    acc1 = 1 - rounds[0]
    acc2 = 1 - rounds[1]
    rules = len(a.confusion.rules())
    print(f" {'─' * 78}")
    print(f" accuracy  round1 {acc1:6.1%}  →  round2 {acc2:6.1%}"
          f"   ({(acc2 - acc1) * 100:+.1f} pp from user feedback)"
          f"   rules {rules}")
    st = a.stats()
    tot = st["stages"].get("pipeline.total_ms", {})
    print(f" latency   p50 {tot.get('p50', 0):.0f}ms"
          f"   p95 {tot.get('p95', 0):.0f}ms"
          f"   max {tot.get('max', 0):.0f}ms   (budget {TOTAL_BUDGET_MS:.0f}ms)")
    rtf = st["stages"].get("pipeline.rtf", {})
    print(f" rtf       avg {rtf.get('avg', 0):.3f}"
          f"  (responses stream ~{1 / max(rtf.get('avg', 1), 1e-6):.0f}x"
          f" faster than real time)")
    langs = a.stats()["learning"]["accuracy"].get("by_lang", {})
    per = "  ".join(f"{l} {v:.0%}" for l, v in sorted(langs.items()))
    print(f" per-lang  {per}")
    print(f" {'─' * 78}")
    a.store.close()
    return 0


# --------------------------------------------------------------------- #
# serve
# --------------------------------------------------------------------- #
def cmd_serve(args) -> int:
    _enable_ansi()
    a = build_assistant(args)
    warm = a.warmup()
    print(f" asr engine {a.asr.name} · tts {a.tts.name if a.tts else 'off'}"
          f" · warmed in {warm['total_s']}s")
    from .server.api import Server
    server = Server(a, port=args.port, workers=args.workers)
    print(f" dashboard  → http://localhost:{server.port}"
          f"   (Ctrl+C to stop)")
    print(f" api        → POST /transcribe · POST /tts · POST /feedback"
          f"\n              GET  /metrics · /healthz · /api/state")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        a.store.close()
    return 0


# --------------------------------------------------------------------- #
# transcribe / synth
# --------------------------------------------------------------------- #
def cmd_transcribe(args) -> int:
    from .audio.wavio import read_wav
    pcm, sr = read_wav(args.wav)
    a = build_assistant(args)
    a.warmup()
    r = a.process(pcm, sr, session_id=args.session, lang=args.lang,
                  want_audio=bool(args.reply_wav))
    if "error" in r:
        print(f" {r['error']}")
        return 1
    print(f" language   {r['language']}  engine {r['engine']}"
          f"  confidence {r['confidence']:.2f}")
    print(f" transcript {r['transcript']}")
    if r["text"] != r["transcript"]:
        print(f" adapted    {r['text']}   "
              f"(rules: {', '.join(f'{a}→{b}' for a, b, _ in r['rules_fired'])})")
    print(f" intent     {r['intent']}  →  {r['reply']}")
    print(f" latency    {r['total_ms']}ms   "
          f"(vad {r['stages']['vad_ms']} · asr {r['stages']['asr_ms']}"
          f" · adapt {r['stages']['adapt_ms']} · nlu {r['stages']['nlu_ms']}"
          f" · tts {r['stages']['tts_ms']})")
    if args.reply_wav:
        import base64
        with open(args.reply_wav, "wb") as fh:
            fh.write(base64.b64decode(r["audio_b64"]))
        print(f" reply wav  {args.reply_wav}")
    a.store.close()
    return 0


def cmd_synth(args) -> int:
    from .tts.base import get_tts
    tts = get_tts(args.tts_engine)
    tts.warmup()
    pcm, sr = tts.synthesize(args.text, args.lang)
    from .audio.wavio import write_wav
    write_wav(args.out, pcm, sr)
    print(f" wrote {args.out} ({len(pcm) / sr:.2f}s @ {sr} Hz,"
          f" engine {tts.name})")
    return 0


# --------------------------------------------------------------------- #
# bench — the continuous-learning benchmark
# --------------------------------------------------------------------- #
def cmd_bench(args) -> int:
    _enable_ansi()
    a = Assistant(asr_engine=OfflineCodecAsr(), tts_engine=OfflineTts(),
                  llm_engine=False, store=Store(args.db))
    channel = Channel(error_rate=args.noise, snr_db=24.0, seed=args.seed)
    syn = Synthesizer(channel)
    phrases = _phrase_list(",".join(LANGUAGES), 10 ** 6)  # full corpus
    phrases += _phrase_list("en-IN", 10 ** 6)

    def run_round(learn: bool) -> tuple[float, float]:
        err = words = 0.0
        lat = n_utts = 0
        passes = 2 if learn else 1  # users repeat themselves; feedback sticks
        for p_i in range(passes):
            for lang, dialect, phrase in phrases:
                pcm, meta = syn.utterance(lang, phrase, dialect)
                r = a.process(pcm, 16000, session_id=f"bench-{learn}",
                              reference=meta["words"])
                if not learn or p_i == passes - 1:
                    err += (wer(meta["words"], r["tokens"])
                            * len(meta["words"]))
                    words += len(meta["words"])
                    lat += r["total_ms"]
                    n_utts += 1
                if learn:
                    a.correct(r["id"], " ".join(meta["words"]))
        return err / max(words, 1), lat / max(n_utts, 1)

    print(f" continuous-learning benchmark — {len(phrases)} utterances ×"
          f" {len(set(l for l, _, _ in phrases))} languages, confusion"
          f" channel {args.noise:.0%}")
    w1, l1 = run_round(learn=True)
    w2, l2 = run_round(learn=False)
    a1, a2 = 1 - w1, 1 - w2
    rules = a.confusion.rules()
    print(f" round 1 (cold)        accuracy {a1:6.1%}   WER {w1:5.1%}"
          f"   avg latency {l1:.0f}ms")
    print(f" round 2 (after user feedback)")
    print(f"                       accuracy {a2:6.1%}   WER {w2:5.1%}"
          f"   avg latency {l2:.0f}ms")
    print(f" improvement           {(a2 - a1) * 100:+.1f} pp accuracy from"
          f" {len(rules)} learned rules")
    print(" top rules: " + ", ".join(f"{l}:{w}→{r}" for l, w, r, _c2, _c3
                                      in rules[:8]))
    a.store.close()
    return 0


# --------------------------------------------------------------------- #
# stats / selftest
# --------------------------------------------------------------------- #
def cmd_stats(args) -> int:
    store = Store(args.db)
    rows = store.accuracy_rows()
    counts = store.counts()
    print(f" db {args.db}: {counts['utterances']} utterances, "
          f"{counts['feedback']} feedback, {counts['rules']} learned rules")
    if rows:
        accs = [1 - w for _, _, w in rows]
        half = len(accs) // 2
        old = accs[:half] or accs
        new = accs[half:] or accs
        print(f" accuracy {sum(old) / len(old):.1%} → {sum(new) / len(new):.1%}"
              f" over {len(accs)} labeled utterances")
    for lang, lhs, rhs, score, conf in store.load_rules("confusion")[:12]:
        print(f" rule [{lang}] hear {lhs!r} → say {rhs!r}"
              f"  (evidence {score:.1f}, conf {conf:.0%})")
    for u in store.recent_utterances(8):
        print(f"  [{u['lang']}] {u['final']!r} → {u['intent']}"
              f" {u['latency_ms']:.0f}ms")
    store.close()
    return 0


def cmd_brain(args) -> int:
    from .llm.config import (PROVIDERS, clear_config, engine_from_config,
                             load_config, probe, save_config)
    if args.clear:
        print(f" brain cleared: {clear_config()}")
        return 0
    if args.provider:
        try:
            cfg = save_config(args.provider, api_key=args.key or "",
                              model=args.model or "",
                              base_url=args.base_url or "")
        except ValueError as exc:
            print(f" error: {exc}")
            return 1
        engine = engine_from_config(cfg)
        status = probe(engine)
        print(f" brain saved: {engine.name} @ {cfg['base_url']}")
        print(f" reachable: {status['ok']}"
              + ("" if status["ok"] else f" ({status.get('error')})"))
        return 0 if status["ok"] else 1
    cfg = load_config()
    print(" providers:")
    for name, spec in PROVIDERS.items():
        print(f"   {name:11} {spec['label']}  — {spec['hint']}")
    if cfg:
        print(f" saved: {cfg['provider']} · {cfg['model']} @ "
              f"{cfg['base_url']} (key {'set' if cfg['api_key'] else 'none'})")
    else:
        print(" saved: none — use --provider/--key/--model, or the "
              "dashboard Brain panel")
    return 0


def cmd_ask(args) -> int:
    from .asr.offline import OfflineCodecAsr
    a = Assistant(asr_engine=OfflineCodecAsr(), store=Store(":memory:"),
                  want_tts=False)
    a.warmup()
    r = a.process_text(args.question, session_id="cli", want_audio=False)
    if r.get("error"):
        print(f" {r['error']}")
        return 1
    print(f" [{r['language']}/{r['intent']}] {r['reply']}")
    if r.get("tools"):
        print(f" tools used: {', '.join(r['tools'])}")
    if r.get("note"):
        print(f" note: {r['note']}")
    a.store.close()
    return 0


def cmd_selftest(args) -> int:
    _enable_ansi()
    failures: list[str] = []

    from .asr.offline import OfflineCodecAsr
    from .tts.offline import OfflineTts
    a = Assistant(asr_engine=OfflineCodecAsr(), tts_engine=OfflineTts(),
                  llm_engine=False, store=Store(":memory:"),
                  want_tts=True)
    a.warmup()
    syn = Synthesizer(Channel(error_rate=0.0, snr_db=26.0, seed=3))

    # 1. recognition roundtrip on a multi-language sample
    for lang, phrase in (("en", "what time is it"),
                         ("en-IN", "note pay the electricity bill"),
                         ("es", "que hora es"),
                         ("fr", "quelle heure est il"),
                         ("de", "wie viel uhr ist es"),
                         ("hi", "अभी समय क्या हुआ"),
                         ("bn", "এখন কয়টা বাজে")):
        dialect = "en-IN" if lang == "en-IN" else ""
        code = "en" if lang == "en-IN" else lang
        pcm, meta = syn.utterance(code, phrase, dialect)
        r = a.process(pcm, 16000, session_id="selftest",
                      reference=meta["words"])
        if r.get("tokens") != meta["words"]:
            failures.append(f"roundtrip {lang}: {r.get('text')!r}")
        if r.get("intent") == "fallback":
            failures.append(f"intent {lang}: fallback for {phrase!r}")

    # 2. learning improves a repeated systematic error
    ch = Channel(error_rate=0.9, snr_db=24.0, seed=11)
    syn2 = Synthesizer(ch)
    worsened = []
    pcm, meta = syn2.utterance("en", "note buy coffee beans")
    r = a.process(pcm, 16000, session_id="learn", reference=meta["words"])
    before = wer(meta["words"], r["tokens"])
    if before > 0:
        a.correct(r["id"], " ".join(meta["words"]))
        pcm, meta = syn2.utterance("en", "note buy coffee beans")
        r2 = a.process(pcm, 16000, session_id="learn",
                       reference=meta["words"])
        after = wer(meta["words"], r2["tokens"])
        if after >= before:
            worsened.append(f"no learning: wer {before:.2f}→{after:.2f}")
    else:
        worsened.append("channel produced no error to learn from")

    # 3. latency budget
    st = a.stats()
    tot = st["stages"].get("pipeline.total_ms", {})
    p95 = tot.get("p95", 0.0)
    if p95 > TOTAL_BUDGET_MS:
        failures.append(f"latency p95 {p95:.0f}ms > budget {TOTAL_BUDGET_MS:.0f}ms")

    # 4. TTS roundtrip: what it says, it can hear back
    pcm_tts, sr_tts = a.tts.synthesize("what time is it", "en")
    r3 = a.process(pcm_tts, sr_tts, session_id="tts")
    if "what time is it" not in " ".join(r3.get("tokens", [])):
        failures.append(f"tts roundtrip: {r3.get('transcript')!r}")

    print(f" selftest: utterances {st['utterances']}"
          f"  latency p95 {p95:.0f}ms/{TOTAL_BUDGET_MS:.0f}ms"
          f"  rules {st['learning']['active']}")
    if failures:
        for f in failures:
            print(f" FAIL: {f}")
        print(" SELFTEST: FAIL")
        return 1
    print(" SELFTEST: PASS")
    return 0


# --------------------------------------------------------------------- #
def main(argv: list | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="vai", description="Voice AI Assistant — real-time "
        "multi-language speech recognition, continuous learning, "
        "production serving")

    # shared flags accepted BOTH before and after the subcommand
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--engine", default=None,
                        help="asr engine: auto | offline | whisper")
    common.add_argument("--db", default=None,
                        help="sqlite file (default in-memory)")
    common.add_argument("--no-tts", action="store_true")
    p._via_common = common

    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("demo", parents=[common],
                       help="multilingual demo with learning loop")
    d.add_argument("--noise", type=float, default=0.15)
    d.add_argument("--seed", type=int, default=42)
    d.add_argument("--langs", default="en,en-IN,es,fr,de,hi,bn")
    d.add_argument("--per-lang", type=int, default=5)
    d.set_defaults(func=cmd_demo)

    s = sub.add_parser("serve", parents=[common], help="HTTP API + dashboard")
    s.add_argument("--port", type=int, default=8080)
    s.add_argument("--workers", type=int, default=8)
    s.set_defaults(func=cmd_serve)

    t = sub.add_parser("transcribe", parents=[common], help="WAV file → text")
    t.add_argument("wav")
    t.add_argument("--lang", default=None)
    t.add_argument("--session", default="cli")
    t.add_argument("--reply-wav", default=None,
                   help="write the spoken reply to this path")
    t.set_defaults(func=cmd_transcribe)

    y = sub.add_parser("synth", parents=[common], help="text → WAV")
    y.add_argument("text")
    y.add_argument("--lang", default="en")
    y.add_argument("--out", default="out.wav")
    y.add_argument("--tts-engine", default="auto")
    y.set_defaults(func=cmd_synth)

    b = sub.add_parser("bench", parents=[common], help="continuous-learning benchmark")
    b.add_argument("--noise", type=float, default=0.15)
    b.add_argument("--seed", type=int, default=42)
    b.set_defaults(func=cmd_bench)

    st = sub.add_parser("stats", parents=[common], help="accuracy trends + rules from db")
    st.set_defaults(func=cmd_stats)

    sf = sub.add_parser("selftest", parents=[common], help="pipeline smoke test (exit 0/1)")
    sf.set_defaults(func=cmd_selftest)

    br = sub.add_parser("brain", parents=[common],
                        help="LLM brain: show / set / clear provider")
    br.add_argument("--provider", default=None,
                    help="ollama | groq | openai | openrouter | custom")
    br.add_argument("--key", default=None, help="API key for the provider")
    br.add_argument("--model", default=None, help="model name")
    br.add_argument("--base-url", default=None,
                    help="custom OpenAI-compatible base url")
    br.add_argument("--clear", action="store_true",
                    help="remove the saved brain")
    br.set_defaults(func=cmd_brain)

    ak = sub.add_parser("ask", parents=[common],
                        help="ask one question (uses the LLM brain + tools)")
    ak.add_argument("question")
    ak.set_defaults(func=cmd_ask)

    args = p.parse_args(argv)
    args.engine = args.engine or "auto"
    args.db = args.db or ":memory:"
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
