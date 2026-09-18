"""Language & dialect registry: vocabularies, normalization, numbers.

Ships with eight voice variants: English (en-US / en-GB / **en-IN**),
Spanish, French, German, **native Hindi (देवनागरी)** and **native Bengali
(বাংলা)**. Every language defines its intent keywords, response templates
and a phrase corpus that doubles as the demo/benchmark material; all
tokens across those tables form the engine vocabulary the codec encodes.

Normalization folds Latin diacritics (``météo`` → ``meteo``) but preserves
Indic matras and vowel signs — Devanagari/Bengali tokens stay intact, in
their native script, end to end (codec hashing is UTF-8, so scripts are
just tokens to the engine).
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field


def _fold(text: str) -> str:
    """Fold LATIN diacritics (``é`` → ``e``); leave Indic scripts untouched.

    NFD would decompose Indic two-part vowels (``ো`` → ``ে`` + ``া``),
    which would break keyword matching against precomposed registry
    strings — so only characters below U+0250 get the NFD treatment.
    """
    out = []
    for ch in text:
        if ord(ch) < 0x250:  # Latin-1 / Latin Extended-A
            d = unicodedata.normalize("NFD", ch)
            out.append("".join(c for c in d
                               if not 0x0300 <= ord(c) <= 0x036F))
        else:
            out.append(ch)
    return "".join(out)


def strip_accents(text: str) -> str:
    return _fold(text)


@dataclass
class Language:
    code: str
    name: str
    # dialect variant -> {spoken form -> canonical form}
    dialects: dict = field(default_factory=dict)
    # dialect variant -> extra demo phrases
    dialect_corpus: dict = field(default_factory=dict)
    # intent -> keywords that trigger it (single tokens)
    keywords: dict = field(default_factory=dict)
    # intent -> reply templates ({h} {m} {n} {unit} {text} placeholders)
    responses: dict = field(default_factory=dict)
    # demo/benchmark phrases
    corpus: list = field(default_factory=list)
    # spelled numbers 0-19 (math/time)
    units: dict = field(default_factory=dict)
    # spelled tens 20..90 (English math)
    tens: dict = field(default_factory=dict)

    def vocab(self) -> set:
        """Every speakable token — digits expand to their spelled forms
        (``"12"`` → ``{"twelve"}``), since audio speaks words, not digits."""
        words: set = set()
        for phrase in self.corpus:
            words.update(self._spoken(tokenize(phrase, self.code)))
        for dialect, phrases in self.dialect_corpus.items():
            for phrase in phrases:
                words.update(self._spoken(
                    tokenize(phrase, self.code, dialect)))
        for kws in self.keywords.values():
            words.update(kws)
        for tpl in self.responses.values():
            for r in tpl:
                words.update(self._spoken(tokenize(r, self.code)))
        words.update(self.units.values())
        words.update(self.tens.values())
        words.discard("")
        return words

    def _spoken(self, tokens: list) -> set:
        out = set()
        for t in tokens:
            if str(t).isdigit():
                out.update(spell_number(self.code, int(t)).split())
            else:
                out.add(t)
        return out


# --------------------------------------------------------------------- #
# Number spelling (units 0-19; tens for English math)
# --------------------------------------------------------------------- #
EN_UNITS = {i: w for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve "
    "thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split())}
EN_TENS = {t: w for t, w in zip(range(20, 100, 10),
                                "twenty thirty forty fifty sixty seventy "
                                "eighty ninety".split())}

_ES = "cero uno dos tres cuatro cinco seis siete ocho nueve diez once doce " \
      "trece catorce quince dieciseis diecisiete dieciocho diecinueve".split()
_FR = "zero un deux trois quatre cinq six sept huit neuf dix onze douze " \
      "treize quatorze quinze seize dixsept dixhuit dixneuf".split()
_DE = "null eins zwei drei vier funf sechs sieben acht neun zehn elf zwolf " \
      "dreizehn vierzehn funfzehn sechzehn siebzehn achtzehn neunzehn".split()
_HI = "शून्य एक दो तीन चार पाँच छह सात आठ नौ दस ग्यारह बारह तेरह चौदह " \
      "पंद्रह सोलह सत्रह अठारह उन्नीस".split()
_BN = "শূন্য এক দুই তিন চার পাঁচ ছয় সাত আট নয় দশ এগারো বারো তেরো চৌদ্দো " \
      "পনেরো ষোলো সতেরো আঠারো উনিশ".split()

DIGITS = {
    "en": EN_UNITS, "es": dict(enumerate(_ES)), "fr": dict(enumerate(_FR)),
    "de": dict(enumerate(_DE)), "hi": dict(enumerate(_HI)),
    "bn": dict(enumerate(_BN)),
}


def spell_number(lang: str, n: int) -> str:
    """Spell 0-99 in words (proper English tens; digit-wise elsewhere)."""
    n = max(0, min(99, int(n)))
    if lang == "en":
        if n < 20:
            return EN_UNITS[n]
        t, u = divmod(n, 10)
        return EN_TENS[t * 10] + (" " + EN_UNITS[u] if u else "")
    digits = DIGITS[lang]
    if n < 20:
        return digits[n]
    return " ".join(digits[int(d)] for d in str(n))


def spell_time(lang: str, h: int, m: int) -> str:
    """English spells the hour/minute words (midnight hour says "twelve");
    other languages return a digital "h:mm" — neural voices read it
    natively ("बारह बजकर चौवालीस") and the codec fallback spells digits."""
    if lang == "en":
        return (f"{spell_number('en', 12 if h == 0 else h)} "
                f"{spell_number('en', m)}")
    return f"{h}:{m:02d}"


# --------------------------------------------------------------------- #
# Tokenizer
# --------------------------------------------------------------------- #
def tokenize(text: str, lang: str = "en", dialect: str = "") -> list[str]:
    """Lowercase ASCII/Latin-folded tokens, applying the dialect's word map
    first. Indic scripts pass through in their native form — vowel signs
    (matras, category Mn/Mc) are token characters, never separators."""
    lang = lang if lang in LANGUAGES else "en"  # unknown ASR codes → en path
    if lang.startswith("en") and dialect:
        wordmap = LANGUAGES["en"].dialects.get(dialect, {})
        if wordmap:
            low = text.lower().split()
            low = [wordmap.get(t, t) for t in low]
            text = " ".join(low)
    text = _fold(str(text)).lower()
    out: list[str] = []
    tok = ""
    for ch in text:
        if ch.isalnum() or unicodedata.category(ch) in ("Mn", "Mc"):
            tok += ch
        elif tok:
            out.append(tok)
            tok = ""
    if tok:
        out.append(tok)
    units = LANGUAGES[lang].units
    if units:  # spelled-out numbers for the codec (units + English tens)
        rev = {w: n for n, w in units.items()}
        rev.update({w: n for n, w in LANGUAGES[lang].tens.items()})
        out = [str(rev[t]) if t in rev else t for t in out]
    return out


def join_tokens(tokens: list[str], lang: str = "en") -> str:
    """Human display form: numbers back to words, capitalized."""
    words = []
    for t in tokens:
        if t.lstrip("-").isdigit():
            words.append(spell_number(lang, int(t)))
        else:
            words.append(t)
    if not words:
        return ""
    text = " ".join(words)
    return text[0].upper() + text[1:] + ("." if not text.endswith((".", "!", "?")) else "")


# --------------------------------------------------------------------- #
# The registry
# --------------------------------------------------------------------- #
LANGUAGES: dict[str, Language] = {
    "en": Language(
        code="en", name="English",
        dialects={
            "en-GB": {"colour": "color", "flavour": "flavor",
                      "favourite": "favorite", "centre": "center",
                      "litre": "liter", "grey": "gray", "cheque": "check",
                      "programme": "program", "theatre": "theater",
                      "metre": "meter", "honour": "honor"},
            "en-IN": {"lakhs": "thousands", "crore": "million",
                      "prepone": "advance", "outofstation": "away",
                      "batchmates": "classmates"},
        },
        dialect_corpus={
            "en-IN": ["i will prepone the meeting",
                      "note pay the electricity bill",
                      "what is the weather in kolkata",
                      "thank you so much for the help"],
        },
        keywords={
            "greet": ["hello", "hi", "hey"],
            "time": ["time", "clock"],
            "math": ["plus", "minus", "times", "divided"],
            "note": ["note", "remember"],
            "timer": ["timer", "alarm"],
            "pc": ["open", "launch", "start"],
            "weather": ["weather", "rain"],
            "help": ["help", "commands"],
            "thanks": ["thanks", "thank"],
            "goodbye": ["bye", "goodbye"],
        },
        responses={
            "greet": ["Hello! How can I help you today?"],
            "time": ["It is {time}."],
            "math": ["{a} {op} {b} is {result}."],
            "note": ["Noted: {text}"],
            "timer": ["Timer set for {n} {unit}."],
            "pc": ["Opening {app} for you.",
                   "I couldn't find {app} on this PC."],
            "weather": ["No network here, but in the demo it is always sunny."],
            "help": ["You can ask for the time, weather, math, notes, a timer, "
                     "or tell me to open an app."],
            "thanks": ["You are very welcome!"],
            "goodbye": ["Goodbye! Happy to help anytime."],
            "fallback": ["I heard {text}. Try asking for help."],
        },
        corpus=[
            "hello there", "what time is it", "what is twelve plus thirty",
            "what is nine minus four", "set a timer for five minutes",
            "note buy coffee beans", "how is the weather",
            "remember to call the dentist", "thank you so much",
            "goodbye for now", "can you help me", "is it going to rain",
            "hey what is the time", "note send the invoice tomorrow",
            "set an alarm for thirty seconds",
        ],
        units=EN_UNITS, tens=EN_TENS,
    ),
    "es": Language(
        code="es", name="Español",
        keywords={
            "greet": ["hola", "buenas", "tardes"],
            "time": ["hora", "reloj"],
            "note": ["nota", "recuerda"],
            "timer": ["alarma", "temporizador"],
            "weather": ["clima", "lluvia"],
            "help": ["ayuda"],
            "thanks": ["gracias"],
            "goodbye": ["adios", "revoir"],
        },
        responses={
            "greet": ["Hola! Como puedo ayudarte hoy?"],
            "time": ["Son las {time}."],
            "note": ["Anotado: {text}"],
            "timer": ["Alarma configurada para {n} {unit}."],
            "weather": ["Sin red aqui, pero en la demo siempre hace sol."],
            "help": ["Puedes pedirme la hora, el clima, notas o una alarma."],
            "thanks": ["De nada!"],
            "goodbye": ["Adios! Hasta pronto."],
            "fallback": ["He escuchado: {text}. Pide ayuda si quieres."],
        },
        corpus=[
            "hola buenas tardes", "que hora es", "pon una alarma de cinco minutos",
            "nota comprar pan", "como esta el clima", "muchas gracias",
            "adios hasta manana", "necesito ayuda", "recuerda llamar a maria",
            "que hora es ahora", "nota enviar el informe", "hola que tal",
        ],
        units=dict(enumerate(_ES)),
    ),
    "fr": Language(
        code="fr", name="Français",
        keywords={
            "greet": ["bonjour", "salut"],
            "time": ["heure", "horloge"],
            "note": ["note", "retiens"],
            "timer": ["minuteur", "reveil"],
            "weather": ["meteo", "pluie"],
            "help": ["aide"],
            "thanks": ["merci"],
            "goodbye": ["revoir", "adieu"],
        },
        responses={
            "greet": ["Bonjour! Comment puis je aider?"],
            "time": ["Il est {time}."],
            "note": ["Note pris: {text}"],
            "timer": ["Minuteur regle pour {n} {unit}."],
            "weather": ["Pas de reseau ici, mais dans la demo il fait beau."],
            "help": ["Demandez moi l heure, la meteo, une note ou un minuteur."],
            "thanks": ["Avec plaisir!"],
            "goodbye": ["Au revoir! A bientot."],
            "fallback": ["J ai entendu: {text}. Demandez de l aide."],
        },
        corpus=[
            "bonjour comment allez vous", "quelle heure est il",
            "met un minuteur de dix minutes", "note acheter du pain",
            "quel temps fait il", "merci beaucoup", "au revoir a demain",
            "j ai besoin d aide", "retiens appeler pierre",
            "bonjour salut", "note envoyer le rapport", "quelle heure il est",
        ],
        units=dict(enumerate(_FR)),
    ),
    "de": Language(
        code="de", name="Deutsch",
        keywords={
            "greet": ["hallo", "guten"],
            "time": ["uhr", "zeit"],
            "note": ["notiz", "merke"],
            "timer": ["timer", "wecker"],
            "weather": ["wetter", "regen"],
            "help": ["hilfe"],
            "thanks": ["danke"],
            "goodbye": ["tschuss", "wiedersehen"],
        },
        responses={
            "greet": ["Hallo! Wie kann ich helfen?"],
            "time": ["Es ist {time} Uhr."],
            "note": ["Notiert: {text}"],
            "timer": ["Timer gestellt fuer {n} {unit}."],
            "weather": ["Kein Netz hier, aber in der Demo scheint die Sonne."],
            "help": ["Frag mich nach Uhrzeit, Wetter, Notizen oder Timer."],
            "thanks": ["Gern geschehen!"],
            "goodbye": ["Tschuss! Bis bald."],
            "fallback": ["Ich habe gehort: {text}. Frag nach Hilfe."],
        },
        corpus=[
            "hallo guten tag", "wie viel uhr ist es",
            "stell einen timer auf funf minuten",
            "notiz milch kaufen", "wie ist das wetter", "vielen dank",
            "tschuss bis morgen", "ich brauche hilfe", "merke ruf den arzt an",
            "hallo wie geht es dir", "notiz bericht senden", "wie spat ist es",
        ],
        units=dict(enumerate(_DE)),
    ),
    "hi": Language(
        code="hi", name="हिन्दी",
        keywords={
            "greet": ["नमस्ते", "नमस्कार"],
            "time": ["समय", "टाइम", "बजे"],
            "note": ["नोट", "याद"],
            "timer": ["टाइमर", "अलार्म"],
            "pc": ["खोलो", "खोल", "चालू"],
            "weather": ["मौसम", "बारिश"],
            "help": ["मदद"],
            "thanks": ["धन्यवाद", "शुक्रिया"],
            "goodbye": ["अलविदा", "फिर"],
        },
        responses={
            "greet": ["नमस्ते! मैं आपकी कैसे मदद करूँ?"],
            "time": ["अभी समय {time} हुआ।"],
            "note": ["नोट लिया: {text}"],
            "timer": ["टाइमर {n} {unit} के लिए सेट।"],
            "pc": ["{app} खोल रहा हूँ।", "मुझे {app} इस पीसी पर नहीं मिला।"],
            "weather": ["नेटवर्क नहीं है, पर डेमो में हमेशा धूप है।"],
            "help": ["आप समय, मौसम, नोट, टाइमर पूछ सकते हैं या कह सकते हैं "
                     "कि कोई ऐप खोलो।"],
            "thanks": ["कोई बात नहीं!"],
            "goodbye": ["अलविदा! फिर मिलेंगे।"],
            "fallback": ["मैंने सुना: {text}। मदद के लिए पूछिए।"],
        },
        corpus=[
            "नमस्ते आप कैसे हो", "अभी समय क्या हुआ",
            "पाँच मिनट का टाइमर लगाओ", "नोट दूध खरीदना है",
            "मौसम कैसा है", "बहुत धन्यवाद", "अलविदा फिर मिलेंगे",
            "मुझे मदद चाहिए", "याद रखना डॉक्टर को कॉल करना",
            "नमस्ते कैसे हो आप", "नोट कल रिपोर्ट भेजनी है", "समय बताओ",
        ],
        units=dict(enumerate(_HI)),
    ),
    "bn": Language(
        code="bn", name="বাংলা",
        keywords={
            "greet": ["নমস্কার", "হ্যালো"],
            "time": ["সময়", "বাজে"],
            "note": ["নোট", "মনে"],
            "timer": ["টাইমার", "অ্যালার্ম"],
            "pc": ["খোলো", "চালু"],
            "weather": ["আবহাওয়া", "বৃষ্টি"],
            "help": ["সাহায্য"],
            "thanks": ["ধন্যবাদ"],
            "goodbye": ["বিদায়", "আবার"],
        },
        responses={
            "greet": ["নমস্কার! আমি আপনাকে কীভাবে সাহায্য করব?"],
            "time": ["এখন সময় {time}।"],
            "note": ["নোট নেওয়া হলো: {text}"],
            "timer": ["টাইমার সেট {n} {unit} এর জন্য।"],
            "pc": ["{app} খুলছি।", "এই পিসিতে {app} খুঁজে পেলাম না।"],
            "weather": ["নেটওয়ার্ক নেই, কিন্তু ডেমোতে সবসময় রোদ থাকে।"],
            "help": ["আপনি সময়, আবহাওয়া, নোট, টাইমার জিজ্ঞাসা করতে পারেন।"],
            "thanks": ["স্বাগতম!"],
            "goodbye": ["বিদায়! আবার দেখা হবে।"],
            "fallback": ["আমি শুনেছি: {text}। সাহায্য চাইতে পারেন।"],
        },
        corpus=[
            "নমস্কার কেমন আছো", "এখন কয়টা বাজে",
            "পাঁচ মিনিটের টাইমার দাও", "নোট দুধ কিনতে হবে",
            "আবহাওয়া কেমন", "অনেক ধন্যবাদ", "বিদায় আবার দেখা হবে",
            "আমার সাহায্য দরকার", "মনে রেখো ডাক্তারকে ফোন করতে হবে",
            "নমস্কার ভালো আছো", "নোট কাল রিপোর্ট পাঠাতে হবে", "সময় বলো",
        ],
        units=dict(enumerate(_BN)),
    ),
}

DIALECTS = {"en": ["en-US", "en-GB", "en-IN"]}
