"""Application-owned lifecycle and lineage for passive memory candidates."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from .memory_models import (
    CandidateStatus,
    CandidateType,
    Commitment,
    Decision,
    DecisionStatus,
    Fact,
    FactStatus,
    IdentityCode,
    MemoryCandidate,
    MemoryDocument,
    RelationshipMemory,
    RelationshipStatus,
    SourceType,
)
from .memory_retriever import MemoryRetriever
from .passive_detection import (
    DETECTOR_VERSION,
    ExistingMemoryRelation,
    MemoryCandidateDetectionRequest,
    MemoryCandidateDetectionResult,
    PassiveCandidatePayload,
    PassiveMemoryCandidateDetector,
    ProposedPassiveCandidate,
    expiry_from,
    threshold_for,
)
from .text_normalization import meaningful_tokens


PASSIVE_RECORD_TYPES = {
    CandidateType.FACT: ("fact", "facts", Fact),
    CandidateType.DECISION: ("decision", "decisions", Decision),
    CandidateType.COMMITMENT: ("commitment", "commitments", Commitment),
    CandidateType.RELATIONSHIP_MEMORY: (
        "relationship_memory",
        "relationship_memories",
        RelationshipMemory,
    ),
}


class PassiveObservationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    detection: MemoryCandidateDetectionResult
    persisted_candidates: tuple[MemoryCandidate, ...]
    duplicate_record_ids: tuple[str, ...] = ()
    duplicate_candidate_ids: tuple[str, ...] = ()
    failure_reason: str | None = None
    persistence_latency_ms: float = Field(default=0.0, ge=0.0)


class MemoryProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: str
    source: SourceType
    candidate_id: str
    conversation_id: str
    project_id: str
    evidence_message_ids: tuple[str, ...]
    detector_version: str
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)
    detected_at: AwareDatetime
    reviewed_by: IdentityCode
    reviewed_at: AwareDatetime
    relation: ExistingMemoryRelation
    related_memory_id: str | None


class CandidateConflictRequiresExplicitSupersession(ValueError):
    pass


class PassiveMemoryService:
    """Persist, review and explain candidates without treating them as truth."""

    def __init__(
        self,
        *,
        repository,
        detector: PassiveMemoryCandidateDetector,
        clock: Callable[[], datetime] | None = None,
    ):
        self.repository = repository
        self.detector = detector
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def observe(
        self,
        request: MemoryCandidateDetectionRequest,
    ) -> PassiveObservationResult:
        from time import perf_counter

        detection = self.detector.detect(request)
        if not detection.proposals:
            return PassiveObservationResult(
                detection=detection,
                persisted_candidates=(),
            )

        started = perf_counter()
        # Expiration is persisted and audited before novelty is evaluated, so
        # an old pending row can never masquerade as a live duplicate.
        self.list_pending()
        document = self._document()
        now = self._now()
        pending: list[MemoryCandidate] = []
        duplicate_records: list[str] = []
        duplicate_candidates: list[str] = []

        for proposal in detection.proposals:
            if proposal.confidence < threshold_for(proposal.candidate_type):
                continue
            duplicate_record = self._duplicate_record(document, proposal)
            if duplicate_record is not None:
                duplicate_records.append(duplicate_record)
                continue
            duplicate_candidate = self._duplicate_candidate(
                document,
                proposal,
                evidence_message_id=request.current_user_message.id,
            )
            if duplicate_candidate is not None:
                duplicate_candidates.append(duplicate_candidate)
                continue
            relation, related_id = self._relation(document, proposal)
            payload = PassiveCandidatePayload(
                record_type=PASSIVE_RECORD_TYPES[proposal.candidate_type][0],
                record=proposal.record,
                conversation_id=request.conversation_id,
                project_id=request.project_id,
                evidence_message_ids=(request.current_user_message.id,),
                detector_version=DETECTOR_VERSION,
                reason=proposal.reason,
                detected_at=now,
                expires_at=expiry_from(now),
                normalized_signature=proposal.normalized_signature,
                relation=relation,
                related_memory_id=related_id,
            )
            pending.append(
                MemoryCandidate(
                    id=f"candidate_{uuid4()}",
                    candidate_type=proposal.candidate_type,
                    proposed_payload=payload.model_dump(mode="json"),
                    status=CandidateStatus.PENDING,
                    confidence=proposal.confidence,
                    source=SourceType.CONVERSATION,
                    project_ids=[request.project_id],
                    evidence_episode_ids=[],
                    created_by=IdentityCode.SYSTEM,
                    reviewed_by=None,
                    created_at=now,
                    reviewed_at=None,
                    result_memory_id=None,
                )
            )

        if pending:
            raw = document.model_dump(mode="json")
            raw["memory_candidates"].extend(
                item.model_dump(mode="json") for item in pending
            )
            detected_events = tuple(
                {
                    "action": "candidate_detected",
                    "entity_type": "memory_candidate",
                    "entity_id": item.id,
                    "payload": self._lineage_payload(item),
                }
                for item in pending
            )
            first, *rest = detected_events
            self.repository.replace_document(
                MemoryDocument.model_validate(raw),
                action=first["action"],
                audit_payload=first["payload"],
                audit_entity_type=first["entity_type"],
                audit_entity_id=first["entity_id"],
                additional_audit_events=tuple(rest),
            )

        return PassiveObservationResult(
            detection=detection,
            persisted_candidates=tuple(pending),
            duplicate_record_ids=tuple(duplicate_records),
            duplicate_candidate_ids=tuple(duplicate_candidates),
            persistence_latency_ms=(perf_counter() - started) * 1_000,
        )

    def observe_safely(
        self,
        request: MemoryCandidateDetectionRequest,
    ) -> PassiveObservationResult:
        try:
            return self.observe(request)
        except Exception as error:
            try:
                self.repository.record_event(
                    action="candidate_detection_failed",
                    entity_type="conversation_message",
                    entity_id=request.current_user_message.id,
                    payload={
                        "conversation_id": request.conversation_id,
                        "detector_version": DETECTOR_VERSION,
                        "error_type": type(error).__name__,
                    },
                )
            except Exception:
                pass
            return PassiveObservationResult(
                detection=MemoryCandidateDetectionResult(
                    proposals=(),
                    skip_reason="detector_failure",
                    gate_latency_ms=0.0,
                    extraction_latency_ms=0.0,
                ),
                persisted_candidates=(),
                failure_reason=type(error).__name__,
            )

    def list_pending(self) -> tuple[MemoryCandidate, ...]:
        now = self._now()
        document = self._document()
        document, expired = self._expire_document(document, now)
        if expired:
            raw = document.model_dump(mode="json")
            events = tuple(
                {
                    "action": "candidate_expired",
                    "entity_type": "memory_candidate",
                    "entity_id": item.id,
                    "payload": self._lineage_payload(item),
                }
                for item in expired
            )
            first, *rest = events
            self.repository.replace_document(
                MemoryDocument.model_validate(raw),
                action=first["action"],
                audit_payload=first["payload"],
                audit_entity_type=first["entity_type"],
                audit_entity_id=first["entity_id"],
                additional_audit_events=tuple(rest),
            )
        return tuple(
            sorted(
                (
                    item
                    for item in document.memory_candidates
                    if item.status is CandidateStatus.PENDING
                    and self._is_passive(item)
                ),
                key=lambda item: (item.created_at, item.id),
            )
        )

    def approve(
        self,
        candidate_id: str,
        *,
        supersede_existing: bool = False,
    ):
        document = self._document()
        candidate = self._candidate(document, candidate_id)
        payload = self._payload(candidate)
        if candidate.status is CandidateStatus.APPROVED:
            return self._record_by_id(document, candidate.result_memory_id)
        if candidate.status is not CandidateStatus.PENDING:
            raise ValueError("memory candidate is not pending")
        if payload.expires_at <= self._now():
            self.expire(candidate_id)
            raise ValueError("memory candidate has expired")
        if (
            payload.relation is ExistingMemoryRelation.POSSIBLE_UPDATE
            and not supersede_existing
        ):
            raise CandidateConflictRequiresExplicitSupersession(
                "candidate requires explicit supersession approval"
            )

        record = self._record(candidate, payload)
        raw = document.model_dump(mode="json")
        if payload.relation is ExistingMemoryRelation.POSSIBLE_UPDATE:
            record = self._apply_supersession(raw, record, payload.related_memory_id)
            payload = payload.model_copy(update={"record": record.model_dump(mode="json")})

        _, collection, _ = PASSIVE_RECORD_TYPES[candidate.candidate_type]
        if any(item.get("id") == record.id for item in raw[collection]):
            existing = self._record_by_id(document, record.id)
            if existing != record:
                raise ValueError("candidate result memory ID already exists")
        else:
            raw[collection].append(record.model_dump(mode="json"))
        now = self._now()
        approved = candidate.model_copy(
            update={
                "proposed_payload": payload.model_dump(mode="json"),
                "status": CandidateStatus.APPROVED,
                "reviewed_by": IdentityCode.MISHA,
                "reviewed_at": now,
                "result_memory_id": record.id,
            }
        )
        self._replace_candidate(raw, approved)
        lineage = {
            **self._lineage_payload(approved),
            "result_memory_id": record.id,
            "reviewed_by": IdentityCode.MISHA.value,
            "reviewed_at": now.isoformat(),
        }
        self.repository.replace_document(
            MemoryDocument.model_validate(raw),
            action="candidate_approved",
            audit_payload=lineage,
            audit_entity_type="memory_candidate",
            audit_entity_id=approved.id,
            additional_audit_events=(
                {
                    "action": "memory_created_from_candidate",
                    "entity_type": payload.record_type,
                    "entity_id": record.id,
                    "payload": lineage,
                },
            ),
        )
        return record

    def reject(self, candidate_id: str) -> MemoryCandidate:
        document = self._document()
        candidate = self._candidate(document, candidate_id)
        self._payload(candidate)
        if candidate.status is CandidateStatus.REJECTED:
            return candidate
        if candidate.status is not CandidateStatus.PENDING:
            raise ValueError("memory candidate is not pending")
        now = self._now()
        rejected = candidate.model_copy(
            update={
                "status": CandidateStatus.REJECTED,
                "reviewed_by": IdentityCode.MISHA,
                "reviewed_at": now,
            }
        )
        raw = document.model_dump(mode="json")
        self._replace_candidate(raw, rejected)
        self.repository.replace_document(
            MemoryDocument.model_validate(raw),
            action="candidate_rejected",
            audit_payload={
                **self._lineage_payload(rejected),
                "reviewed_by": IdentityCode.MISHA.value,
                "reviewed_at": now.isoformat(),
            },
            audit_entity_type="memory_candidate",
            audit_entity_id=rejected.id,
        )
        return rejected

    def expire(self, candidate_id: str) -> MemoryCandidate:
        document = self._document()
        candidate = self._candidate(document, candidate_id)
        self._payload(candidate)
        if candidate.status is CandidateStatus.EXPIRED:
            return candidate
        if candidate.status is not CandidateStatus.PENDING:
            raise ValueError("memory candidate is not pending")
        expired = candidate.model_copy(update={"status": CandidateStatus.EXPIRED})
        raw = document.model_dump(mode="json")
        self._replace_candidate(raw, expired)
        self.repository.replace_document(
            MemoryDocument.model_validate(raw),
            action="candidate_expired",
            audit_payload=self._lineage_payload(expired),
            audit_entity_type="memory_candidate",
            audit_entity_id=expired.id,
        )
        return expired

    def provenance(self, record_id: str) -> MemoryProvenance:
        document = self._document()
        candidate = next(
            (
                item
                for item in document.memory_candidates
                if item.result_memory_id == record_id and self._is_passive(item)
            ),
            None,
        )
        if candidate is None or candidate.status is not CandidateStatus.APPROVED:
            raise KeyError("passive memory provenance not found")
        payload = self._payload(candidate)
        if candidate.reviewed_by is None or candidate.reviewed_at is None:
            raise ValueError("approved candidate has incomplete review lineage")
        audit_match = any(
            event["action"] == "memory_created_from_candidate"
            and event["entity_id"] == record_id
            and event["payload"].get("candidate_id") == candidate.id
            for event in self.repository.list_audit_events()
        )
        if not audit_match:
            raise ValueError("passive memory audit lineage is incomplete")
        record = self._record_by_id(document, record_id)
        return MemoryProvenance(
            record_id=record_id,
            source=record.source,
            candidate_id=candidate.id,
            conversation_id=payload.conversation_id,
            project_id=payload.project_id,
            evidence_message_ids=payload.evidence_message_ids,
            detector_version=payload.detector_version,
            reason=payload.reason,
            confidence=candidate.confidence,
            detected_at=payload.detected_at,
            reviewed_by=candidate.reviewed_by,
            reviewed_at=candidate.reviewed_at,
            relation=payload.relation,
            related_memory_id=payload.related_memory_id,
        )

    def _expire_document(
        self,
        document: MemoryDocument,
        now: datetime,
    ) -> tuple[MemoryDocument, tuple[MemoryCandidate, ...]]:
        expired: list[MemoryCandidate] = []
        raw = document.model_dump(mode="json")
        for candidate in document.memory_candidates:
            if candidate.status is not CandidateStatus.PENDING or not self._is_passive(candidate):
                continue
            payload = self._payload(candidate)
            if payload.expires_at <= now:
                updated = candidate.model_copy(update={"status": CandidateStatus.EXPIRED})
                self._replace_candidate(raw, updated)
                expired.append(updated)
        return MemoryDocument.model_validate(raw), tuple(expired)

    def _duplicate_record(
        self,
        document: MemoryDocument,
        proposal: ProposedPassiveCandidate,
    ) -> str | None:
        _, collection, _ = PASSIVE_RECORD_TYPES[proposal.candidate_type]
        for record in getattr(document, collection):
            if not self._active(record):
                continue
            if self._same_meaning(proposal.normalized_signature, self._signature(record, proposal.candidate_type)):
                return record.id
        return None

    def _duplicate_candidate(
        self,
        document: MemoryDocument,
        proposal: ProposedPassiveCandidate,
        *,
        evidence_message_id: str,
    ) -> str | None:
        for candidate in document.memory_candidates:
            if not self._is_passive(candidate):
                continue
            payload = self._payload(candidate)
            same_meaning = (
                candidate.candidate_type is proposal.candidate_type
                and self._same_meaning(proposal.normalized_signature, payload.normalized_signature)
            )
            if same_meaning and (
                candidate.status is CandidateStatus.PENDING
                or evidence_message_id in payload.evidence_message_ids
            ):
                return candidate.id
        return None

    def _relation(
        self,
        document: MemoryDocument,
        proposal: ProposedPassiveCandidate,
    ) -> tuple[ExistingMemoryRelation, str | None]:
        _, collection, model = PASSIVE_RECORD_TYPES[proposal.candidate_type]
        candidate_record = model.model_validate(proposal.record)
        for existing in getattr(document, collection):
            if not self._active(existing):
                continue
            if isinstance(candidate_record, Fact) and candidate_record.key == existing.key:
                if candidate_record.key in {"preference", "routine"}:
                    candidate_tokens = set(
                        self._meaning_tokens(proposal.normalized_signature)
                    )
                    existing_tokens = set(
                        self._meaning_tokens(
                            self._signature(existing, proposal.candidate_type)
                        )
                    )
                    if not candidate_tokens & existing_tokens:
                        continue
                return ExistingMemoryRelation.POSSIBLE_UPDATE, existing.id
            if isinstance(candidate_record, Decision):
                candidate_tokens = set(self._meaning_tokens(proposal.normalized_signature))
                existing_tokens = set(self._meaning_tokens(self._signature(existing, proposal.candidate_type)))
                if candidate_tokens & existing_tokens and any(
                    marker in candidate_record.decision.casefold()
                    for marker in ("теперь", "всё", "оставляем", "будет")
                ):
                    return ExistingMemoryRelation.POSSIBLE_UPDATE, existing.id
        return ExistingMemoryRelation.NEW, None

    @staticmethod
    def _apply_supersession(raw: dict, record, related_id: str | None):
        if related_id is None:
            raise ValueError("possible update has no related memory")
        if isinstance(record, Fact):
            index = next(i for i, item in enumerate(raw["facts"]) if item["id"] == related_id)
            old = Fact.model_validate(raw["facts"][index])
            record = record.model_copy(update={"supersedes_id": old.id})
            raw["facts"][index] = old.model_copy(
                update={"status": FactStatus.SUPERSEDED, "superseded_by": record.id, "updated_at": record.updated_at}
            ).model_dump(mode="json")
            return record
        if isinstance(record, Decision):
            index = next(i for i, item in enumerate(raw["decisions"]) if item["id"] == related_id)
            old = Decision.model_validate(raw["decisions"][index])
            record = record.model_copy(update={"supersedes_id": old.id})
            raw["decisions"][index] = old.model_copy(
                update={"status": DecisionStatus.SUPERSEDED, "superseded_by": record.id, "updated_at": record.updated_at}
            ).model_dump(mode="json")
            return record
        if isinstance(record, RelationshipMemory):
            index = next(i for i, item in enumerate(raw["relationship_memories"]) if item["id"] == related_id)
            old = RelationshipMemory.model_validate(raw["relationship_memories"][index])
            record = record.model_copy(update={"revises_id": old.id})
            raw["relationship_memories"][index] = old.model_copy(
                update={"status": RelationshipStatus.REVISED}
            ).model_dump(mode="json")
            return record
        raise ValueError("candidate type does not support supersession")

    @staticmethod
    def _active(record) -> bool:
        status = getattr(record, "status", None)
        return status is None or status.value in {"active", "open", "current"}

    @staticmethod
    def _signature(record, candidate_type: CandidateType) -> str:
        record_type = PASSIVE_RECORD_TYPES[candidate_type][0]
        searchable = MemoryRetriever.searchable_text(
            record_type,
            record.model_dump(mode="json"),
        )
        return " ".join(sorted(set(meaningful_tokens(searchable))))

    @classmethod
    def _same_meaning(cls, left: str, right: str) -> bool:
        left_tokens = set(cls._meaning_tokens(left))
        right_tokens = set(cls._meaning_tokens(right))
        if not left_tokens or not right_tokens:
            return left == right
        overlap = len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))
        return overlap >= 0.8

    @staticmethod
    def _meaning_tokens(signature: str) -> tuple[str, ...]:
        ignored = {
            "misha", "миш", "fact", "факт", "preference", "предпочтен",
            "explicit", "statement", "разговор", "решен", "project",
            "обычн", "всегд", "люб", "пью", "оставля",
        }
        return tuple(token for token in signature.split() if token not in ignored)

    @staticmethod
    def _record(candidate: MemoryCandidate, payload: PassiveCandidatePayload):
        expected_type, _, model = PASSIVE_RECORD_TYPES[candidate.candidate_type]
        if payload.record_type != expected_type:
            raise ValueError("candidate payload type mismatch")
        record = model.model_validate(payload.record)
        if record.source is not SourceType.CONVERSATION:
            raise ValueError("reviewed passive record must preserve conversation source")
        return record

    @staticmethod
    def _record_by_id(document: MemoryDocument, record_id: str | None):
        for collection in (
            document.facts,
            document.decisions,
            document.commitments,
            document.relationship_memories,
        ):
            for record in collection:
                if record.id == record_id:
                    return record
        raise KeyError("candidate result memory not found")

    @staticmethod
    def _replace_candidate(raw: dict, candidate: MemoryCandidate) -> None:
        index = next(
            index
            for index, item in enumerate(raw["memory_candidates"])
            if item["id"] == candidate.id
        )
        raw["memory_candidates"][index] = candidate.model_dump(mode="json")

    @staticmethod
    def _lineage_payload(candidate: MemoryCandidate) -> dict:
        payload = PassiveCandidatePayload.model_validate(candidate.proposed_payload)
        return {
            "candidate_id": candidate.id,
            "candidate_type": candidate.candidate_type.value,
            "conversation_id": payload.conversation_id,
            "project_id": payload.project_id,
            "evidence_message_ids": list(payload.evidence_message_ids),
            "detector_version": payload.detector_version,
            "reason": payload.reason,
            "confidence": candidate.confidence,
            "relation": payload.relation.value,
            "related_memory_id": payload.related_memory_id,
        }

    @staticmethod
    def _is_passive(candidate: MemoryCandidate) -> bool:
        return candidate.proposed_payload.get("version") == "passive_candidate_v1"

    @classmethod
    def _payload(cls, candidate: MemoryCandidate) -> PassiveCandidatePayload:
        if not cls._is_passive(candidate):
            raise ValueError("candidate is not a passive-memory candidate")
        return PassiveCandidatePayload.model_validate(candidate.proposed_payload)

    @classmethod
    def _candidate(cls, document: MemoryDocument, candidate_id: str) -> MemoryCandidate:
        candidate = next(
            (item for item in document.memory_candidates if item.id == candidate_id),
            None,
        )
        if candidate is None or not cls._is_passive(candidate):
            raise KeyError("passive memory candidate not found")
        return candidate

    def _document(self) -> MemoryDocument:
        document = self.repository.read_document()
        if document is None:
            raise ValueError("memory store is empty")
        return document

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("candidate lifecycle clock must be timezone-aware")
        return value.astimezone(timezone.utc)
