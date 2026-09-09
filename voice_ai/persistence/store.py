"""SQLite persistence: sessions, utterances, feedback, learned rules.

Thread-safe (dashboard reads from another thread), WAL journal for fast
commits. Learned rules survive restarts — the assistant keeps its memory.
"""
from __future__ import annotations

import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    created    REAL,
    last_seen  REAL,
    language   TEXT,
    turns      INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS utterances (
    id           TEXT PRIMARY KEY,
    session_id   TEXT,
    ts           REAL,
    lang         TEXT,
    audio_ms     REAL,
    hypothesis   TEXT,
    final        TEXT,
    intent       TEXT,
    reply        TEXT,
    wer          REAL,
    latency_ms   REAL,
    engine       TEXT,
    dialect      TEXT
);
CREATE TABLE IF NOT EXISTS feedback (
    utterance_id TEXT PRIMARY KEY,
    ts           REAL,
    corrected    TEXT
);
CREATE TABLE IF NOT EXISTS rules (
    kind     TEXT,
    lang     TEXT,
    lhs      TEXT,
    rhs      TEXT,
    score    REAL,
    conf     REAL,
    updated  REAL,
    PRIMARY KEY (kind, lang, lhs, rhs)
);
CREATE TABLE IF NOT EXISTS events (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    ts     REAL,
    level  TEXT,
    stage  TEXT,
    event  TEXT,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_utt_ts ON utterances (ts);
CREATE INDEX IF NOT EXISTS idx_utt_lang ON utterances (lang);
"""


class Store:
    def __init__(self, path: str = ":memory:"):
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _exec(self, sql: str, params: tuple = ()):
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    # ---------------------------------------------------------------- #
    # Sessions / utterances
    # ---------------------------------------------------------------- #
    def upsert_session(self, session_id: str, language: str, turns: int) -> None:
        now = time.time()
        self._exec(
            "INSERT INTO sessions (session_id, created, last_seen, language,"
            " turns) VALUES (?, ?, ?, ?, ?) ON CONFLICT(session_id) DO UPDATE"
            " SET last_seen=?, language=?, turns=?",
            (session_id, now, now, language, turns,
             now, language, turns))

    def insert_utterance(self, row: dict) -> None:
        self._exec(
            "INSERT OR REPLACE INTO utterances (id, session_id, ts, lang,"
            " audio_ms, hypothesis, final, intent, reply, wer, latency_ms,"
            " engine, dialect) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (row["id"], row.get("session_id"), row.get("ts", time.time()),
             row.get("lang"), row.get("audio_ms"), row.get("hypothesis"),
             row.get("final"), row.get("intent"), row.get("reply"),
             row.get("wer"), row.get("latency_ms"), row.get("engine"),
             row.get("dialect")))

    def get_utterance(self, utterance_id: str) -> dict | None:
        cur = self._exec("SELECT * FROM utterances WHERE id=?",
                         (utterance_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def recent_utterances(self, n: int = 12) -> list:
        cur = self._exec(
            "SELECT id, ts, lang, final, intent, latency_ms, wer, engine"
            " FROM utterances ORDER BY ts DESC LIMIT ?", (n,))
        return [dict(r) for r in cur.fetchall()]

    def accuracy_rows(self) -> list:
        """(ts, lang, wer) for utterances with a known reference."""
        cur = self._exec(
            "SELECT ts, lang, wer FROM utterances"
            " WHERE wer IS NOT NULL ORDER BY ts")
        return [(r["ts"], r["lang"], r["wer"]) for r in cur.fetchall()]

    def counts(self) -> dict:
        out = {}
        for table in ("sessions", "utterances", "feedback", "rules", "events"):
            cur = self._exec(f"SELECT COUNT(*) AS n FROM {table}")
            out[table] = cur.fetchone()["n"]
        return out

    # ---------------------------------------------------------------- #
    # Feedback + learned rules
    # ---------------------------------------------------------------- #
    def insert_feedback(self, utterance_id: str, corrected: str) -> None:
        self._exec("INSERT OR REPLACE INTO feedback VALUES (?, ?, ?)",
                   (utterance_id, time.time(), corrected))

    def feedback_seen(self, utterance_id: str) -> bool:
        cur = self._exec("SELECT 1 FROM feedback WHERE utterance_id=?",
                         (utterance_id,))
        return cur.fetchone() is not None

    def save_rules(self, kind: str, rows: list) -> None:
        """rows: (lang, lhs, rhs, score, conf)"""
        now = time.time()
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO rules (kind, lang, lhs, rhs, score,"
                " conf, updated) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(kind, lang, lhs, rhs, score, conf, now)
                 for lang, lhs, rhs, score, conf in rows])
            self._conn.commit()

    def load_rules(self, kind: str) -> list:
        cur = self._exec(
            "SELECT lang, lhs, rhs, score, conf FROM rules WHERE kind=?"
            " ORDER BY score DESC", (kind,))
        return [tuple(r) for r in cur.fetchall()]

    # ---------------------------------------------------------------- #
    def insert_event(self, level: str, stage: str, event: str,
                     detail: str = "") -> None:
        self._exec(
            "INSERT INTO events (ts, level, stage, event, detail)"
            " VALUES (?, ?, ?, ?, ?)",
            (time.time(), level, stage, event, detail))

    def recent_events(self, n: int = 25) -> list:
        cur = self._exec(
            "SELECT ts, level, stage, event, detail FROM events"
            " ORDER BY id DESC LIMIT ?", (n,))
        return [dict(r) for r in cur.fetchall()]
