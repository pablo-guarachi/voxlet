"""Persistenza cronologia trascrizioni in SQLite."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import List, Tuple

import config

DATA_DIR = config.DATA_DIR
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "history.db"


def _connect():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS transcriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                text_raw TEXT NOT NULL,
                text_final TEXT NOT NULL,
                used_llm INTEGER NOT NULL,
                stt_seconds REAL NOT NULL,
                llm_seconds REAL NOT NULL
            )
            """
        )
        c.execute("CREATE INDEX IF NOT EXISTS idx_ts ON transcriptions(ts DESC)")


def insert(text_raw: str, text_final: str, used_llm: bool,
           stt_seconds: float, llm_seconds: float) -> int:
    with _connect() as c:
        cur = c.execute(
            "INSERT INTO transcriptions (ts, text_raw, text_final, used_llm, "
            "stt_seconds, llm_seconds) VALUES (?, ?, ?, ?, ?, ?)",
            (time.time(), text_raw, text_final, int(used_llm), stt_seconds, llm_seconds),
        )
        return cur.lastrowid


def list_recent(limit: int = 500, search: str = "") -> List[sqlite3.Row]:
    q = "SELECT * FROM transcriptions"
    args: tuple = ()
    if search:
        q += " WHERE text_final LIKE ? OR text_raw LIKE ?"
        args = (f"%{search}%", f"%{search}%")
    q += " ORDER BY ts DESC LIMIT ?"
    args = args + (limit,)
    with _connect() as c:
        return c.execute(q, args).fetchall()


def delete_all():
    with _connect() as c:
        c.execute("DELETE FROM transcriptions")
