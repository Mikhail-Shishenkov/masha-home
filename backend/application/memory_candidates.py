"""Typed application boundary for future passive-memory review UI."""

from __future__ import annotations

from backend.memory.candidate_lifecycle import PassiveMemoryService
from backend.memory.passive_detection import (
    ExistingMemoryRelation,
    PassiveCandidatePayload,
)

from .contracts import (
    MemoryProvenanceView,
    PassiveMemoryCandidateResolutionView,
    PassiveMemoryCandidateView,
)


class MemoryCandidateApplicationService:
    def __init__(self, lifecycle: PassiveMemoryService):
        self.lifecycle = lifecycle

    def list_pending_memory_candidates(
        self,
    ) -> tuple[PassiveMemoryCandidateView, ...]:
        return tuple(self._view(item) for item in self.lifecycle.list_pending())

    def approve_memory_candidate(
        self,
        candidate_id: str,
        *,
        supersede_existing: bool = False,
    ) -> PassiveMemoryCandidateResolutionView:
        record = self.lifecycle.approve(
            candidate_id,
            supersede_existing=supersede_existing,
        )
        return PassiveMemoryCandidateResolutionView(
            candidate_id=candidate_id,
            status="approved",
            result_memory_id=record.id,
        )

    def reject_memory_candidate(
        self,
        candidate_id: str,
    ) -> PassiveMemoryCandidateResolutionView:
        self.lifecycle.reject(candidate_id)
        return PassiveMemoryCandidateResolutionView(
            candidate_id=candidate_id,
            status="rejected",
            result_memory_id=None,
        )

    def memory_provenance(self, record_id: str) -> MemoryProvenanceView:
        provenance = self.lifecycle.provenance(record_id)
        return MemoryProvenanceView(
            record_id=provenance.record_id,
            source=provenance.source.value,
            candidate_id=provenance.candidate_id,
            conversation_id=provenance.conversation_id,
            project_id=provenance.project_id,
            evidence_message_ids=provenance.evidence_message_ids,
            detector_version=provenance.detector_version,
            reason=provenance.reason,
            confidence=provenance.confidence,
            detected_at=provenance.detected_at,
            reviewed_by=provenance.reviewed_by.value,
            reviewed_at=provenance.reviewed_at,
            relation=provenance.relation.value,
            related_memory_id=provenance.related_memory_id,
        )

    @staticmethod
    def _view(candidate) -> PassiveMemoryCandidateView:
        payload = PassiveCandidatePayload.model_validate(candidate.proposed_payload)
        record = payload.record
        summary = str(
            record.get("value")
            or record.get("decision")
            or record.get("text")
            or (
                record.get("content", {}).get("text")
                if isinstance(record.get("content"), dict)
                else record.get("content")
            )
            or "Кандидат памяти"
        )
        return PassiveMemoryCandidateView(
            candidate_id=candidate.id,
            candidate_type=candidate.candidate_type.value,
            summary=summary[:500],
            reason=payload.reason,
            confidence=candidate.confidence,
            detected_at=payload.detected_at,
            expires_at=payload.expires_at,
            relation=payload.relation.value,
            related_memory_id=payload.related_memory_id,
            requires_explicit_supersession=(
                payload.relation is ExistingMemoryRelation.POSSIBLE_UPDATE
            ),
        )
