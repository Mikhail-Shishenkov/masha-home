"""Evidence-linked Masha reflections and the bounded Honest Help bridge."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from backend.llm.model_models import ModelMessage, ModelRequest, PrivacyScope
from backend.llm.model_provider import ModelProviderUnavailableError, ModelTimeoutError
from backend.memory.memory_models import (
    CandidateStatus,
    CandidateType,
    IdentityCode,
    MashaReflection,
    MemoryCandidate,
    MemoryDocument,
    SourceType,
    Visibility,
)
from backend.memory.memory_retriever import MemoryRetrievalRequest


class ReflectionScope(str, Enum):
    SELF = "self"
    SHARED = "shared"
    HELP_LEARNING = "help_learning"


class HelpOffer(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    observation: str = Field(min_length=5, max_length=400)
    offer: str = Field(min_length=5, max_length=400)
    expected_benefit: str = Field(min_length=5, max_length=300)
    why_now: str = Field(min_length=5, max_length=300)
    capability: Literal["conversation"] = "conversation"


class GeneratedReflection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=10, max_length=700)
    meaning: str = Field(min_length=8, max_length=500)
    confidence: float = Field(ge=0.0, le=1.0)
    importance: float = Field(ge=0.0, le=1.0)
    help_offer: HelpOffer | None = None


class ReflectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate: MemoryCandidate
    reflection: MashaReflection | None
    scope: ReflectionScope
    adopted: bool
    duplicate_of: str | None = None


class ReflectionView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reflection: MashaReflection
    scope: ReflectionScope
    candidate_id: str
    evidence_message_ids: tuple[str, ...]
    help_offer: HelpOffer | None


class ReflectionGenerationError(RuntimeError):
    pass


class ReflectionUnavailableError(RuntimeError):
    pass


_DIAGNOSIS_PATTERNS = (
    re.compile(r"\bу\s+миши\s+(?:депресси|травм|расстройств|выгоран)", re.IGNORECASE),
    re.compile(r"\bмиша\s+(?:депрессив|травмирован|психически|болен)", re.IGNORECASE),
    re.compile(r"\bдиагноз\s+миши\b", re.IGNORECASE),
)
_FALSE_ACTION_PATTERNS = (
    re.compile(r"\bя\s+(?:уже\s+)?(?:отправила|запустила|удалила|изменила|скачала)\b", re.IGNORECASE),
    re.compile(r"\bя\s+(?:сама\s+)?напишу\s+(?:позже|потом)\b", re.IGNORECASE),
)
_WORD = re.compile(r"[a-zа-яё0-9]+", re.IGNORECASE)


class ReflectionService:
    """One local generation per explicit reflection request; no background loop."""

    def __init__(
        self,
        *,
        repository,
        identity_kernel,
        memory_retriever,
        router,
        model_profiles,
        clock: Callable[[], datetime] | None = None,
        evidence_limit: int = 4,
        conversation_limit: int = 8,
    ):
        self.repository = repository
        self.identity_kernel = identity_kernel
        self.memory_retriever = memory_retriever
        self.router = router
        self.model_profiles = model_profiles
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self.evidence_limit = evidence_limit
        self.conversation_limit = conversation_limit

    def reflect(
        self,
        *,
        scope: ReflectionScope,
        topic: str,
        project_id: str,
        conversation_id: str,
        evidence_message_ids: tuple[str, ...],
        conversation_messages: tuple,
        reconsiders_reflection_id: str | None = None,
        outcome: Literal["helped", "not_helped"] | None = None,
    ) -> ReflectionResult:
        topic = topic.strip()
        if not topic:
            raise ValueError("reflection topic cannot be empty")
        if not evidence_message_ids:
            raise ValueError("reflection requires conversation evidence")
        document = self._document()
        if reconsiders_reflection_id is not None and not any(
            item.id == reconsiders_reflection_id for item in document.reflections
        ):
            raise KeyError("reflection to reconsider was not found")
        evidence = self._select_memory_evidence(topic, project_id)
        generated = self._generate(
            scope=scope,
            topic=topic,
            evidence=evidence,
            conversation_messages=conversation_messages,
            reconsiders_reflection_id=reconsiders_reflection_id,
            outcome=outcome,
        )
        self._validate_generated(generated, scope)
        duplicate = self._duplicate(document, generated)
        if duplicate is not None:
            return ReflectionResult(
                candidate=self._duplicate_candidate(
                    generated,
                    scope=scope,
                    topic=topic,
                    project_id=project_id,
                    conversation_id=conversation_id,
                    evidence_message_ids=evidence_message_ids,
                    duplicate_id=duplicate.id,
                ),
                reflection=None,
                scope=scope,
                adopted=False,
                duplicate_of=duplicate.id,
            )

        now = self._now()
        memory_ids = tuple(item["data"]["id"] for item in evidence)
        episode_ids = tuple(
            item["data"]["id"] for item in evidence if item["type"] == "episode"
        )
        reflection = MashaReflection(
            id=f"reflection_{uuid4()}",
            text=generated.text.strip(),
            meaning=generated.meaning.strip(),
            importance=generated.importance,
            confidence=generated.confidence,
            source=SourceType.INFERENCE,
            visibility=Visibility.VISIBLE,
            project_ids=[project_id],
            source_episode_ids=list(episode_ids),
            related_memory_ids=list(dict.fromkeys((*memory_ids, *(() if reconsiders_reflection_id is None else (reconsiders_reflection_id,))))),
            reconsiders_reflection_id=reconsiders_reflection_id,
            created_at=now,
        )
        auto_adopt = scope == ReflectionScope.SELF or (
            scope == ReflectionScope.HELP_LEARNING and outcome is not None
        )
        auto_adopt = auto_adopt and generated.confidence >= 0.55
        candidate = self._candidate(
            reflection,
            generated,
            scope=scope,
            topic=topic,
            project_id=project_id,
            conversation_id=conversation_id,
            evidence_message_ids=evidence_message_ids,
            episode_ids=episode_ids,
            outcome=outcome,
            auto_adopt=auto_adopt,
        )
        self._persist_new(document, candidate, reflection if auto_adopt else None)
        return ReflectionResult(
            candidate=candidate,
            reflection=reflection if auto_adopt else None,
            scope=scope,
            adopted=auto_adopt,
        )

    def adopt(self, candidate_id: str, *, reviewed_by: IdentityCode = IdentityCode.MISHA) -> MashaReflection:
        document = self._document()
        candidate = self._candidate_by_id(document, candidate_id)
        if candidate.candidate_type != CandidateType.REFLECTION:
            raise ValueError("candidate is not a reflection")
        if candidate.status == CandidateStatus.APPROVED:
            reflection = self._reflection_by_id(document, candidate.result_memory_id)
            assert reflection is not None
            return reflection
        if candidate.status != CandidateStatus.PENDING:
            raise ValueError("reflection candidate is not pending")
        reflection = MashaReflection.model_validate(candidate.proposed_payload["reflection"])
        duplicate = self._duplicate(document, GeneratedReflection(
            text=reflection.text,
            meaning=reflection.meaning,
            confidence=reflection.confidence,
            importance=reflection.importance,
            help_offer=self._help_offer(candidate),
        ))
        if duplicate is not None:
            raise ValueError(f"reflection duplicates {duplicate.id}")
        now = self._now()
        approved = candidate.model_copy(
            update={
                "status": CandidateStatus.APPROVED,
                "reviewed_by": reviewed_by,
                "reviewed_at": now,
                "result_memory_id": reflection.id,
            }
        )
        payload = document.model_dump(mode="json")
        index = next(index for index, item in enumerate(payload["memory_candidates"]) if item["id"] == candidate.id)
        payload["memory_candidates"][index] = approved.model_dump(mode="json")
        payload["reflections"].append(reflection.model_dump(mode="json"))
        self.repository.replace_document(
            MemoryDocument.model_validate(payload),
            action="reflection_adopted",
            audit_payload={
                "who": reviewed_by.value,
                "candidate_id": candidate.id,
                "record_id": reflection.id,
                "scope": candidate.proposed_payload["scope"],
            },
        )
        return reflection

    def reject(self, candidate_id: str) -> MemoryCandidate:
        document = self._document()
        candidate = self._candidate_by_id(document, candidate_id)
        if candidate.status == CandidateStatus.REJECTED:
            return candidate
        if candidate.status != CandidateStatus.PENDING:
            raise ValueError("reflection candidate is not pending")
        rejected = candidate.model_copy(
            update={
                "status": CandidateStatus.REJECTED,
                "reviewed_by": IdentityCode.MISHA,
                "reviewed_at": self._now(),
            }
        )
        payload = document.model_dump(mode="json")
        index = next(index for index, item in enumerate(payload["memory_candidates"]) if item["id"] == candidate.id)
        payload["memory_candidates"][index] = rejected.model_dump(mode="json")
        self.repository.replace_document(
            MemoryDocument.model_validate(payload),
            action="reflection_rejected",
            audit_payload={"who": "misha", "candidate_id": candidate.id},
        )
        return rejected

    def reflections(self) -> tuple[ReflectionView, ...]:
        document = self._document()
        candidates = {
            item.result_memory_id: item
            for item in document.memory_candidates
            if item.candidate_type == CandidateType.REFLECTION
            and item.status == CandidateStatus.APPROVED
            and item.result_memory_id is not None
        }
        views = []
        for reflection in sorted(document.reflections, key=lambda item: item.created_at, reverse=True):
            candidate = candidates.get(reflection.id)
            if candidate is None:
                continue
            evidence = candidate.proposed_payload.get("evidence", {})
            views.append(
                ReflectionView(
                    reflection=reflection,
                    scope=ReflectionScope(candidate.proposed_payload["scope"]),
                    candidate_id=candidate.id,
                    evidence_message_ids=tuple(evidence.get("conversation_message_ids", [])),
                    help_offer=self._help_offer(candidate),
                )
            )
        return tuple(views)

    def pending(self, *, conversation_id: str | None = None) -> tuple[MemoryCandidate, ...]:
        document = self._document()
        rows = [
            item
            for item in document.memory_candidates
            if item.candidate_type == CandidateType.REFLECTION
            and item.status == CandidateStatus.PENDING
            and (
                conversation_id is None
                or item.proposed_payload.get("conversation_id") == conversation_id
            )
        ]
        return tuple(sorted(rows, key=lambda item: item.created_at, reverse=True))

    def find_reflection(self, query: str) -> MashaReflection:
        needle = query.strip().casefold()
        matches = [
            view.reflection
            for view in self.reflections()
            if needle in view.reflection.text.casefold()
            or needle in view.reflection.meaning.casefold()
            or needle == view.reflection.id.casefold()
        ]
        if not matches:
            raise LookupError("reflection not found")
        if len(matches) > 1:
            raise ValueError("reflection query is ambiguous")
        return matches[0]

    def pending_help(self, *, conversation_id: str | None = None) -> tuple[MemoryCandidate, ...]:
        outcomes = self._help_outcomes()
        rows = []
        for candidate in self._document().memory_candidates:
            if candidate.candidate_type != CandidateType.REFLECTION or candidate.status != CandidateStatus.APPROVED:
                continue
            if self._help_offer(candidate) is None:
                continue
            if conversation_id is not None and candidate.proposed_payload.get("conversation_id") != conversation_id:
                continue
            if outcomes.get(candidate.id) in {"delivered", "rejected"}:
                continue
            rows.append(candidate)
        return tuple(sorted(rows, key=lambda item: item.created_at, reverse=True))

    def accept_help(self, candidate_id: str, *, conversation_messages: tuple) -> str:
        candidate = self._candidate_by_id(self._document(), candidate_id)
        offer = self._help_offer(candidate)
        if candidate.status != CandidateStatus.APPROVED or offer is None:
            raise ValueError("candidate has no adopted help offer")
        outcomes = self._help_outcomes()
        if outcomes.get(candidate.id) == "delivered":
            return "Это предложение помощи уже было принято и обработано."
        if outcomes.get(candidate.id) == "rejected":
            raise ValueError("help offer was rejected")
        if outcomes.get(candidate.id) != "accepted":
            self.repository.record_event(
                action="help_offer_accepted",
                entity_type="reflection_candidate",
                entity_id=candidate.id,
                payload={"who": "misha", "capability": offer.capability},
            )
        response = self._generate_help(offer, candidate, conversation_messages)
        self.repository.record_event(
            action="help_offer_delivered",
            entity_type="reflection_candidate",
            entity_id=candidate.id,
            payload={"capability": offer.capability, "model_profile": self.model_profiles.get_active_profile().profile_id},
        )
        return response

    def reject_help(self, candidate_id: str) -> None:
        candidate = self._candidate_by_id(self._document(), candidate_id)
        if self._help_offer(candidate) is None:
            raise ValueError("candidate has no help offer")
        if self._help_outcomes().get(candidate.id) == "rejected":
            return
        self.repository.record_event(
            action="help_offer_rejected",
            entity_type="reflection_candidate",
            entity_id=candidate.id,
            payload={"who": "misha"},
        )

    def _generate(
        self,
        *,
        scope: ReflectionScope,
        topic: str,
        evidence: list[dict],
        conversation_messages: tuple,
        reconsiders_reflection_id: str | None,
        outcome: str | None,
    ) -> GeneratedReflection:
        profile = self.model_profiles.get_active_profile()
        if "structured_output" not in profile.capabilities:
            raise ReflectionUnavailableError(
                f"профиль {profile.profile_id} не поддерживает structured reflection"
            )
        evidence_context = [self._evidence_record(item) for item in evidence]
        recent = [
            {"role": message.role.value, "content": message.content}
            for message in conversation_messages[-self.conversation_limit:]
        ]
        request = ModelRequest(
            messages=(
                ModelMessage(
                    role="user",
                    content=(
                        "Создай одну краткую рефлексию Маши по теме: "
                        f"{topic}\nВерни только JSON без markdown: "
                        '{"text":"...","meaning":"...","confidence":0.0,'
                        '"importance":0.0,"help_offer":null}. '
                        "help_offer либо null, либо объект с observation, offer, "
                        "expected_benefit, why_now и capability=conversation."
                    ),
                ),
            ),
            identity_context=self.identity_kernel.build_context(),
            private_context={
                "task": "masha_reflection_candidate",
                "scope": scope.value,
                "reflection_contract": (
                    "Пиши от лица Маши, живо и честно. Рефлексия — субъективное "
                    "осмысление, не Fact и не диагноз Миши. Не выдумывай evidence, "
                    "выполненные действия или возможности. Можно спорить, шутить и "
                    "материться, если это органично; не превращай текст в корпоративную "
                    "психотерапию. help_offer делай только конкретным и выполнимым в "
                    "обычном разговоре без tools. Если полезного предложения нет — null."
                ),
                "evidence_memory": evidence_context,
                "recent_conversation": recent,
                "reconsiders_reflection_id": reconsiders_reflection_id,
                "outcome": outcome,
                "current_utc": self._now().isoformat(),
            },
            privacy_scope=PrivacyScope.LOCAL_ONLY,
            preferred_provider_id=profile.provider_id,
            execution_model_id=profile.model_id,
            execution_think=False,
            timeout_seconds=profile.timeout_seconds,
        )
        try:
            response = self.router.generate(request)
        except (ModelProviderUnavailableError, ModelTimeoutError) as error:
            raise ReflectionUnavailableError("локальная модель недоступна для рефлексии") from error
        try:
            return GeneratedReflection.model_validate(self._parse_json(response.text))
        except (ValueError, json.JSONDecodeError) as error:
            raise ReflectionGenerationError("локальная модель вернула некорректную рефлексию") from error

    def _generate_help(self, offer: HelpOffer, candidate: MemoryCandidate, conversation_messages: tuple) -> str:
        profile = self.model_profiles.get_active_profile()
        request = ModelRequest(
            messages=(
                ModelMessage(
                    role="user",
                    content=(
                        "Миша явно принял предложение помощи. Дай первый конкретный "
                        "полезный результат в рамках обычного разговора. Не утверждай, "
                        "что запускала tools или изменила данные."
                    ),
                ),
            ),
            identity_context=self.identity_kernel.build_context(),
            private_context={
                "task": "accepted_honest_help_offer",
                "help_offer": offer.model_dump(mode="json"),
                "reflection": candidate.proposed_payload["reflection"],
                "recent_conversation": [
                    {"role": item.role.value, "content": item.content}
                    for item in conversation_messages[-self.conversation_limit:]
                ],
                "capability_contract": (
                    "Разрешена только разговорная помощь: анализ, объяснение, план, "
                    "текст или вопрос. Tools и внешние действия отсутствуют."
                ),
            },
            privacy_scope=PrivacyScope.LOCAL_ONLY,
            preferred_provider_id=profile.provider_id,
            execution_model_id=profile.model_id,
            execution_think=False,
            timeout_seconds=profile.timeout_seconds,
        )
        try:
            return self.router.generate(request).text
        except (ModelProviderUnavailableError, ModelTimeoutError) as error:
            raise ReflectionUnavailableError("локальная модель недоступна для помощи") from error

    def _candidate(
        self,
        reflection: MashaReflection,
        generated: GeneratedReflection,
        *,
        scope: ReflectionScope,
        topic: str,
        project_id: str,
        conversation_id: str,
        evidence_message_ids: tuple[str, ...],
        episode_ids: tuple[str, ...],
        outcome: str | None,
        auto_adopt: bool,
    ) -> MemoryCandidate:
        now = self._now()
        return MemoryCandidate(
            id=f"candidate_{uuid4()}",
            candidate_type=CandidateType.REFLECTION,
            proposed_payload={
                "reflection": reflection.model_dump(mode="json"),
                "scope": scope.value,
                "topic": topic,
                "conversation_id": conversation_id,
                "evidence": {
                    "conversation_message_ids": list(evidence_message_ids),
                    "memory_ids": list(reflection.related_memory_ids),
                },
                "outcome": outcome,
                "help_offer": None if generated.help_offer is None else generated.help_offer.model_dump(mode="json"),
            },
            status=CandidateStatus.APPROVED if auto_adopt else CandidateStatus.PENDING,
            confidence=reflection.confidence,
            source=SourceType.INFERENCE,
            project_ids=[project_id],
            evidence_episode_ids=list(episode_ids),
            created_by=IdentityCode.MASHA,
            reviewed_by=IdentityCode.SYSTEM if auto_adopt else None,
            created_at=now,
            reviewed_at=now if auto_adopt else None,
            result_memory_id=reflection.id if auto_adopt else None,
        )

    def _duplicate_candidate(
        self,
        generated: GeneratedReflection,
        *,
        scope: ReflectionScope,
        topic: str,
        project_id: str,
        conversation_id: str,
        evidence_message_ids: tuple[str, ...],
        duplicate_id: str,
    ) -> MemoryCandidate:
        now = self._now()
        return MemoryCandidate(
            id=f"candidate_duplicate_{uuid4()}",
            candidate_type=CandidateType.REFLECTION,
            proposed_payload={
                "reflection": {
                    "text": generated.text,
                    "meaning": generated.meaning,
                },
                "scope": scope.value,
                "topic": topic,
                "conversation_id": conversation_id,
                "evidence": {"conversation_message_ids": list(evidence_message_ids), "memory_ids": []},
                "duplicate_of": duplicate_id,
                "help_offer": None,
            },
            status=CandidateStatus.REJECTED,
            confidence=generated.confidence,
            source=SourceType.SYSTEM,
            project_ids=[project_id],
            evidence_episode_ids=[],
            created_by=IdentityCode.SYSTEM,
            reviewed_by=IdentityCode.SYSTEM,
            created_at=now,
            reviewed_at=now,
            result_memory_id=None,
        )

    def _persist_new(
        self,
        document: MemoryDocument,
        candidate: MemoryCandidate,
        reflection: MashaReflection | None,
    ) -> None:
        payload = document.model_dump(mode="json")
        payload["memory_candidates"].append(candidate.model_dump(mode="json"))
        if reflection is not None:
            payload["reflections"].append(reflection.model_dump(mode="json"))
        self.repository.replace_document(
            MemoryDocument.model_validate(payload),
            action="reflection_adopted" if reflection is not None else "reflection_candidate_created",
            audit_payload={
                "who": "system" if reflection is not None else "masha",
                "candidate_id": candidate.id,
                "record_id": None if reflection is None else reflection.id,
                "scope": candidate.proposed_payload["scope"],
                "auto_adopted": reflection is not None,
            },
        )

    def _select_memory_evidence(self, topic: str, project_id: str) -> list[dict]:
        return self.memory_retriever.retrieve(
            MemoryRetrievalRequest(
                query=topic,
                project_id=project_id,
                limit=self.evidence_limit,
                memory_budget_chars=6_000,
            )
        )

    @staticmethod
    def _evidence_record(item: dict) -> dict:
        data = item["data"]
        record = {
            "record_type": item["type"],
            "id": data["id"],
            "source": data.get("source"),
        }
        for field in (
            "subject", "key", "value", "title", "decision", "text", "summary",
            "meaning", "kind", "content", "status", "occurred_at",
        ):
            if field in data:
                record[field] = data[field]
        return record

    @classmethod
    def _duplicate(cls, document: MemoryDocument, generated: GeneratedReflection) -> MashaReflection | None:
        candidate_words = cls._words(f"{generated.text} {generated.meaning}")
        for reflection in document.reflections:
            existing = cls._words(f"{reflection.text} {reflection.meaning}")
            if candidate_words == existing:
                return reflection
            union = candidate_words | existing
            if union and len(candidate_words & existing) / len(union) >= 0.78:
                return reflection
        return None

    @staticmethod
    def _validate_generated(generated: GeneratedReflection, scope: ReflectionScope) -> None:
        combined = " ".join(
            filter(
                None,
                (
                    generated.text,
                    generated.meaning,
                    None if generated.help_offer is None else generated.help_offer.observation,
                    None if generated.help_offer is None else generated.help_offer.offer,
                ),
            )
        )
        if any(pattern.search(combined) for pattern in _DIAGNOSIS_PATTERNS):
            raise ReflectionGenerationError("reflection contains an unsupported diagnosis")
        if any(pattern.search(combined) for pattern in _FALSE_ACTION_PATTERNS):
            raise ReflectionGenerationError("reflection claims an unverified action")
        if scope == ReflectionScope.SELF and generated.confidence < 0.25:
            raise ReflectionGenerationError("self reflection confidence is too low")

    def _help_outcomes(self) -> dict[str, str]:
        outcomes: dict[str, str] = {}
        mapping = {
            "help_offer_accepted": "accepted",
            "help_offer_delivered": "delivered",
            "help_offer_rejected": "rejected",
        }
        for event in self.repository.list_audit_events():
            if event["action"] in mapping and event["entity_id"]:
                outcomes[event["entity_id"]] = mapping[event["action"]]
        return outcomes

    @staticmethod
    def _help_offer(candidate: MemoryCandidate) -> HelpOffer | None:
        raw = candidate.proposed_payload.get("help_offer")
        return None if raw is None else HelpOffer.model_validate(raw)

    @staticmethod
    def _candidate_by_id(document: MemoryDocument, candidate_id: str) -> MemoryCandidate:
        candidate = next((item for item in document.memory_candidates if item.id == candidate_id), None)
        if candidate is None:
            raise KeyError("reflection candidate not found")
        return candidate

    @staticmethod
    def _reflection_by_id(document: MemoryDocument, reflection_id: str | None) -> MashaReflection | None:
        return next((item for item in document.reflections if item.id == reflection_id), None)

    @staticmethod
    def _parse_json(text: str) -> dict:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
            stripped = re.sub(r"\s*```$", "", stripped)
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end < start:
            raise json.JSONDecodeError("no JSON object", stripped, 0)
        return json.loads(stripped[start : end + 1])

    @staticmethod
    def _words(value: str) -> set[str]:
        return {word.casefold() for word in _WORD.findall(value) if len(word) >= 3}

    def _document(self) -> MemoryDocument:
        document = self.repository.read_document()
        if document is None:
            raise ValueError("memory store is empty")
        return document

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("reflection clock must return aware datetime")
        return value.astimezone(timezone.utc)
