"""Narrow deterministic Russian intents for explicit Google Drive reads."""

from __future__ import annotations

import re
from dataclasses import dataclass


_SPACE = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s'-]+", re.UNICODE)
_ORDINAL = {"первый": 1, "первую": 1, "первое": 1, "второй": 2, "вторую": 2, "второе": 2, "третий": 3, "третью": 3, "третье": 3}
_YANDEX_DISK = re.compile(r"\b(?:яндекс[\s-]*диск\w*|yandex[\s-]*disk)\b", re.IGNORECASE)


@dataclass(frozen=True)
class DriveIntent:
    kind: str
    query: str | None = None
    ordinal: int | None = None


def drive_intent(message: str) -> DriveIntent | None:
    normalized = _SPACE.sub(" ", _PUNCT.sub(" ", message.casefold().replace("ё", "е"))).strip()
    if not normalized:
        return None
    # A named provider is application-owned routing authority.  Drive must
    # never turn an explicitly Yandex-targeted request into a Drive call.
    if _YANDEX_DISK.search(normalized):
        return None
    ordinal = re.fullmatch(r"(?:маш(?:а|енька)?\s+)?(?:прочитай|изучи|открой)\s+(?:файл\s+|документ\s+)?(первый|первую|первое|второй|вторую|второе|третий|третью|третье)", normalized)
    if ordinal is not None:
        return DriveIntent("read_ordinal", ordinal=_ORDINAL[ordinal.group(1)])
    written = re.match(r"^(?:маш(?:а|енька)?\s+)?что\s+написано\s+в\s+(?:файл(?:е)?|документ(?:е)?)\s+(.+)$", normalized)
    if written is not None:
        query = _bounded_query(written.group(1))
        return DriveIntent("read_name", query=query) if query else DriveIntent("clarify")
    read = re.match(r"^(?:маш(?:а|енька)?\s+)?(?:прочитай|изучи|открой)\s+(.+)$", normalized)
    if read is not None:
        body = read.group(1).strip()
        if re.match(r"https?\b|s\d+\b|(?:первый|второй|третий)\s+источник\b", body):
            return None
        explicit = re.match(r"(?:в\s+(?:моем\s+)?(?:drive|драйве)\s+)?(?:файл(?:е)?|документ(?:е)?)\s+(.+)$", body)
        query = _bounded_query((explicit or read).group(1))
        if not query:
            return DriveIntent("clarify")
        return DriveIntent("read_name" if explicit is not None else "read_presented_name", query=query)
    listed = re.fullmatch(
        r"(?:маш(?:а|енька)?\s+)?(?:покажи|выведи|открой|дай\s+посмотреть)\s+(?:просто\s+)?(?:мои\s+)?(?:файл(?:ы)?|документ(?:ы)?)\s+(?:в|на)\s+(?:моем\s+)?(?:drive|драйве)",
        normalized,
    ) or re.fullmatch(r"(?:маш(?:а|енька)?\s+)?что\s+у\s+меня\s+есть\s+в\s+(?:моем\s+)?(?:drive|драйве)", normalized)
    if listed is not None:
        return DriveIntent("list")
    search = re.match(r"^(?:маш(?:а|енька)?\s+)?(?:найди|поищи|отыщи|посмотри|проверь|покажи|есть\s+у\s+меня)\s+(?:в\s+(?:моем\s+)?(?:drive|драйве)\s+)?(?:файл(?:ы)?|документ(?:ы)?)?\s*(.*)$", normalized)
    if search is not None:
        if not re.search(r"\b(?:drive|драйв\w*|файл\w*|документ\w*)\b", normalized):
            return None
        query = _bounded_query(search.group(1))
        if not query:
            return DriveIntent("clarify")
        return DriveIntent(
            "search_read" if re.search(r"\b(?:что\s+там|что\s+написано|скажи\s+что|расскажи\s+главное)\b", normalized) else "search",
            query=query,
        )
    return None


def _bounded_query(value: str) -> str | None:
    query = re.sub(r"^(?:про|о|по)\s+", "", value).strip(" -")
    query = re.sub(r"\s+(?:и\s+)?(?:скажи|расскажи|что)\s+.*$", "", query).strip()
    query = _SPACE.sub(" ", query)[:200]
    return query or None
