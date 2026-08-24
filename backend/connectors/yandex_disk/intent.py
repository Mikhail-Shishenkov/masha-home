"""Narrow deterministic Russian intents for explicit Yandex Disk reads."""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.connectors.provider_language import normalize_explicit_provider


_ORD = {"первый": 1, "первую": 1, "первое": 1, "второй": 2, "вторую": 2, "второе": 2, "третий": 3, "третью": 3, "третье": 3}
_PROVIDER = r"yandex_disk"


@dataclass(frozen=True)
class DiskIntent:
    kind: str
    query: str | None = None
    ordinal: int | None = None


def _text(message: str) -> str:
    return " ".join(re.sub(r"[^\w\s'-]", " ", message.casefold().replace("ё", "е")).split())


def disk_intent(message: str) -> DiskIntent | None:
    language = normalize_explicit_provider(message)
    if language.provider_id == "google_drive":
        return None
    text = language.text
    ordinal = re.fullmatch(r"(?:маш(?:а|енька)? )?(?:прочитай|изучи|открой) (?:файл |документ )?(первый|первую|первое|второй|вторую|второе|третий|третью|третье)", text)
    if ordinal:
        return DiskIntent("read_ordinal", ordinal=_ORD[ordinal.group(1)])
    if re.fullmatch(rf"(?:маш(?:а|енька)? )?(?:(?:покажи|найди|выведи|открой) (?:последние|недавние|свежие) (?:файлы|документы) (?:на )?{_PROVIDER}|что (?:недавно|последним) (?:загрузил|добавил) (?:на )?(?:{_PROVIDER}|диск))", text):
        return DiskIntent("recent")
    listed = re.fullmatch(rf"(?:маш(?:а|енька)? )?(?:(?:покажи|выведи|открой|дай посмотреть) (?:просто )?(?:все )?(?:мои )?(?:файлы|документы) (?:на )?{_PROVIDER}|(?:что|какие файлы) у меня есть (?:на )?{_PROVIDER}|покажи содержимое (?:моего )?{_PROVIDER})", text)
    if listed:
        return DiskIntent("list")
    search = re.match(rf"^(?:маш(?:а|енька)? )?(?:найди|поищи|отыщи|посмотри|проверь|есть у меня) (?:на )?{_PROVIDER} (?:файл|документ)? ?(?:про |о |по )?(.+)$", text)
    if search and search.group(1).strip():
        return DiskIntent("search", query=_query(search.group(1)))
    read = re.match(rf"^(?:маш(?:а|енька)? )?(?:прочитай|изучи|открой) (?:(?:на {_PROVIDER} )|(?:файл |документ ))(.+)$", text)
    if read:
        value = _query(read.group(1))
        return DiskIntent("read_name", query=value) if value else DiskIntent("clarify")
    return None


def _query(value: str) -> str | None:
    value = " ".join(value.strip(" -").split())[:200]
    return value or None
