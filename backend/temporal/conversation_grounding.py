"""Small deterministic interpretation of temporal conversation signals."""

from __future__ import annotations

import re
from enum import Enum


class GreetingKind(str, Enum):
    NONE = "none"
    GENERAL = "general"
    MORNING = "morning"
    DAY = "day"
    EVENING = "evening"
    NIGHT = "night"


def greeting_kind(message: str) -> GreetingKind:
    normalized = " ".join(
        re.sub(r"[^\w\sё-]", " ", message.casefold(), flags=re.UNICODE).split()
    )
    if re.search(r"\b(?:доброе утро|утречка|утречко)\b", normalized):
        return GreetingKind.MORNING
    if re.search(r"\bдобрый день\b", normalized):
        return GreetingKind.DAY
    if re.search(r"\bдобрый вечер\b", normalized):
        return GreetingKind.EVENING
    if re.search(r"\b(?:доброй ночи|спокойной ночи)\b", normalized):
        return GreetingKind.NIGHT
    if re.search(r"\b(?:привет|здравствуй|здравствуйте)\b", normalized):
        return GreetingKind.GENERAL
    return GreetingKind.NONE


def greeting_matches_daypart(kind: GreetingKind, daypart: str) -> bool | None:
    if kind in {GreetingKind.NONE, GreetingKind.GENERAL}:
        return None
    matches = {
        GreetingKind.MORNING: {"morning"},
        GreetingKind.DAY: {"day"},
        GreetingKind.EVENING: {"evening", "late_evening"},
        GreetingKind.NIGHT: {"night", "late_evening"},
    }
    return daypart in matches[kind]
