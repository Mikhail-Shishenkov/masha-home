"""Bounded, conservative passive-memory candidate interpretation.

The detector consumes stored USER evidence only.  It deliberately implements
the v0.3 deterministic fast path: ambiguous language fails closed instead of
adding a second model call to every ordinary conversation turn.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from enum import Enum
from time import perf_counter
from typing import Literal
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue

from backend.conversation.conversation_models import (
    ConversationMessage,
    ConversationMessageOrigin,
    ConversationRole,
)
from backend.temporal.temporal_engine import TemporalContext, TemporalEngine

from .memory_models import (
    CandidateType,
    Commitment,
    CommitmentStatus,
    Decision,
    DecisionStatus,
    Fact,
    FactStatus,
    IdentityCode,
    RelationshipKind,
    RelationshipMemory,
    RelationshipStatus,
    SourceType,
    Visibility,
)
from .memory_retriever import MemoryRetriever
from .text_normalization import meaningful_tokens, normalize_search_text


DETECTOR_VERSION = "passive-memory-v0.3.0"
FACT_THRESHOLD = 0.82
DECISION_THRESHOLD = 0.82
COMMITMENT_THRESHOLD = 0.90
RELATIONSHIP_THRESHOLD = 0.90
CANDIDATE_EXPIRY_DAYS = 7


class ExistingMemoryRelation(str, Enum):
    NEW = "new"
    DUPLICATE = "duplicate"
    POSSIBLE_UPDATE = "possible_update"


class PassiveCandidatePayload(BaseModel):
    """Backward-compatible typed envelope stored in proposed_payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal["passive_candidate_v1"] = "passive_candidate_v1"
    record_type: Literal["fact", "decision", "commitment", "relationship_memory"]
    record: dict[str, JsonValue]
    conversation_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    evidence_message_ids: tuple[str, ...] = Field(min_length=1, max_length=4)
    detector_version: str = Field(min_length=1)
    reason: str = Field(min_length=3, max_length=240)
    detected_at: AwareDatetime
    expires_at: AwareDatetime
    normalized_signature: str = Field(min_length=1)
    relation: ExistingMemoryRelation = ExistingMemoryRelation.NEW
    related_memory_id: str | None = None


class ProposedPassiveCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_type: CandidateType
    record: dict[str, JsonValue]
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=3, max_length=240)
    normalized_signature: str = Field(min_length=1)


class MemoryCandidateDetectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    conversation_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    current_user_message: ConversationMessage
    recent_messages: tuple[ConversationMessage, ...] = Field(max_length=8)
    temporal_context: TemporalContext


class MemoryCandidateDetectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    proposals: tuple[ProposedPassiveCandidate, ...]
    skip_reason: str | None = None
    gate_latency_ms: float = Field(ge=0.0)
    extraction_latency_ms: float = Field(ge=0.0)
    semantic_extractor_invoked: bool = False


_SPACE = re.compile(r"\s+")
_EXPLICIT_CAPABILITY = re.compile(
    r"^\s*(?:маша[,.!]?\s*)?(?:запомни|забудь|удали|добавь|создай|напомни|"
    r"подтверждаю|подтверди|закрой\s+(?:нить|дело))",
    re.IGNORECASE,
)
_BARE_CONFIRMATION = re.compile(
    r"^\s*(?:да|нет|подтверждаю|не\s+сейчас)[)!.,\s]*$",
    re.IGNORECASE,
)
_GREETING_OR_ACK = re.compile(
    r"^\s*(?:доброе\s+утро|добрый\s+(?:день|вечер)|доброй\s+ночи|утречк[ао]?|"
    r"привет|здравствуй(?:те)?|понятно|ясно|ага|угу|ок(?:ей)?|спасибо)[)!.,\s]*$",
    re.IGNORECASE,
)
_QUESTION = re.compile(
    r"\?|^\s*(?:кто|что|где|когда|как|какой|какая|какие|почему|зачем|сколько|"
    r"можно\s+ли|стоит\s+ли)\b",
    re.IGNORECASE,
)
_UNCERTAIN = re.compile(
    r"\b(?:может(?:\s+быть)?|наверное|возможно|подумаем|рассматриваю|кажется|"
    r"когда-нибудь|надо\s+бы|хотел(?:ось)?\s+бы)\b",
    re.IGNORECASE,
)
_SECRET = re.compile(
    r"\b(?:парол[ья]|password|api[ _-]?key|токен|token|секретн(?:ый|ая)\s+ключ|"
    r"пин[ -]?код|cvv|cvc|номер\s+(?:мо(?:ей|его)\s+)?(?:карты|сч[её]та)|seed\s+phrase)\b",
    re.IGNORECASE,
)
_SENSITIVE = re.compile(
    r"\b(?:диагноз|вич|спид|онколог|психиатр|сексуальн|интимн|политическ(?:ие|ая)\s+взгляд|"
    r"религиозн(?:ые|ая)\s+убежден|голосую|коммунист|либерал|консерватор|"
    r"православн\w*|мусульман\w*|атеист\w*|католик\w*|иудей\w*|буддист\w*|паспорт|снилс|инн|"
    r"кредит\w*|зарплат\w*|доход\w*|инсулин)\b",
    re.IGNORECASE,
)
_TRANSIENT = re.compile(
    r"^\s*(?:я\s+)?(?:сейчас|сегодня)\s+(?:я\s+)?(?:устал(?:а)?|хочу|голоден|"
    r"мне\s+холодно|мне\s+жарко|мне\s+грустно|мне\s+весело|болит)\b|"
    r"^\s*мне\s+надо\s+в\s+туалет\b",
    re.IGNORECASE,
)
_QUOTED = re.compile(r"^\s*(?:он|она|они|друг|коллега|мама|папа)\s+(?:сказал|сказала|говорит)\b", re.IGNORECASE)
_GENERAL_KNOWLEDGE = re.compile(
    r"\b(?:находится|является|представляет\s+собой)\b|\s+[—-]\s+(?:красный|это)\b",
    re.IGNORECASE,
)

_GENDER = re.compile(r"\bя\s+(?P<value>мужчина|женщина)\b", re.IGNORECASE)
_NAME = re.compile(r"\bзовут\s+меня\s+(?P<value>[А-ЯЁA-Z][а-яёa-z-]{1,40})\b")
_RESIDENCE = re.compile(r"\bя\s+живу\s+в\s+(?P<value>[А-ЯЁA-Z][А-ЯЁа-яёA-Za-z -]{1,80})", re.IGNORECASE)
_PREFER = re.compile(r"\bя\s+предпочитаю\s+(?P<value>[^.!?]{3,160})", re.IGNORECASE)
_CONVENIENT = re.compile(r"\bмне\s+удобнее\s+(?P<value>[^.!?]{3,160})", re.IGNORECASE)
_TEA = re.compile(
    r"\bчай\s+(?:я\s+)?(?:обычно|всегда|по-прежнему)\s+пью\s+"
    r"(?P<value>без\s+сахара)\b",
    re.IGNORECASE,
)
_ROUTINE = re.compile(r"\bя\s+обычно\s+(?P<value>[^.!?]{4,160})", re.IGNORECASE)
_ALWAYS = re.compile(r"\bя\s+всегда\s+(?P<value>[^.!?]{4,160})", re.IGNORECASE)

_DECISION = re.compile(
    r"(?:^|\b)(?:вс[её][,!:]?\s*)?(?P<value>(?:оставляем|решили(?:\s*:)?|"
    r"будем\s+использовать|теперь\s+основн\w*\s+будет)\s+[^.!?]{3,220})",
    re.IGNORECASE,
)
_COMMITMENT = re.compile(
    r"^\s*(?P<value>(?:завтра|послезавтра|сегодня)\s+(?:я\s+)?обязательно\s+[^.!?]{3,220})",
    re.IGNORECASE,
)
_RELATIONSHIP = re.compile(
    r"(?:мне\s+очень\s+нравится[^.!?]*(?:мы\s+вместе|как\s+мы)|"
    r"для\s+меня[^.!?]*(?:важн\w*\s+наш|наш\s+важн\w*)[^.!?]*)",
    re.IGNORECASE,
)


class PassiveMemoryCandidateDetector:
    """Deterministic Stage A + strict extraction for clear v0.3 evidence."""

    def __init__(self, temporal_engine: TemporalEngine):
        self.temporal_engine = temporal_engine

    def detect(
        self,
        request: MemoryCandidateDetectionRequest,
    ) -> MemoryCandidateDetectionResult:
        gate_started = perf_counter()
        message = request.current_user_message
        self._validate_evidence(request)
        text = _SPACE.sub(" ", message.content.strip())
        skip = self._ineligible_reason(text)
        gate_ms = (perf_counter() - gate_started) * 1_000
        if skip is not None:
            return MemoryCandidateDetectionResult(
                proposals=(),
                skip_reason=skip,
                gate_latency_ms=gate_ms,
                extraction_latency_ms=0.0,
            )

        extraction_started = perf_counter()
        proposals = self._extract(text, request)
        extraction_ms = (perf_counter() - extraction_started) * 1_000
        return MemoryCandidateDetectionResult(
            proposals=tuple(proposals),
            skip_reason=None if proposals else "no_supported_durable_claim",
            gate_latency_ms=gate_ms,
            extraction_latency_ms=extraction_ms,
        )

    @staticmethod
    def _validate_evidence(request: MemoryCandidateDetectionRequest) -> None:
        message = request.current_user_message
        if message.role is not ConversationRole.USER:
            raise ValueError("passive evidence must be a USER message")
        if message.origin is not ConversationMessageOrigin.USER:
            raise ValueError("passive evidence must be user-authored")
        if message.conversation_id != request.conversation_id:
            raise ValueError("evidence conversation mismatch")
        if not any(item.id == message.id for item in request.recent_messages):
            raise ValueError("current evidence message is not stored in the bounded window")

    @staticmethod
    def _ineligible_reason(text: str) -> str | None:
        if _SECRET.search(text):
            return "secret_rejected"
        if _SENSITIVE.search(text):
            return "sensitive_personal_data_rejected"
        if _EXPLICIT_CAPABILITY.search(text) or _BARE_CONFIRMATION.match(text):
            return "explicit_capability_turn"
        if _GREETING_OR_ACK.match(text):
            return "greeting_or_acknowledgement"
        if _QUESTION.search(text):
            return "question"
        if _QUOTED.search(text) or PassiveMemoryCandidateDetector._looks_quoted(text):
            return "quoted_or_other_person_claim"
        if _UNCERTAIN.search(text):
            return "uncertain_or_hypothetical"
        if _TRANSIENT.search(text):
            return "transient_state"
        if _GENERAL_KNOWLEDGE.search(text) and not re.search(
            r"\b(?:я|мне|мы|решили|оставляем|будем)\b", text, re.IGNORECASE
        ):
            return "general_knowledge"
        if len(meaningful_tokens(text)) < 2:
            return "too_little_user_evidence"
        return None

    @staticmethod
    def _looks_quoted(text: str) -> bool:
        stripped = text.strip()
        return (
            ("«" in stripped and "»" in stripped)
            or stripped.count('"') >= 2
        )

    def _extract(
        self,
        text: str,
        request: MemoryCandidateDetectionRequest,
    ) -> list[ProposedPassiveCandidate]:
        now = request.current_user_message.created_at.astimezone(timezone.utc)
        project_id = request.project_id
        proposals: list[ProposedPassiveCandidate] = []

        relationship = _RELATIONSHIP.search(text)
        if relationship:
            record = RelationshipMemory(
                id=f"relationship_{uuid4()}",
                kind=RelationshipKind.SHARED_MILESTONE,
                title="Значимый общий проект",
                content={"text": relationship.group(0).strip(" ;,")},
                status=RelationshipStatus.CURRENT,
                visibility=Visibility.VISIBLE,
                importance=0.8,
                confidence=0.94,
                source=SourceType.CONVERSATION,
                project_ids=[project_id],
                source_episode_ids=[],
                revises_id=None,
                created_at=now,
            )
            proposals.append(self._proposal(record, CandidateType.RELATIONSHIP_MEMORY, 0.94, "пользователь явно назвал общий опыт значимым"))
            return proposals

        commitment = _COMMITMENT.search(text)
        if commitment:
            statement = commitment.group("value").strip()
            body, due = self.temporal_engine.extract_due(statement)
            if due is not None and due.resolved_utc is not None:
                body = re.sub(r"^обязательно\s+", "", body, flags=re.IGNORECASE)
                record = Commitment(
                    id=f"commitment_{uuid4()}",
                    text=body.strip(),
                    owner=IdentityCode.MISHA,
                    status=CommitmentStatus.OPEN,
                    visibility=Visibility.VISIBLE,
                    project_ids=[project_id],
                    due_at=due.resolved_utc,
                    completed_at=None,
                    importance=0.75,
                    source=SourceType.CONVERSATION,
                    source_episode_ids=[],
                    replaces_id=None,
                    created_at=now,
                    updated_at=now,
                )
                proposals.append(self._proposal(record, CandidateType.COMMITMENT, 0.94, "явное обязательство Миши с определимым сроком"))
            return proposals

        decision = _DECISION.search(text)
        if decision:
            statement = re.split(r",\s*а\s+[^,]*(?:потом|позже)\b", decision.group("value"), maxsplit=1, flags=re.IGNORECASE)[0].strip(" ,:;")
            record = Decision(
                id=f"decision_{uuid4()}",
                title="Решение из разговора",
                decision=statement,
                reason="Миша сформулировал выбор как принятое решение.",
                status=DecisionStatus.ACTIVE,
                visibility=Visibility.VISIBLE,
                project_ids=[project_id],
                source=SourceType.CONVERSATION,
                source_episode_ids=[],
                supersedes_id=None,
                superseded_by=None,
                created_at=now,
                updated_at=now,
            )
            proposals.append(self._proposal(record, CandidateType.DECISION, 0.89, "явно сформулированное принятое решение"))
            return proposals

        facts: list[tuple[str, str, str, float]] = []
        if match := _GENDER.search(text):
            facts.append(("gender", match.group("value").casefold(), "явное устойчивое профильное утверждение", 0.97))
        if match := _NAME.search(text):
            facts.append(("name", match.group("value"), "пользователь явно назвал своё имя", 0.97))
        if match := _RESIDENCE.search(text):
            facts.append(("residence", match.group("value").strip(" ,;"), "пользователь явно назвал место проживания", 0.93))
        if match := _TEA.search(text):
            facts.append(("tea_preference", f"чай {match.group('value').casefold()}", "явная стабильная привычка", 0.94))
        elif match := _PREFER.search(text):
            value = match.group("value").strip(" ,;")
            key = "transmission_preference" if "автомат" in value.casefold() else "preference"
            facts.append((key, value, "явно выраженное устойчивое предпочтение", 0.92))
        elif match := _CONVENIENT.search(text):
            facts.append(("work_preference", match.group("value").strip(" ,;"), "явно выраженный устойчивый рабочий паттерн", 0.88))
        elif match := _ROUTINE.search(text):
            value = match.group("value").strip(" ,;")
            key = "sleep_schedule" if re.search(r"ложусь|спать|полуночи", value, re.IGNORECASE) else "routine"
            facts.append((key, value, "явно обозначенная повторяющаяся привычка", 0.88))
        elif match := _ALWAYS.search(text):
            facts.append(("routine", match.group("value").strip(" ,;"), "явно обозначенная устойчивая привычка", 0.9))

        for key, value, reason, confidence in facts:
            record = Fact(
                id=f"fact_{uuid4()}",
                subject="misha",
                key=key,
                value=value,
                status=FactStatus.ACTIVE,
                visibility=Visibility.VISIBLE,
                importance=0.7,
                confidence=confidence,
                source=SourceType.CONVERSATION,
                owner=IdentityCode.MISHA,
                known_by=[IdentityCode.MISHA, IdentityCode.MASHA],
                project_ids=[project_id],
                source_episode_ids=[],
                supersedes_id=None,
                superseded_by=None,
                created_at=now,
                updated_at=now,
            )
            proposals.append(self._proposal(record, CandidateType.FACT, confidence, reason))
        return proposals

    @staticmethod
    def _proposal(record, candidate_type: CandidateType, confidence: float, reason: str) -> ProposedPassiveCandidate:
        record_type = {
            CandidateType.FACT: "fact",
            CandidateType.DECISION: "decision",
            CandidateType.COMMITMENT: "commitment",
            CandidateType.RELATIONSHIP_MEMORY: "relationship_memory",
        }[candidate_type]
        payload = record.model_dump(mode="json")
        searchable = MemoryRetriever.searchable_text(record_type, payload)
        signature = " ".join(sorted(set(meaningful_tokens(searchable))))
        return ProposedPassiveCandidate(
            candidate_type=candidate_type,
            record=payload,
            confidence=confidence,
            reason=reason,
            normalized_signature=signature or normalize_search_text(searchable),
        )


def threshold_for(candidate_type: CandidateType) -> float:
    return {
        CandidateType.FACT: FACT_THRESHOLD,
        CandidateType.DECISION: DECISION_THRESHOLD,
        CandidateType.COMMITMENT: COMMITMENT_THRESHOLD,
        CandidateType.RELATIONSHIP_MEMORY: RELATIONSHIP_THRESHOLD,
    }.get(candidate_type, 1.0)


def expiry_from(detected_at: datetime) -> datetime:
    return detected_at.astimezone(timezone.utc) + timedelta(days=CANDIDATE_EXPIRY_DAYS)
