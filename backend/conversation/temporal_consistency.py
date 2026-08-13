"""Narrow validation of model claims against application-owned temporal facts."""

from __future__ import annotations

import re

from backend.temporal.temporal_engine import Daypart, TemporalContext


_USER_SLEEP_EVIDENCE = re.compile(
    r"\b(?:я\s+)?(?:только\s+что\s+)?(?:проснул(?:ся|ась)|поспал(?:а)?|спал(?:а)?|"
    r"выспал(?:ся|ась)|лег(?:ла)?\s+спать|не\s+спал(?:а)?)\b",
    re.IGNORECASE,
)
_UNSUPPORTED_SLEEP_CLAIM = re.compile(
    r"\b(?:ты\s+(?:снова\s+)?(?:проснул(?:ся|ась)|выспал(?:ся|ась)|отдохнул(?:а)?|"
    r"поспал(?:а)?|спал(?:а)?(?:\s+всю\s+ночь)?)|после\s+сна|с\s+новыми\s+силами|"
    r"полон\s+сил|полна\s+сил)\b",
    re.IGNORECASE,
)
_INTERNAL_TEMPORAL_LEAK = re.compile(
    r"(?:\bпримечание\s*:|социальн(?:ый|ого)\s+сигнал|"
    r"приветстви[ея]\s+не\s+соответствует\s+текущему\s+времени|"
    r"temporal[_\s-]?context|temporal[_\s-]?contract)",
    re.IGNORECASE,
)
_RECENT_YESTERDAY_CLAIM = re.compile(
    r"\b(?:наш(?:ем)?\s+вчерашн(?:ий|ем|яя)\s+разговор(?:е)?|"
    r"видел[аи]?\s+тебя\s+вчера|мы\s+разговаривали\s+вчера)\b",
    re.IGNORECASE,
)
_CURRENT_MORNING_CLAIM = re.compile(
    r"\b(?:сейчас|теперь|уже)\s+(?:снова\s+)?утро\b|"
    r"\bсолнце\s+уже\s+встало\b|\bтолько\s+что\s+было\s+полночь\b",
    re.IGNORECASE,
)


def enforce_temporal_consistency(
    text: str,
    *,
    user_message: str,
    context: TemporalContext,
) -> str:
    """Replace only a proven contradiction; otherwise preserve model prose."""
    mismatch = context.greeting_matches_current_daypart is False
    if mismatch and (
        _INTERNAL_TEMPORAL_LEAK.search(text)
        or _current_daypart_contradiction(text, context)
    ):
        return _mismatched_greeting_response(context)
    if (
        context.same_local_date_as_last_interaction is True
        and context.absence_duration_seconds is not None
        and context.absence_duration_seconds <= 3_600
        and _RECENT_YESTERDAY_CLAIM.search(text)
    ):
        return _recent_interaction_response(context)
    if (
        not _USER_SLEEP_EVIDENCE.search(user_message)
        and _UNSUPPORTED_SLEEP_CLAIM.search(text)
    ):
        return _absence_only_response(context)
    return text


def _current_daypart_contradiction(text: str, context: TemporalContext) -> bool:
    return (
        context.daypart is not Daypart.MORNING
        and _CURRENT_MORNING_CLAIM.search(text) is not None
    )


def _mismatched_greeting_response(context: TemporalContext) -> str:
    local = context.current_local_time
    if context.greeting_kind.value == "morning":
        return f"Доброе утро в {local:%H:%M}? 😄 Решил начать завтра заранее?"
    return f"Неожиданное приветствие для {local:%H:%M} 😄 Но я здесь."


def _recent_interaction_response(context: TemporalContext) -> str:
    seconds = context.absence_duration_seconds or 0
    minutes = max(1, round(seconds / 60))
    return (
        f"Мы разговаривали совсем недавно — около {minutes} мин. назад. "
        f"Сейчас {context.current_local_time:%H:%M}."
    )


def _absence_only_response(context: TemporalContext) -> str:
    seconds = context.absence_duration_seconds
    if seconds is None:
        return "Я здесь. О сне или пробуждении могу судить только по твоим словам."
    minutes = max(1, round(seconds / 60))
    return (
        f"Мы не общались около {minutes} мин., но это ничего не говорит о сне или отдыхе."
    )
