"""Bounded natural-language routing for existing local application capabilities.

The router never owns or mutates domain data.  It maps one current utterance to
one allow-listed intent; the existing MemoryIntentHandler remains the only
place that can create proposals or execute confirmed mutations.
"""

from __future__ import annotations

import json
import re
from enum import Enum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from backend.llm.model_models import (
    FinishReason,
    MessageRole,
    ModelCapabilities,
    ModelMessage,
    ModelRequest,
    PrivacyScope,
)
from backend.llm.model_provider import ModelProviderUnavailableError, ModelTimeoutError


class CapabilityIntent(str, Enum):
    QUERY_MEMORY = "query_memory"
    FORGET_MEMORY = "forget_memory"
    QUERY_COMMITMENTS = "query_commitments"
    CREATE_COMMITMENT = "create_commitment"
    COMPLETE_COMMITMENT = "complete_commitment"
    QUERY_CONTINUITY = "query_continuity"
    OPEN_CONTINUITY = "open_continuity"


class ParsedCapabilityIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: CapabilityIntent
    confidence: float = Field(ge=0.0, le=1.0)
    entity: str | None = None
    temporal_scope: str | None = None
    source: str = "deterministic"


class SemanticClassifier(Protocol):
    def classify(self, message: str) -> ParsedCapabilityIntent | None: ...


_POLITE_PREFIX = re.compile(r"^\s*(?:(?:маш(?:а|енька)?|маш)\s*[,!:-]?\s*)", re.IGNORECASE)
_SPACE = re.compile(r"\s+")
_PUNCTUATION = re.compile(r"[^\w\s«»'-]+", re.UNICODE)
_WORD_NUMBERS = {
    "одну": "1", "один": "1", "одно": "1",
    "две": "2", "два": "2",
    "три": "3", "четыре": "4", "пять": "5",
}


def normalize_utterance(value: str) -> str:
    text = _POLITE_PREFIX.sub("", value.casefold().replace("ё", "е"))
    text = _PUNCTUATION.sub(" ", text)
    words = [_WORD_NUMBERS.get(word, word) for word in text.split()]
    return _SPACE.sub(" ", " ".join(words)).strip()


class NaturalLanguageCapabilityRouter:
    """Deterministic aliases first, optional local semantic classification last."""

    CONFIDENCE_THRESHOLD = 0.78

    def __init__(self, classifier: SemanticClassifier | None = None):
        self.classifier = classifier

    def route(self, message: str) -> ParsedCapabilityIntent | None:
        text = normalize_utterance(message)
        if not text:
            return None
        deterministic = self._deterministic(text)
        if deterministic is not None:
            return deterministic
        if self.classifier is None or not self._has_capability_signal(text):
            return None
        try:
            classified = self.classifier.classify(message)
        except (ModelProviderUnavailableError, ModelTimeoutError):
            # Semantic routing is an optional local hint.  If its selected
            # model is unavailable, the utterance remains an ordinary turn.
            return None
        if classified is None or classified.confidence < self.CONFIDENCE_THRESHOLD:
            return None
        return classified

    @staticmethod
    def _deterministic(text: str) -> ParsedCapabilityIntent | None:
        # Explicit shared-continuity language wins over task-like nouns.  It
        # still creates only a proposal in MemoryIntentHandler.
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
        if re.search(r"\b(?:к чему|что|какие)\b.*\b(?:вернут|продолжа|не закончил|нить|тем|наш(?:а|ей) истор)\w*\b", text):
            return ParsedCapabilityIntent(intent=CapabilityIntent.QUERY_CONTINUITY, confidence=0.97)
        if re.search(r"\b(?:какие|что|покажи)\b.*\b(?:дел|задач|план|запланир|обязательств)\w*\b", text):
            scope = "today" if "сегодня" in text else None
            return ParsedCapabilityIntent(intent=CapabilityIntent.QUERY_COMMITMENTS, confidence=0.96, temporal_scope=scope)
        if re.search(r"\bчто\b.*\b(?:сегодня|запланир)\w*\b", text):
            return ParsedCapabilityIntent(intent=CapabilityIntent.QUERY_COMMITMENTS, confidence=0.91, temporal_scope="today" if "сегодня" in text else None)
        if re.search(r"\b(?:что|покажи)\b.*\b(?:помн|памят|зна)\w*\b", text):
            return ParsedCapabilityIntent(intent=CapabilityIntent.QUERY_MEMORY, confidence=0.96)

        # Writes: these only lead to proposals in MemoryIntentHandler.
        complete = re.match(r"^(?:с\s+)?(?P<body>.+?)\s+(?:закончили|закончил|готово|сделано)$", text)
        if complete:
            return ParsedCapabilityIntent(intent=CapabilityIntent.COMPLETE_COMMITMENT, confidence=0.91, entity=complete.group("body"))
        complete = re.match(r"^(?P<body>.+?)\s+(?:купил|купила|сделал|сделала|выполнил|выполнила|отправил|отправила)$", text)
        if complete:
            return ParsedCapabilityIntent(intent=CapabilityIntent.COMPLETE_COMMITMENT, confidence=0.91, entity=complete.group("body"))
        return None

    @staticmethod
    def _has_capability_signal(text: str) -> bool:
        return bool(re.search(
            r"\b(?:помн|забуд|дел|задач|план|напомн|закон|выполн|купил|сделал|нить|тем|вернут)\w*\b",
            text,
        ))


class LocalSemanticIntentClassifier:
    """Optional local-LLM classifier; it sees only the current utterance."""

    def __init__(self, *, router, identity_kernel, model_profiles):
        self.router = router
        self.identity_kernel = identity_kernel
        self.model_profiles = model_profiles

    def classify(self, message: str) -> ParsedCapabilityIntent | None:
        profile = self.model_profiles.get_active_profile()
        allowed = ", ".join(intent.value for intent in CapabilityIntent)
        request = ModelRequest(
            messages=(ModelMessage(
                role=MessageRole.SYSTEM,
                content=(
                    "Classify one Russian utterance into this fixed allowlist: " + allowed + ". "
                    "Definitions: create_commitment means create a new task, plan, obligation or reminder; "
                    "complete_commitment means mark an existing task done; query_commitments means ask about "
                    "existing tasks or plans; query_memory means ask for confirmed remembered facts; "
                    "forget_memory means remove a confirmed fact; open_continuity means explicitly preserve "
                    "a discussion topic for later; query_continuity means ask which preserved topics remain. "
                    "Return JSON only: {\"intent\": string, \"confidence\": 0..1, "
                    "\"entity\": string|null, \"temporal_scope\": string|null}. "
                    "For create/complete/forget/open intents, entity is the concise object or action "
                    "from the utterance with request words removed; it must be null only when the "
                    "utterance contains no resolvable object. Preserve dates and relative time in entity. "
                    "Do not answer the user and do not invent stored records."
                ),
            ), ModelMessage(role=MessageRole.USER, content=message)),
            identity_context=self.identity_kernel.build_context(),
            required_capabilities=ModelCapabilities(),
            privacy_scope=PrivacyScope.LOCAL_ONLY,
            preferred_provider_id=profile.provider_id,
            timeout_seconds=min(profile.timeout_seconds, 15.0),
            execution_model_id=profile.model_id,
            execution_think=False,
        )
        response = self.router.generate(request)
        if response.finish_reason not in {FinishReason.COMPLETED, FinishReason.LENGTH}:
            return None
        try:
            payload = json.loads(response.text.strip().removeprefix("```json").removesuffix("```").strip())
            payload["source"] = "local_semantic"
            return ParsedCapabilityIntent.model_validate(payload)
        except (ValueError, TypeError, KeyError):
            return None
