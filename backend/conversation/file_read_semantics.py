"""Small Home-owned normalization for provider-neutral file read meaning."""

from __future__ import annotations

import re

from .capability_router import normalize_utterance


_MODE_STEMS = (
    ("read", ("прочит", "изуч", "откр")),
    ("recent", ("последн", "недавн", "свеж")),
    ("search", ("найд", "найт", "поищ", "поиск", "отыщ")),
    ("list", ("покаж", "вывед", "посмотр", "есть")),
)


def normalize_file_read_mode(evidence_text: str) -> str | None:
    """Canonicalize one grounded action fragment, never a filename/query."""

    # Keep grammatical request words such as ``есть``.  Search-oriented token
    # normalization intentionally removes them, but they carry list semantics
    # here ("что у меня есть на Диске?").
    tokens = tuple(re.findall(r"[a-zа-яё0-9]+", normalize_utterance(evidence_text)))
    for mode, stems in _MODE_STEMS:
        if any(token.startswith(stem) for token in tokens for stem in stems):
            return mode
    return None
