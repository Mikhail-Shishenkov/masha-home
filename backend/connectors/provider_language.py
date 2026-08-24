"""Small deterministic language boundary for explicit file-provider requests."""

from __future__ import annotations

import re
from dataclasses import dataclass


_SPACE = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s'-]+", re.UNICODE)
_GOOGLE = re.compile(r"\b(?:google\s*drive|гугл\s+диск\w*|google\s+диск\w*|drive|драйв\w*)\b", re.IGNORECASE)
_YANDEX = re.compile(r"\b(?:yandex\s*disk|яндекс\s+диск\w*|yandex\s+диск\w*)\b", re.IGNORECASE)
_COMMAND_WORDS = (
    "покажи", "найди", "поищи", "проверь", "посмотри", "открой", "прочитай",
    "последние", "недавние", "свежие", "файл", "файлы", "документ", "документы", "все",
)
_LEADING_COMMANDS = frozenset(("покажи", "найди", "поищи", "проверь", "посмотри", "открой", "прочитай"))
_LISTING_COMMANDS = frozenset(("покажи", "найди", "поищи", "проверь", "посмотри"))
_LISTING_MODIFIERS = frozenset(("последние", "недавние", "свежие", "все"))
_ADDRESS = frozenset(("маш", "маша", "машенька"))
_OBVIOUS_COMMAND_TYPOS = {"послледние": "последние", "файы": "файлы"}


@dataclass(frozen=True)
class ProviderLanguage:
    provider_id: str | None
    text: str


def normalize_explicit_provider(message: str) -> ProviderLanguage:
    """Normalize only an explicitly named provider; ambiguity fails closed."""
    text = _SPACE.sub(" ", _PUNCT.sub(" ", message.casefold().replace("ё", "е"))).strip()
    google = tuple(_GOOGLE.finditer(text))
    yandex = tuple(_YANDEX.finditer(text))
    if google and yandex:
        return ProviderLanguage(None, text)
    if google:
        start = min(match.start() for match in google)
        return ProviderLanguage("google_drive", _GOOGLE.sub("google_drive", _correct_command_prefix(text, start)))
    if yandex:
        start = min(match.start() for match in yandex)
        return ProviderLanguage("yandex_disk", _YANDEX.sub("yandex_disk", _correct_command_prefix(text, start)))
    return ProviderLanguage(None, text)


def normalize_command_prefix(message: str, *, token_limit: int = 3) -> str:
    """Correct a small leading command phrase, never a filename or query tail."""
    text = _SPACE.sub(" ", _PUNCT.sub(" ", message.casefold().replace("ё", "е"))).strip()
    words = text.split(" ")
    if not words:
        return text
    command_index = 1 if words[0] in _ADDRESS else 0
    if command_index >= min(token_limit, len(words)):
        return text
    command = _correct_word(words[command_index])
    if command not in _LEADING_COMMANDS:
        return text
    words[command_index] = command
    # A read command is followed by a user-owned filename.  For list/search
    # commands, only the compact "recent/all files" grammar may be corrected.
    if command not in _LISTING_COMMANDS:
        return " ".join(words)
    for index in range(command_index + 1, min(token_limit, len(words))):
        previous = words[index - 1]
        corrected = _correct_word(words[index])
        if index == command_index + 1 or previous in _LISTING_MODIFIERS:
            words[index] = corrected
    return " ".join(words)


def _correct_command_prefix(text: str, boundary: int) -> str:
    head, tail = text[:boundary], text[boundary:]
    separator = " " if head.endswith(" ") else ""
    return normalize_command_prefix(head, token_limit=len(head.split())) + separator + tail


def _correct_word(value: str) -> str:
    if value in _OBVIOUS_COMMAND_TYPOS:
        return _OBVIOUS_COMMAND_TYPOS[value]
    candidates = tuple(word for word in _COMMAND_WORDS if _edit_distance_at_most_one(value, word))
    return candidates[0] if len(candidates) == 1 else value


def _edit_distance_at_most_one(left: str, right: str) -> bool:
    if abs(len(left) - len(right)) > 1:
        return False
    if left == right:
        return True
    if len(left) == len(right):
        return sum(a != b for a, b in zip(left, right)) <= 1
    if len(left) > len(right):
        left, right = right, left
    index = offset = changes = 0
    while index < len(left) and offset < len(right):
        if left[index] == right[offset]:
            index += 1
            offset += 1
        else:
            changes += 1
            if changes > 1:
                return False
            if len(left) == len(right):
                index += 1
            offset += 1
    return changes + (len(right) - offset) <= 1
