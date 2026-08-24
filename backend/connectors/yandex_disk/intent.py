"""Narrow deterministic Russian intents for explicit Yandex Disk reads."""

from __future__ import annotations

import re
from dataclasses import dataclass


_ORD = {"первый": 1, "первую": 1, "первое": 1, "второй": 2, "вторую": 2, "второе": 2, "третий": 3, "третью": 3, "третье": 3}


@dataclass(frozen=True)
class DiskIntent:
    kind: str
    query: str | None = None
    ordinal: int | None = None


def _text(message: str) -> str:
    return " ".join(re.sub(r"[^\w\s'-]", " ", message.casefold().replace("ё", "е")).split())


def disk_intent(message: str) -> DiskIntent | None:
    text = _text(message)
    ordinal = re.fullmatch(r"(?:маш(?:а|енька)? )?(?:прочитай|изучи|открой) (?:файл |документ )?(первый|первую|первое|второй|вторую|второе|третий|третью|третье)", text)
    if ordinal:
        return DiskIntent("read_ordinal", ordinal=_ORD[ordinal.group(1)])
    if re.fullmatch(r"(?:маш(?:а|енька)? )?(?:покажи последние файлы на яндекс диске|что недавно загрузил на диск)", text):
        return DiskIntent("recent")
    search = re.match(r"^(?:маш(?:а|енька)? )?(?:найди|поищи|есть у меня) (?:на )?яндекс диске (?:файл|документ)? ?(?:про |о |по )?(.+)$", text)
    if search and search.group(1).strip():
        return DiskIntent("search", query=_query(search.group(1)))
    read = re.match(r"^(?:маш(?:а|енька)? )?(?:прочитай|изучи|открой) (?:(?:на яндекс диске )|(?:файл |документ ))(.+)$", text)
    if read:
        value = _query(read.group(1))
        return DiskIntent("read_name", query=value) if value else DiskIntent("clarify")
    return None


def _query(value: str) -> str | None:
    value = " ".join(value.strip(" -").split())[:200]
    return value or None
