"""Explicit, inspectable long-term-memory operations for the active repository."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .memory_models import Decision, DecisionStatus, Fact, FactStatus, MemoryDocument, Visibility


ManagedRecordType = Literal["fact", "decision", "commitment", "episode"]
RetrievalRecordType = Literal[
    "fact",
    "decision",
    "commitment",
    "episode",
    "relationship_memory",
    "continuity_state",
]


class MemoryMutationOperation(str, Enum):
    EDIT = "edit"
    ARCHIVE = "archive"
    FORGET = "forget"
    SUPERSEDE = "supersede"


class MemoryRecordView(BaseModel):
    """A local inspection view; payload remains the validated stored payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: str
    record_type: ManagedRecordType
    project_ids: tuple[str, ...]
    payload: dict[str, Any]
    status: str | None
    source: str | None
    confidence: float | None
    identity_version: str
    created_at: str | None
    updated_at: str | None
    supersedes_id: str | None
    superseded_by: str | None
    audit_events: tuple[dict[str, Any], ...]


class MemoryRetrievalTrace(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: str
    record_type: RetrievalRecordType
    relevance_score: float
    reasons: tuple[str, ...]
    source: str | None
    active_status: str | None


class MemoryManagementService:
    """Uses whole-document validated transactions; it never infers a mutation."""

    def __init__(self, repository):
        self.repository = repository

    def list(self, *, record_type: ManagedRecordType | None = None, project_id: str | None = None,
             query: str | None = None, include_hidden: bool = True) -> list[MemoryRecordView]:
        document = self._document()
        return [
            self._view(document, item_type, item)
            for item_type, item in self._records(document, record_type)
            if (project_id is None or project_id in item.get("project_ids", []))
            and (include_hidden or item.get("visibility", "visible") == "visible")
            and self._matches_query(item, query)
        ]

    def get(self, record_id: str) -> MemoryRecordView | None:
        document = self._document()
        for item_type, item in self._records(document):
            if item["id"] == record_id:
                return self._view(document, item_type, item)
        return None

    def conflicts(self, *, project_id: str | None = None) -> list[tuple[MemoryRecordView, ...]]:
        """Show active visible Fact conflicts; never select a winner."""
        groups: dict[tuple[str, str, tuple[str, ...]], list[dict[str, Any]]] = {}
        document = self._document()
        for fact in document.model_dump(mode="json")["facts"]:
            if fact["status"] != "active" or fact["visibility"] != "visible":
                continue
            if project_id is not None and project_id not in fact["project_ids"]:
                continue
            key = (fact["subject"], fact["key"], tuple(sorted(fact["project_ids"])))
            groups.setdefault(key, []).append(fact)
        return [
            tuple(self._view(document, "fact", item) for item in items)
            for items in groups.values()
            if len({json.dumps(item["value"], sort_keys=True, ensure_ascii=False) for item in items}) > 1
        ]

    def apply(self, *, operation: MemoryMutationOperation, record_id: str,
              replacement_payload: dict[str, Any] | None = None, proposal_id: str) -> MemoryRecordView:
        """Apply an already explicitly approved proposal atomically, or raise."""
        document = self._document()
        payload = document.model_dump(mode="json")
        record_type, index = self._find(payload, record_id)
        old = dict(payload[f"{record_type}s"][index])
        old_state = dict(old)
        now = datetime.now(timezone.utc).isoformat()

        if operation in (MemoryMutationOperation.ARCHIVE, MemoryMutationOperation.FORGET):
            new = {**old, "visibility": "hidden"}
            if "updated_at" in new:
                new["updated_at"] = now
            payload[f"{record_type}s"][index] = new
        elif operation == MemoryMutationOperation.EDIT:
            if replacement_payload is None:
                raise ValueError("edit requires replacement_payload")
            new = dict(replacement_payload)
            if new.get("id") != record_id:
                raise ValueError("edit must retain the existing record id")
            if "updated_at" in new:
                new["updated_at"] = now
            payload[f"{record_type}s"][index] = new
        elif operation == MemoryMutationOperation.SUPERSEDE:
            if record_type not in ("fact", "decision") or replacement_payload is None:
                raise ValueError("supersession requires a replacement Fact or Decision")
            replacement = dict(replacement_payload)
            if replacement.get("id") == record_id:
                raise ValueError("replacement must have a new record id")
            if replacement.get("supersedes_id") != record_id:
                raise ValueError("replacement must explicitly supersede the old record")
            if record_type == "fact":
                old.update(status=FactStatus.SUPERSEDED.value, superseded_by=replacement["id"], updated_at=now)
            else:
                old.update(status=DecisionStatus.SUPERSEDED.value, superseded_by=replacement["id"], updated_at=now)
            payload[f"{record_type}s"][index] = old
            payload[f"{record_type}s"].append(replacement)
            new = replacement
        else:  # pragma: no cover - enum guards this branch
            raise ValueError(f"unsupported operation: {operation}")

        validated = MemoryDocument.model_validate(payload)
        self.repository.replace_document(
            validated,
            action=f"memory_{operation.value}",
            audit_payload={
                "who": "misha", "operation": operation.value, "record_id": record_id,
                "proposal_id": proposal_id, "old_state": old_state, "new_state": new,
            },
        )
        view = self.get(new["id"])
        assert view is not None
        return view

    def propose(
        self,
        proposal_store,
        *,
        operation: MemoryMutationOperation,
        record_id: str,
        conversation_id: str,
        replacement_payload: dict[str, Any] | None = None,
    ):
        """Persist a pending proposal using the established proposal store."""
        from uuid import uuid4
        from backend.conversation.memory_intent import MemoryProposal, ProposalStatus

        view = self.get(record_id)
        if view is None:
            raise KeyError(f"memory record not found: {record_id}")
        if operation == MemoryMutationOperation.SUPERSEDE and replacement_payload is None:
            raise ValueError("supersession requires a replacement payload")
        return proposal_store.create(MemoryProposal(
            id=str(uuid4()), conversation_id=conversation_id, record_type=view.record_type,
            record_payload=replacement_payload or view.payload,
            created_at=datetime.now(timezone.utc), status=ProposalStatus.PENDING,
            operation=operation.value, target_record_id=record_id,
        ))

    def confirm_proposal(self, proposal, proposal_store) -> MemoryRecordView:
        """Mutation confirmation entry point; caller must verify pending user approval."""
        if proposal.status.value != "pending" or proposal.operation == "create" or not proposal.target_record_id:
            raise ValueError("proposal is not a pending memory mutation")
        view = self.apply(
            operation=MemoryMutationOperation(proposal.operation),
            record_id=proposal.target_record_id,
            replacement_payload=proposal.record_payload,
            proposal_id=proposal.id,
        )
        from backend.conversation.memory_intent import ProposalStatus
        proposal_store.set_status(proposal.id, ProposalStatus.CONFIRMED)
        return view

    def trace(self, retrieved: list[dict[str, Any]]) -> tuple[MemoryRetrievalTrace, ...]:
        return tuple(
            MemoryRetrievalTrace(
                record_id=item["data"]["id"], record_type=item["type"],
                relevance_score=item["score"], reasons=tuple(item.get("reasons", ())),
                source=item["data"].get("source"), active_status=item["data"].get("status"),
            ) for item in retrieved
        )

    def _document(self) -> MemoryDocument:
        document = self.repository.read_document()
        if document is None:
            raise ValueError("memory store is empty")
        return document

    @staticmethod
    def _records(document: MemoryDocument, only: ManagedRecordType | None = None):
        data = document.model_dump(mode="json")
        for record_type in ("fact", "decision", "commitment", "episode"):
            if only is None or only == record_type:
                yield from ((record_type, item) for item in data[f"{record_type}s"])

    def _view(self, document: MemoryDocument, record_type: ManagedRecordType, item: dict[str, Any]) -> MemoryRecordView:
        return MemoryRecordView(record_id=item["id"], record_type=record_type,
            project_ids=tuple(item.get("project_ids", [])), payload=item,
            status=item.get("status"), source=item.get("source"), confidence=item.get("confidence"),
            identity_version=document.identity_version, created_at=item.get("created_at"),
            updated_at=item.get("updated_at"), supersedes_id=item.get("supersedes_id") or item.get("replaces_id"),
            superseded_by=item.get("superseded_by"), audit_events=tuple(self._audit(item["id"])))

    def _audit(self, record_id: str) -> list[dict[str, Any]]:
        return [event for event in self.repository.list_audit_events()
                if event["entity_id"] == record_id or event["payload"].get("record_id") == record_id]

    @staticmethod
    def _matches_query(item: dict[str, Any], query: str | None) -> bool:
        return query is None or query.casefold() in json.dumps(item, ensure_ascii=False, sort_keys=True).casefold()

    @staticmethod
    def _find(payload: dict[str, Any], record_id: str) -> tuple[ManagedRecordType, int]:
        for record_type in ("fact", "decision", "commitment", "episode"):
            for index, item in enumerate(payload[f"{record_type}s"]):
                if item["id"] == record_id:
                    return record_type, index
        raise KeyError(f"memory record not found: {record_id}")
