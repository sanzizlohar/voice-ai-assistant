# VIA — the plain-English guide

New to voice pipelines, WER, or "continuous learning"? This walks through
everything the assistant does, in order, without assuming prior knowledge.

## 1. What happens when you speak

Say you hold the mic button and say (in Hindi):

> नमस्ते आप कैसे हो

Your browser records raw sound waves and encodes them as a **WAV file** —
a long list of numbers, one per audio sample (16,000 per second). That
file travels to the assistant, which runs five stages:

### Stage 1 — VAD (voice activity detection)

Before spending effort on recognition, the assistant finds *where the
speech actually is*. It measures loudness in 10 ms chunks, estimates the
background noise level, and opens a "gate" when sound is clearly louder
than the room. Two subtleties make it feel natural:

- **Hysteresis** — the gate opens at +6 dB above the noise floor but only
  closes below +3 dB, so a breathy pause doesn't chop words in half.
- **Gap bridging** — silences shorter than 150 ms are *kept*, because
  real speech has rhythm: tiny pauses inside and between words carry
  meaning. Only the long silence before and after you speak is trimmed.

### Stage 2 — ASR (automatic speech recognition)

This stage turns audio into text tokens. The assistant doesn't care
*which* engine does it:

- **Offline engine (default)** — words are rendered as short melodies:
  2–4 pure tones from an 8-note scale, one melody per word. Recognition
  is real signal processing: the decoder measures which frequency
  dominates each 30 ms frame (Goertzel filtering, or a vectorized numpy
  version), groups tones into words, and looks them up. If a tone got
  corrupted, it finds the *nearest* known word — exactly how a human
  "mishears" one sound for another. This is why the whole system runs
  with zero downloads: it's a test double that exercises every code path
  a real engine would.
- **Whisper engine** — if you `pip install faster-whisper`, the exact
  same stage runs OpenAI's Whisper model (int8-quantized for speed). Your
  learned vocabulary is injected as `initial_prompt` so the model itself
  is biased toward words you use.

Either way the stage also **detects the language** (all 6 are scored; the
session's recent language gets a small bonus so detection never
flickers mid-conversation).

### Stage 3 — the adaptive layer

Here the assistant applies what it has *learned from you*. Two mechanisms:

- **Confusion model** — every time you correct a transcript, the system
  aligns the wrong text with your correction (word-level edit distance)
  and records pairs like "I keep hearing `but` when the user says
  `buy`". After two observations at ≥ 50% confidence it becomes a rule:
  future `but`s in that context are rewritten to `buy` automatically.
  Evidence fades with a 6-hour half-life, so the model tracks how you
  speak *now*.
- **Hotwords** — corrections often contain words the engine never knew
  (a friend's name, jargon). Those become weighted hotwords, matched
  fuzzily (small spelling distance) into future transcripts.

### Stage 4 — NLU (what did the user *want*?)

Keywords per language map the text to an intent: `time`, `math`,
`timer`, `note`, `weather`, `greet`, `help`, `thanks`, `goodbye`. Slots
are extracted (which number? which unit? what should the note say?), and
a response template renders the reply in the user's language. English
math parses spelled numbers ("what is twelve plus thirty" → 42).

### Stage 5 — reply + TTS

The reply text is spoken back — in order of preference: **Coqui TTS**
(natural neural voices, if installed), **Edge neural voices**
(native Bengali/Hindi/English, `pip install edge-tts miniaudio`,
needs internet), **your Windows system voices** (offline, English),
then the tone codec "beeps" as the universal fallback. Replies are
cached, so asking the time twice costs ~0 ms the second time.

## 2. Latency: why it's a first-class citizen

A voice assistant that takes 1–2 seconds to answer feels broken. So:

- **Every stage has a budget** (VAD ≤ 15 ms, ASR ≤ 400 ms, adapt ≤ 10 ms,
  NLU ≤ 5 ms, TTS ≤ 150 ms; total ≤ 500 ms) and every utterance records
  its actual stage times. `selftest` fails the build if p95 drifts over
  budget.
- **Warmup at boot** — engines and language codecs are built before the
  first request, so nobody pays a cold start.
- **numpy fast path** — when numpy is installed, audio analysis runs as
  matrix math (150 ms → 37 ms per utterance) and releases the GIL, so
  concurrent requests genuinely run in parallel.
- **Backpressure** — the server has a bounded worker queue; under
  overload it answers 503 + Retry-After instead of letting everyone's
  latency quietly explode.

Measured: **p50 47 ms** for a 2.4 s utterance end-to-end — roughly 100×
faster than real time (RTF 0.0096).

## 3. The learning loop, end to end

1. You speak; the transcript is stored with an ID (`u000042`).
2. The dashboard shows what it heard; you type the correction.
3. `POST /feedback {"utterance_id": "u000042", "text": "..."}` aligns
   your words against the raw hypothesis, feeds the confusion model and
   hotwords, and saves the rules to SQLite.
4. The next utterance benefits. `stats`/`bench` print the measured
   accuracy before and after.

Why counting instead of gradient descent? Because it is **explainable**
(you can print every rule and its evidence), **fast** (microseconds), and
**safe** (a bad rule decays away in hours instead of poisoning a model).

## 4. Words you'll see in the code

- **WER** — word error rate: edit distance between what was said and what
  was recognized, divided by the number of words. 0.0 is perfect.
- **RTF** — real-time factor: processing time divided by audio duration.
  0.01 means the answer is ready 100× faster than the audio itself.
- **Corpus** — the phrase list per language that demos and benchmarks
  speak (`voice_ai/text/normalize.py`).
- **Dialect** — a word-level vocabulary map (en-IN: *prepone* →
  *advance*) applied before anything else touches the text.
- **Backpressure** — rejecting work (politely, with a status code) when
  the queue is full, instead of accepting it and being slow for everyone.

## 5. Try this right now

```bash
python -m voice_ai.main demo          # watch accuracy climb as it learns
python -m voice_ai.main serve         # open http://localhost:8080, click to talk
python -m voice_ai.main bench         # the reproducible learning benchmark
```

Speak any of the corpus languages — including English with Indian
vocabulary ("i will prepone the meeting"), Hindi ("पाँच मिनट का टाइमर
लगाओ") or Bengali ("এখন কয়টা বাজে"). Correct it when it's wrong — and
watch the green "fixed" lines appear.

## 6. The brain, the hands and the eyes

The intent keywords handle the familiar commands fast and offline. But
what about "who wrote the odyssey"? That goes to the **LLM brain**:

1. Nothing matches an intent → the utterance is routed to the configured
   model (Ollama locally, or Groq/OpenAI/OpenRouter/custom via an API
   key you paste in the dashboard's Brain panel).
2. The model can answer directly, or reply with a JSON tool call.
3. The **ActionCenter** executes it — `web_search`, `read_page`,
   `open_app`, `open_url`, `sys_info`, `list_dir` — and feeds the
   observation back. Up to 3 rounds, then the final text is spoken.

Safety: the tool list is a strict allowlist; arbitrary shell commands
stay disabled unless you set `VIA_SHELL=1`; every action is written to
the auditable event stream. The "open X" fast path ("open chrome") runs
without any LLM — it's a keyword intent that launches apps directly.

## 7. Agent mode — every word goes to the brain

With a brain connected, the pipeline flips to **agent-first**: your
voice (transcribed through cloud Whisper for perfect Bengali/Hindi)
goes straight to the LLM, which may chain tools — get_time, take_note,
set_timer, web_search, read_page, open_app, search_files, read_file,
clipboard_write, linkedin_share — before speaking one natural reply.
The local intent engine stops being the primary brain and becomes the
**safety net**: if the model or network fails, the offline commands
still work exactly as before.
