"""Bounded natural-language routing for existing local application capabilities.

The router never owns or mutates domain data.  It maps one current utterance to
one allow-listed intent; the existing MemoryIntentHandler remains the only
place that can create proposals or execute confirmed mutations.
"""

from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class CapabilityIntent(str, Enum):
    QUERY_MEMORY = "query_memory"
    FORGET_MEMORY = "forget_memory"
    QUERY_COMMITMENTS = "query_commitments"
    CREATE_COMMITMENT = "create_commitment"
    COMPLETE_COMMITMENT = "complete_commitment"
    QUERY_CONTINUITY = "query_continuity"
    OPEN_CONTINUITY = "open_continuity"
    RESOLVE_CONTINUITY = "resolve_continuity"


class ParsedCapabilityIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: CapabilityIntent
    confidence: float = Field(ge=0.0, le=1.0)
    entity: str | None = None
    temporal_scope: str | None = None
    source: str = "deterministic"


_POLITE_PREFIX = re.compile(r"^\s*(?:(?:маш(?:а|енька)?|маш)\s*[,!:-]?\s*)", re.IGNORECASE)
_SPACE = re.compile(r"\s+")
_PUNCTUATION = re.compile(r"[^\w\s«»'-]+", re.UNICODE)
_WORD_NUMBERS = {
    "одну": "1", "один": "1", "одно": "1",
    "две": "2", "два": "2",
    "три": "3", "четыре": "4", "пять": "5",
}
_SHARED_HISTORY_QUERY = re.compile(
    r"^(?:"
    r"что\s+(?:"
    r"есть\s+в\s+(?:нашей|общей)\s+истории|"
    r"у\s+нас(?:\s+есть)?\s+в\s+истории|"
    r"сохранено\s+в\s+нашей\s+истории"
    r")|"
    r"покажи\s+нашу\s+историю"
    r")$"
)
def normalize_utterance(value: str) -> str:
    text = _POLITE_PREFIX.sub("", value.casefold().replace("ё", "е"))
    text = _PUNCTUATION.sub(" ", text)
    words = [_WORD_NUMBERS.get(word, word) for word in text.split()]
    return _SPACE.sub(" ", " ".join(words)).strip()


def memory_query_entity(value: str) -> str | None:
    """Extract a supplied topic while keeping broad memory reads broad."""
    text = normalize_utterance(value)
    match = re.match(
        r"^(?:кстати\s+а\s+|а\s+)?что\s+ты\s+(?:обо\s+мне\s+)?"
        r"(?:помнишь|знаешь)\s+про\s+(?P<entity>.+)$",
        text,
    )
    if match:
        return match.group("entity").strip() or None
    return None


class NaturalLanguageCapabilityRouter:
    """Strict compatibility aliases; semantic meaning belongs to DialogueCore."""

    def route(
        self,
        message: str,
        *,
        explicit_only: bool = False,
    ) -> ParsedCapabilityIntent | None:
        text = normalize_utterance(message)
        if not text:
            return None
        deterministic = self._deterministic(text, explicit_only=explicit_only)
        if deterministic is not None:
            return deterministic
        return None

# Local semantic routing intentionally lives in semantic_resolver.py.
    @staticmethod
    def _deterministic(
        text: str,
        *,
        explicit_only: bool = False,
    ) -> ParsedCapabilityIntent | None:
        # Explicit shared-continuity language wins over task-like nouns.  It
        # still creates only a proposal in MemoryIntentHandler.
        resolve = re.match(
            r"^(?:"
            r"(?:закрой|закрыть|заверши|завершить|удали|удалить|убери|убрать)\s+"
            r"(?:открытую\s+)?(?:нить|тему)"
            r"(?:\s+(?:про|о))?\s*(?P<named>.+)?|"
            r"(?:эту\s+)?тему\s+можно\s+закрыть|"
            r"с\s+этой\s+темой\s+(?:закончили|закончено)"
            r")$",
            text,
        )
        if resolve:
            entity = (resolve.groupdict().get("named") or "").strip() or None
            return ParsedCapabilityIntent(
                intent=CapabilityIntent.RESOLVE_CONTINUITY,
                confidence=0.99,
                entity=entity,
            )

        thread = re.match(
            r"^(?:давай\s+)?(?:"
            r"(?:к|к этому)\s+(?P<return>.+?)\s+потом\s+вернемся|"
            r"не\s+потеряй(?:\s+эту|\s+этот)?(?:\s+(?:нить|тему|вопрос))?\s*(?P<lost>.*)|"
            r"(?:оставь|сохрани)\s+(?:эту\s+)?(?:нить|тему|вопрос)\s*(?P<keep>.*)|"
            r"вернемся\s+потом\s+к\s+(?P<later>.+)"
            r")$",
            text,
        )
        if thread:
            entity = next((value for value in thread.groupdict().values() if value), None)
            if entity in {None, "этому вопросу", "эту тему", "этому", "теме", "вопросу"}:
                entity = None
            return ParsedCapabilityIntent(intent=CapabilityIntent.OPEN_CONTINUITY, confidence=0.98, entity=entity)

        # Explicit writes win over broad read questions such as "что
        # сегодня...". They still produce proposals only.
        forget = re.match(
            r"^(?:забудь|не помни|убери из памяти)\s+(?:то\s+)?(?:что\s+)?(?P<body>.+)$",
            text,
        )
        if forget:
            return ParsedCapabilityIntent(
                intent=CapabilityIntent.FORGET_MEMORY,
                confidence=0.99,
                entity=forget.group("body"),
            )
        create = re.match(
            r"^(?:"
            r"(?:добавь|запиши|внеси)(?:\s+мне|\s+нам)?(?:\s+в)?(?:\s+наши)?\s+(?:дело|дела|задачу|обязательство)|"
            r"(?:дело|задачу|обязательство)\s+(?:добавь|запиши)|"
            r"(?:и\s+)?еще\s+(?:одна\s+)?(?:задача|дело|обязательство)|"
            r"надо\s+не\s+забыть|нужно\s+не\s+забыть|напомни(?:\s+мне)?"
            r")\s+(?P<body>.+)$",
            text,
        )
        if create:
            return ParsedCapabilityIntent(
                intent=CapabilityIntent.CREATE_COMMITMENT,
                confidence=0.98,
                entity=create.group("body"),
            )

        # Read routes.
        if _SHARED_HISTORY_QUERY.match(text):
            return ParsedCapabilityIntent(
                intent=CapabilityIntent.QUERY_CONTINUITY,
                confidence=0.99,
            )
        if re.match(
            r"^(?:к чему (?:мы )?(?:хотели )?вернут\w*|"
            r"что (?:у нас )?(?:остал\w*|продолжа\w*|не закончен\w*|не закрыт\w*).*(?:тем|нит)\w*|"
            r"какие (?:у нас )?(?:тем|нит)\w*.*(?:открыт|остал|продолжа)\w*)$",
            text,
        ):
            return ParsedCapabilityIntent(
                intent=CapabilityIntent.QUERY_CONTINUITY,
                confidence=0.97,
            )

        if re.match(
            r"^(?:"
            r"какие (?:у (?:меня|нас) )?(?:сейчас )?(?:дела|задачи|обязательства)|"
            r"что (?:у (?:меня|нас) )?(?:сейчас )?(?:по )?(?:делам|задачам|обязательствам)|"
            r"что (?:у (?:меня|нас) )?сегодня|"
            r"что (?:было )?запланировано(?: на сегодня)?|"
            r"покажи (?:мои |наши )?(?:дела|задачи|обязательства|планы)"
            r")$",
            text,
        ):
            scope = "today" if "сегодня" in text else None
            return ParsedCapabilityIntent(
                intent=CapabilityIntent.QUERY_COMMITMENTS,
                confidence=0.96,
                temporal_scope=scope,
            )

        if re.match(
            r"^(?:(?:кстати а |а )?что ты (?:обо мне )?"
            r"(?:помнишь|знаешь)(?: про .+)?|"
            r"покажи (?:мою )?память)$",
            text,
        ):
            return ParsedCapabilityIntent(
                intent=CapabilityIntent.QUERY_MEMORY,
                confidence=0.96,
                entity=memory_query_entity(text),
            )

        # In conversation-first mode implicit completion aliases do not own the turn.
        if explicit_only:
            return None

        # Writes: these only lead to proposals in MemoryIntentHandler.
        complete = re.match(r"^(?:с\s+)?(?P<body>.+?)\s+(?:закончили|закончил|готово|сделано)$", text)
        if complete:
            return ParsedCapabilityIntent(intent=CapabilityIntent.COMPLETE_COMMITMENT, confidence=0.91, entity=complete.group("body"))
        complete = re.match(r"^(?P<body>.+?)\s+(?:купил|купила|сделал|сделала|выполнил|выполнила|отправил|отправила)$", text)
        if complete:
            return ParsedCapabilityIntent(intent=CapabilityIntent.COMPLETE_COMMITMENT, confidence=0.91, entity=complete.group("body"))
        return None
