# 🎙️ Voice AI Assistant (VIA)

> **A real-time voice assistant that listens in six languages (including native Hindi, Bengali and Indian English), learns from every correction, and answers in well under 100 ms.**

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-82_passing-brightgreen.svg)](#-quickstart)
[![Latency](https://img.shields.io/badge/p50_latency-47ms-informational.svg)](#-performance)
[![No External Dependencies](https://img.shields.io/badge/deps-zero-9cf.svg)](#-architecture)

## ⚡ Quickstart

```bash
# 1. Clone and run the demo
git clone https://github.com/sanzizlohar/voice-ai-assistant.git
cd voice-ai-assistant
python -m voice_ai.main demo

# 2. Start the HTTP server with live dashboard
python -m voice_ai.main serve --port 8080
# → http://localhost:8080

# 3. Transcribe audio
python -m voice_ai.main transcribe speech.wav --reply-wav reply.wav

# 4. Text-to-speech
python -m voice_ai.main synth "namaste, aap kaise ho" --lang hi --out hi.wav

# 5. Run tests
python -m unittest discover -s tests -t .
```

---

## 🎬 Live Demo

<video controls autoplay loop>
  <source src="https://raw.githubusercontent.com/sanzizlohar/voice-ai-assistant/main/docs/demo_screenshot.png" type="image/png">
</video>

*Voice AI Assistant processing multilingual requests with continuous learning*

| Metric | Value |
|--------|-------|
| Voice-to-voice latency (p50) | **47 ms** end-to-end |
| Server-side processing | 22.6 ms |
| Real-time factor | **0.0096** (~100× real time) |
| Sustained throughput | **19.3 req/s** (8 workers) |
| Daily capacity | ~1.7M requests |
| WER improvement (learning) | **7.8% → 6.8%** after feedback |

| Code | Language | Script | Notes |
|------|----------|--------|-------|
| `en` | English | Latin | Includes **Indian English** dialect (*lakh*, *crore*, *prepone*) |
| `hi` | हिन्दी | Devanagari | Native end-to-end support |
| `bn` | বাংলা | Bengali | Native support with inflected forms |
| `es` | Español | Latin | Spanish |
| `fr` | Français | Latin | French |
| `de` | Deutsch | Latin | German |

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Voice Input (WAV)                          │
│                              │                                  │
│                              ▼                                  │
│                    ┌─────────────────┐                          │
│                    │   VAD Engine     │  ← Voice Activity       │
│                    │   (adaptive      │    Detection with        │
│                    │    noise floor)  │    hysteresis            │
│                    └────────┬────────┘                          │
│                             │                                   │
│                             ▼                                   │
│                    ┌─────────────────┐                          │
│                    │   ASR Engine     │  ← Whisper (optional)   │
│                    │   / Tone Codec   │    or offline fallback  │
│                    └────────┬────────┘                          │
│                             │                                   │
│                             ▼                                   │
│                    ┌─────────────────┐                          │
│                    │  Learning Layer  │  ← ConfusionModel +     │
│                    │  (Corrections)   │    HotwordSet           │
│                    └────────┬────────┘                          │
│                             │                                   │
│                             ▼                                   │
│                    ┌─────────────────┐                          │
│                    │   NLU Engine     │  ← Intent recognition   │
│                    │   (6 languages)  │    + slot extraction    │
│                    └────────┬────────┘                          │
│                             │                                   │
│                             ▼                                   │
│                    ┌─────────────────┐                          │
│                    │   TTS Engine     │  ← Coqui TTS / Edge /   │
│                    │   (reply spoken) │    offline codec        │
│                    └─────────────────┘                          │
└─────────────────────────────────────────────────────────────────┘
```

## 🔄 Continuous Learning — The Core Innovation

VIA turns systematic mishearings into an advantage:

![Continuous Learning Loop](docs/learning_loop.png)

```
User:    "note buy coffee beans"
ASR:     "note buy but coffee beans"     ← misheard
User:    [corrects via dashboard/API]
           ↓ WER alignment → confusion pair (but → buy)
Next:    engine says "but" → rewritten to "buy" automatically
```

**Key components:**
- **ConfusionModel** — Counts (wrong → right) pairs per language with time-based forgetting (6h half-life)
- **HotwordSet** — User vocabulary (names, jargon) becomes weighted hotwords for future transcriptions
- **Persistence** — Learned rules stored in SQLite WAL, survives restarts

## 📊 Performance

| Metric | Result |
|--------|--------|
| Voice-to-voice latency (p50) | **47 ms** end-to-end |
| Server-side processing | 22.6 ms |
| Real-time factor | **0.0096** (~100× real time) |
| Sustained throughput | **19.3 req/s** (8 workers) |
| Daily capacity | ~1.7M requests |
| WER improvement (learning) | **7.8% → 6.8%** after feedback |

![Dashboard Mockup](docs/dashboard_mockup.png)

## 🎮 What Can You Say?

| Say (in any supported language) | It does |
|--------------------------------|---------|
| "what time is it" / "अभी समय क्य़ा हुआ" | Answers out loud in the same language |
| "what is twelve plus thirty" | Computes and speaks the result |
| "set a timer for five minutes" / "पाँच मिनिट का टाइमर लगाओ" | Confirms the timer |
| "note buy milk tomorrow" | Stores a note |
| Anything misheard | Correct it once — **it learns and stops repeating the mistake** |

## 🔧 Tech Stack & Design Decisions

| Choice | Why |
|--------|-----|
| **Python stdlib (zero deps)** | The workload is short CPU bursts; a bounded thread pool beats frameworks here |
| **Offline tone codec** | Test double for acoustic models — words → tone sequences → decoded with Goertzel filtering. Real DSP, no downloads needed |
| **numpy (optional)** | Vectorized DFT for 4× faster decode; releases GIL for true parallelism |
| **Whisper adapter** | `faster-whisper` with int8 quantization — ~4× faster than standard |
| **Coqui TTS / Edge TTS** | Natural neural voices; falls back to offline codec gracefully |
| **SQLite (WAL)** | Zero-setup persistence with per-request commits off the hot path |
| **ThreadingHTTPServer** | Live dashboard with browser mic capture, zero dependencies |

## 🌐 HTTP API

```bash
# Transcribe audio
curl -X POST --data-binary @speech.wav \
  -H "Content-Type: audio/wav" \
  "http://localhost:8080/transcribe?session=me"

# Text-to-speech
curl -X POST -H "Content-Type: application/json" \
  -d '{"text":"hello there","lang":"en"}' \
  http://localhost:8080/tts > reply.wav

# Feed corrections (triggers learning)
curl -X POST -H "Content-Type: application/json" \
  -d '{"utterance_id":"u000001","text":"what I actually said"}' \
  http://localhost:8080/feedback

# Monitor
curl http://localhost:8080/metrics      # Prometheus format
curl http://localhost:8080/healthz       # Liveness check
curl http://localhost:8080/api/state     # Dashboard snapshot
```

## 📁 Project Structure

```
voice-ai-assistant/
├── voice_ai/
│   ├── audio/          # WAV I/O, tone codec, synthesizer, VAD
│   ├── asr/            # Engine interface, offline codec, Whisper adapter
│   ├── text/           # Language registry, dialects, normalization
│   ├── learn/          # Confusion model, hotwords, accuracy tracker
│   ├── nlu/            # Intent engine + multilingual responses
│   ├── tts/            # Engine interface, offline, Coqui TTS
│   ├── persistence/    # SQLite store (utterances, feedback, rules)
│   ├── server/         # HTTP API, live dashboard, Prometheus metrics
│   ├── pipeline.py     # Core assistant: stages, budgets, sessions
│   ├── metrics.py      # Thread-safe counters/gauges/histograms
│   └── main.py         # CLI: demo, serve, transcribe, synth, bench
├── tests/              # 82 unit + end-to-end tests
├── scripts/            # Load test, architecture diagram generator
├── deploy/             # Dockerfile, docker-compose (+Prometheus), k8s HPA
└── docs/               # Detailed usage guide
```

## 🚢 Deployment

```bash
# Docker
cd deploy
docker compose up --build          # app + Prometheus, healthchecked
docker compose exec via python -m voice_ai.main selftest

# Kubernetes
kubectl apply -f deploy/k8s.yaml   # 3 replicas + HPA
```

One pod sustains ~19 req/s (~1.7M/day) with p95 under 500ms.

## 📝 Real Speech Setup (Optional)

The default engine is a test double for zero-dependency demos. For real speech:

```bash
# Install Whisper for transcription
pip install faster-whisper
# Windows: pin to avoid segfaults
pip install ctranslate2==4.4.0

# Install neural TTS for natural voices
pip install edge-tts miniaudio   # Native Hindi/Bengali voices

# Start with Whisper
python -m voice_ai.main serve --port 8080 --engine whisper
```

## 🧪 Testing

```bash
# Run all tests
python -m unittest discover -s tests -t .

# Run specific test
python -m unittest tests.test_nlu.TestIndic.test_hindi_time -v

# Self-test (CI-friendly)
python -m voice_ai.main selftest
```

**82 tests, 0 failures, no network required.**

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

## 🔗 Related Projects

- [Multi-Agent Browser](https://github.com/sanzizlohar/multi-agent-browser) — 5-agent web research system
- [Finance Agent System](https://github.com/sanzizlohar/finance-agent-system) — Multi-agent fraud detection
- [AI Page Summarizer](https://github.com/sanzizlohar/ai-page-summarizer) — Chrome extension

---

**Built with ❤️ by Soumen Lohar** — A portfolio project demonstrating the full anatomy of a production voice assistant.
