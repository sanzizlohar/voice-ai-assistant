"""Intent engine: keyword matching + slots + multilingual responses.

Deliberately simple and explainable (this project is about the voice
pipeline, not an LLM brain): priority-ordered intent keywords per
language, slot extraction for notes/timers/math, response templates from
the language registry. English additionally parses spelled-out arithmetic.
"""
from __future__ import annotations

import datetime as _dt

from ..text.normalize import LANGUAGES, join_tokens, spell_time

# order matters: most specific first
PRIORITY = ("math", "timer", "note", "weather", "greet", "time",
            "thanks", "help", "goodbye")


def _within_one_edit(a: str, b: str) -> bool:
    """True when a and b differ by at most one edit (sub/ins/del)."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = j = edits = 0
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            i += 1
            j += 1
        else:
            edits += 1
            if edits > 1:
                return False
            if len(a) == len(b):
                i += 1
            j += 1
    return True

TIMER_UNITS = {
    "en": {"second": "seconds", "seconds": "seconds", "minute": "minutes",
           "minutes": "minutes", "sec": "seconds", "min": "minutes"},
    "es": {"segundo": "seconds", "segundos": "seconds", "minuto": "minutes",
           "minutos": "minutes"},
    "fr": {"seconde": "seconds", "secondes": "seconds", "minute": "minutes",
           "minutes": "minutes"},
    "de": {"sekunde": "seconds", "sekunden": "seconds", "minute": "minutes",
           "minuten": "minutes"},
    "hi": {"सेकंड": "seconds", "मिनट": "minutes", "सेकेंड": "seconds"},
    "bn": {"সেকেন্ড": "seconds", "মিনিট": "minutes", "মিনিটের": "minutes",
           "মিনিটে": "minutes"},
}


class IntentEngine:
    def handle(self, tokens: list[str], lang: str,
               transcript_display: str = "") -> tuple:
        """Returns (intent, slots, reply_text). Keyword matching is exact
        first, then fuzzy (edit distance 1 on words ≥ 4 chars) — small
        ASR models type 'समें' for 'समय' and the intent should survive."""
        language = LANGUAGES[lang]
        low = [t.lower() for t in tokens]

        for intent in PRIORITY:
            kws = language.keywords.get(intent, [])
            hit = next((k for k in kws if k in low), None)
            if hit is None:
                hit = next((k for t in low if len(t) >= 4
                            for k in kws if _within_one_edit(t, k)), None)
            if hit is None:
                continue
            handler = getattr(self, f"_intent_{intent}", None)
            if handler:
                got = handler(low, lang, hit)
                if got:
                    return got
        fallback = language.responses["fallback"][0]
        return ("fallback", {},
                fallback.replace("{text}", transcript_display
                                 or join_tokens(low, lang)))

    # ---------------------------------------------------------------- #
    def _intent_math(self, low, lang, hit):
        if lang != "en":
            return None
        ops = {"plus": "+", "minus": "-", "times": "*", "divided": "/",
               "multiplied": "*"}
        op_tok = next((t for t in low if t in ops), None)
        if not op_tok:
            return None
        idx = low.index(op_tok)
        a = words_to_number(low[:idx])
        b = words_to_number(low[idx + 1:])
        if a is None or b is None:
            return None
        op = ops[op_tok]
        if op == "/" and b == 0:
            reply = "Dividing by zero is not allowed, even in a demo."
            return ("math", {"a": a, "b": b, "op": op_tok}, reply)
        result = {"+": a + b, "-": a - b, "*": a * b, "/": a / b}[op]
        result = int(result) if float(result).is_integer() else round(result, 4)
        reply = (LANGUAGES["en"].responses["math"][0]
                 .replace("{a}", spell_time("en", a, 0).split()[0]
                          if a < 20 else str(a))
                 .replace("{op}", op_tok)
                 .replace("{b}", str(b))
                 .replace("{result}", str(result)))
        return ("math", {"a": a, "b": b, "op": op_tok, "result": result},
                f"{a} {op_tok} {b} is {result}.")

    def _intent_time(self, low, lang, hit):
        now = _dt.datetime.now()
        reply = (LANGUAGES[lang].responses["time"][0]
                 .replace("{time}", spell_time(lang, now.hour, now.minute)))
        return ("time", {"h": now.hour, "m": now.minute}, reply)

    def _intent_note(self, low, lang, hit):
        idx = low.index(hit)
        text = join_tokens(low[idx + 1:], lang)
        if not text:
            return None
        reply = (LANGUAGES[lang].responses["note"][0]
                 .replace("{text}", text))
        return ("note", {"text": text}, reply)

    def _intent_timer(self, low, lang, hit):
        units = TIMER_UNITS.get(lang, TIMER_UNITS["en"])
        unit = next((t for t in low if t in units), None)
        if not unit:
            return None
        idx = low.index(unit)
        n = words_to_number_local(low[:idx], lang)
        if n is None or n <= 0:
            return None
        canon = units[unit]
        reply = (LANGUAGES[lang].responses["timer"][0]
                 .replace("{n}", str(n)).replace("{unit}", unit))
        return ("timer", {"n": n, "unit": canon}, reply)

    def _intent_weather(self, low, lang, hit):
        return ("weather", {}, LANGUAGES[lang].responses["weather"][0])

    def _intent_greet(self, low, lang, hit):
        return ("greet", {}, LANGUAGES[lang].responses["greet"][0])

    def _intent_thanks(self, low, lang, hit):
        return ("thanks", {}, LANGUAGES[lang].responses["thanks"][0])

    def _intent_help(self, low, lang, hit):
        return ("help", {}, LANGUAGES[lang].responses["help"][0])

    def _intent_goodbye(self, low, lang, hit):
        return ("goodbye", {}, LANGUAGES[lang].responses["goodbye"][0])


# --------------------------------------------------------------------- #
def words_to_number(tokens: list[str]) -> int | None:
    """English spelled numbers: 'twelve' → 12, 'twenty three' → 23."""
    units = LANGUAGES["en"].units
    tens = LANGUAGES["en"].tens
    rev_u = {w: n for n, w in units.items()}
    rev_t = {w: n for n, w in tens.items()}
    value = None
    for t in tokens:
        if t.isdigit():
            value = (value or 0) + int(t) if value is None else value
            value = int(t)
        elif t in rev_t:
            value = (value or 0) + rev_t[t]
        elif t in rev_u:
            v = rev_u[t]
            if v < 10 and value is not None and value % 10 == 0 and value >= 20:
                value += v
            elif v >= 10:
                value = (value or 0) + v
            else:
                value = v
        elif value is not None:
            break
    return value


def words_to_number_local(tokens: list[str], lang: str) -> int | None:
    """Number for timer slots: English words in full, other languages use
    their units table (0-19) or digits."""
    if lang == "en":
        return words_to_number(tokens)
    units = LANGUAGES[lang].units
    rev = {w: n for n, w in units.items()}
    for t in reversed(tokens):
        if t.isdigit():
            return int(t)
        if t in rev:
            return rev[t]
    return None
