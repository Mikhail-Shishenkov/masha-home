"""Explicit user-confirmed writes to long-term memory; never used by chat automatically."""

from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from .memory_models import (
    Commitment,
    Decision,
    Episode,
    Fact,
    IdentityCode,
    MemoryDocument,
    RelationshipMemory,
    SourceType,
    StrictMemoryModel,
)
from .memory_repository import MemoryDocumentRepository


ConfirmedRecord = Fact | Decision | Commitment | Episode | RelationshipMemory
ConfirmedRecordType = Literal[
    "fact",
    "decision",
    "commitment",
    "episode",
    "relationship_memory",
]


_COLLECTION_BY_RECORD_TYPE = {
    "fact": "facts",
    "decision": "decisions",
    "commitment": "commitments",
    "episode": "episodes",
    "relationship_memory": "relationship_memories",
}


class ExplicitMemoryConfirmation(StrictMemoryModel):
    """A write request that must be created by an explicit user interaction."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True, frozen=True)

    confirmed_by: Literal[IdentityCode.MISHA]
    record: ConfirmedRecord
    proposal_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def require_explicit_user_source(self):
        if self.record.source != SourceType.EXPLICIT_USER_INPUT:
            raise ValueError("confirmed memory must use explicit_user_input source")
        return self


class ConfirmedMemoryService:
    """Writes a prepared record once after explicit confirmation, with no inference."""

    def __init__(self, repository: MemoryDocumentRepository):
        self.repository = repository

    def confirm(self, confirmation: ExplicitMemoryConfirmation) -> ConfirmedRecord:
        document = self.repository.read_document()
        if document is None:
            raise ValueError("cannot confirm memory in an empty store")
        record_type = self._record_type(confirmation.record)
        if self._contains_id(document, confirmation.record.id):
            raise ValueError(f"memory id already exists: {confirmation.record.id}")

        payload = document.model_dump(mode="json")
        payload[_COLLECTION_BY_RECORD_TYPE[record_type]].append(
            confirmation.record.model_dump(mode="json")
        )
        self.repository.replace_document(
            MemoryDocument.model_validate(payload),
            action="confirmed_memory",
            audit_payload={
                "who": confirmation.confirmed_by.value,
                "what": record_type,
                "when": confirmation.record.created_at.isoformat(),
                "operation": "confirmed_memory",
                "record_id": confirmation.record.id,
                **(
                    {"proposal_id": confirmation.proposal_id}
                    if confirmation.proposal_id is not None
                    else {}
                ),
            },
        )
        return confirmation.record

    def confirmation_postcondition(
        self,
        confirmation: ExplicitMemoryConfirmation,
    ) -> bool:
        """Verify the exact proposed record, plus its audit when available."""
        document = self.repository.read_document()
        if document is None:
            return False
        record_type = self._record_type(confirmation.record)
        collection = getattr(document, _COLLECTION_BY_RECORD_TYPE[record_type])
        matches = [item for item in collection if item.id == confirmation.record.id]
        if len(matches) != 1 or matches[0] != confirmation.record:
            return False
        if confirmation.proposal_id is None or not hasattr(self.repository, "list_audit_events"):
            return True
        return any(
            event.get("action") == "confirmed_memory"
            and event.get("payload", {}).get("proposal_id") == confirmation.proposal_id
            and event.get("payload", {}).get("record_id") == confirmation.record.id
            for event in self.repository.list_audit_events()
        )

    @staticmethod
    def _record_type(record: ConfirmedRecord) -> ConfirmedRecordType:
        if isinstance(record, Fact):
            return "fact"
        if isinstance(record, Decision):
            return "decision"
        if isinstance(record, Commitment):
            return "commitment"
        if isinstance(record, Episode):
            return "episode"
        return "relationship_memory"

    @staticmethod
    def _contains_id(document: MemoryDocument, memory_id: str) -> bool:
        return any(
            record.id == memory_id
            for collection in (
                document.projects,
                document.facts,
                document.decisions,
                document.commitments,
                document.episodes,
                document.memory_candidates,
                document.reflections,
                document.relationship_memories,
                document.affective_records,
                document.continuity_states,
            )
            for record in collection
        )
