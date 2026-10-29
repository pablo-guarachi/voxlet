"""Custom vocabulary: terms injected into Whisper's initial_prompt."""
from __future__ import annotations

import json
from pathlib import Path
from typing import List

import config

DATA_DIR = config.DATA_DIR
DATA_DIR.mkdir(parents=True, exist_ok=True)
VOCAB_PATH = DATA_DIR / "vocabulary.json"


def load() -> List[str]:
    if not VOCAB_PATH.exists():
        return []
    try:
        with open(VOCAB_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [str(x) for x in data]
    except Exception:
        pass
    return []


def save(items: List[str]):
    with open(VOCAB_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def add(term: str) -> List[str]:
    term = term.strip()
    if not term:
        return load()
    items = load()
    if term not in items:
        items.append(term)
        save(items)
    return items


def remove(term: str) -> List[str]:
    items = [t for t in load() if t != term]
    save(items)
    return items
