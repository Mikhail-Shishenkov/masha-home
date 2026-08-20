"""High-precision explicit Web intent gate; nouns alone never authorize traffic."""

from __future__ import annotations

import re
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from .models import FreshnessRequirement


class ExternalIntentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    explicit: bool
    query_hint: str | None = Field(default=None, max_length=300)
    freshness: FreshnessRequirement = FreshnessRequirement.TIMELESS
    reason: str = Field(min_length=1, max_length=100)


class FetchIntentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    explicit: bool
    direct_url: str | None = Field(default=None, max_length=2_000)
    source_id: str | None = Field(default=None, pattern=r"^S[1-9][0-9]*$")
    source_position: int | None = Field(default=None, ge=1, le=5)
    search_then_fetch: bool = False
    query_hint: str | None = Field(default=None, max_length=300)
    freshness: FreshnessRequirement = FreshnessRequirement.TIMELESS
    reason: str = Field(min_length=1, max_length=100)


class ExternalIntentClassifier(Protocol):
    def classify(self, message: str, recent_messages: tuple[str, ...]) -> ExternalIntentDecision | None: ...


_PREFIX = re.compile(r"^\s*(?:маш(?:а|енька)?\s*[,!:-]?\s*)?", re.IGNORECASE)
_SPACE = re.compile(r"\s+")
_PUNCTUATION = re.compile(r"[^\w\s«»'./+:#-]+", re.UNICODE)
_EXPLICIT = (
    re.compile(
        r"^(?:поищи|найди|проверь|посмотри)\s+"
        r"(?:пожалуйста\s+)?(?:в\s+(?:интернете|сети|вебе)|онлайн)\s*(?P<query>.*)$"
    ),
    re.compile(
        r"^(?:поищи|найди)\s+(?:самую\s+)?(?:свежую|актуальную|последнюю|текущую)\s+"
        r"(?:информацию|версию|новость|новости|данные)\s+(?:о|об|про)?\s*(?P<query>.*)$"
    ),
    re.compile(
        r"^(?:посмотри|проверь)\s*,?\s*(?:что|чего)\s+(?:сейчас\s+)?"
        r"(?:пишут|говорят|известно)\s+(?:о|об|про)?\s*(?P<query>.*)$"
    ),
    re.compile(
        r"^(?:проверь|узнай)\s*,?\s*(?:исправили|вышла|вышел|обновили|изменилось|"
        r"доступно|появилось)\s*(?P<query>.*)$"
    ),
)
_REFERENCE_ONLY = re.compile(
    r"^(?:(?:исправили|решили|обновили|изменилось|вышло)\s+(?:ли\s+)?(?:уже\s+)?)?"
    r"(?:это|эту\s+проблему|этот\s+баг|тот\s+баг|ту\s+ошибку|там|сейчас)$"
)
_CONTEXTUAL_FOLLOW_UP = re.compile(
    r"^(?:а\s+)?(?:сейчас|теперь)|"
    r"^(?:исправили|решили|обновили|изменилось|вышло)\s+ли\s+(?:уже\s+)?(?:это|там)$"
)
_HTTPS_URL = re.compile(r"https://[^\s<>\"']+", re.IGNORECASE)
_FETCH_VERB = re.compile(r"\b(?:прочитай|посмотри|глянь|изучи|расскажи)\b", re.IGNORECASE)
_SOURCE_REFERENCE = re.compile(
    r"^(?:прочитай|посмотри|изучи)\s+(?:(?:источник\s+)?s(?P<id>[1-9][0-9]*)|"
    r"(?P<ordinal>первый|второй|третий|четвертый|пятый)\s+источник)"
    r"(?:\s+(?:и|а)\s+.+)?$"
)
_SEARCH_THEN_FETCH = re.compile(
    r"^(?:найди|поищи)\s+(?P<query>.+?)\s*(?:и\s+|,\s*)"
    r"(?:прочитай|посмотри|изучи|расскажи)\b",
    re.IGNORECASE,
)
_ORDINAL = {"первый": 1, "второй": 2, "третий": 3, "четвертый": 4, "пятый": 5}


def normalize_external_utterance(value: str) -> str:
    text = _PREFIX.sub("", value.casefold().replace("ё", "е"))
    return _SPACE.sub(" ", _PUNCTUATION.sub(" ", text)).strip()


def infer_freshness(value: str) -> FreshnessRequirement:
    if re.search(r"\b(?:срочно|прямо\s+сейчас|breaking|свежие\s+новости|последние\s+новости)\b", value):
        return FreshnessRequirement.BREAKING
    if re.search(r"\b(?:сейчас|актуальн|текущ|последн\w*\s+верси|уже|исправили|вышл\w*)\b", value):
        return FreshnessRequirement.CURRENT
    if re.search(r"\b(?:недавн|за\s+(?:неделю|месяц)|свеж\w*)\b", value):
        return FreshnessRequirement.RECENT
    return FreshnessRequirement.TIMELESS


class ExplicitExternalIntentGate:
    """Deterministic requests first; optional local classifier only for ambiguity."""

    def __init__(self, classifier: ExternalIntentClassifier | None = None):
        self.classifier = classifier

    def detect(
        self,
        message: str,
        *,
        recent_messages: tuple[str, ...] = (),
    ) -> ExternalIntentDecision:
        normalized = normalize_external_utterance(message)
        deterministic = self._deterministic(normalized)
        if deterministic is not None:
            return deterministic
        if _CONTEXTUAL_FOLLOW_UP.fullmatch(normalized) and any(
            self._deterministic(normalize_external_utterance(previous)) is not None
            for previous in recent_messages[-4:]
        ):
            return ExternalIntentDecision(
                explicit=True,
                query_hint=None,
                freshness=FreshnessRequirement.CURRENT,
                reason="explicit_web_follow_up",
            )
        if self.classifier is not None:
            try:
                classified = self.classifier.classify(message, recent_messages[-6:])
            except Exception:
                classified = None
            if classified is not None and classified.explicit:
                return classified
        return ExternalIntentDecision(explicit=False, reason="no_explicit_external_request")

    @staticmethod
    def _deterministic(normalized: str) -> ExternalIntentDecision | None:
        for pattern in _EXPLICIT:
            match = pattern.match(normalized)
            if match is None:
                continue
            query = (match.groupdict().get("query") or "").strip(" -—,:;.")
            if _REFERENCE_ONLY.fullmatch(query):
                query = ""
            return ExternalIntentDecision(
                explicit=True,
                query_hint=query or None,
                freshness=infer_freshness(normalized),
                reason="deterministic_explicit_request",
            )
        return None


class ExplicitWebFetchIntentGate:
    """High-precision fetch routing; opening a source is deliberately excluded."""

    def detect(self, message: str) -> FetchIntentDecision:
        raw_urls = tuple(_HTTPS_URL.findall(message))
        normalized = normalize_external_utterance(message)
        search_fetch = _SEARCH_THEN_FETCH.match(normalized)
        if search_fetch is not None:
            query = search_fetch.group("query").strip(" -—,:;.")
            return FetchIntentDecision(
                explicit=True,
                search_then_fetch=True,
                query_hint=query or None,
                freshness=infer_freshness(normalized),
                reason="explicit_search_then_fetch",
            )
        source_reference = _SOURCE_REFERENCE.fullmatch(normalized)
        if source_reference is not None:
            source_id = source_reference.group("id")
            return FetchIntentDecision(
                explicit=True,
                source_id=None if source_id is None else f"S{source_id}",
                source_position=(
                    None if source_id is not None else _ORDINAL[source_reference.group("ordinal")]
                ),
                reason="explicit_source_fetch",
            )
        if raw_urls and (_FETCH_VERB.search(message) or len(message.strip()) == len(raw_urls[0])):
            return FetchIntentDecision(
                explicit=True,
                direct_url=raw_urls[0].rstrip(".,;:!?)]}"),
                freshness=infer_freshness(normalized),
                reason="explicit_direct_fetch",
            )
        return FetchIntentDecision(explicit=False, reason="no_explicit_fetch_request")
