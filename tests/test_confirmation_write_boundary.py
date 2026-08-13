from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from backend.application import build_masha_application
from backend.conversation.conversation_models import ConversationMessageOrigin
from backend.conversation.memory_intent import (
    MemoryIntentHandler,
    MemoryProposalStore,
    ProposalStatus,
)
from backend.llm.model_router import ModelRouter
from backend.memory.confirmed_memory_service import ConfirmedMemoryService
from backend.memory.memory_management import MemoryManagementService, MemoryMutationOperation
from backend.memory.memory_models import MemoryDocument
from backend.memory.shared_continuity import SharedContinuityService
from backend.memory.sqlite_repository import MemorySqliteRepository
from backend.temporal.temporal_engine import FixedClock, TemporalEngine
from backend.temporal.temporal_runtime import TemporalRuntime
from tests.test_application_boundary import LocalProfileProvider, _isolated_root


PROJECT_ID = "project_masha_home"
NOW = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)


class _FailOnceRepository:
    def __init__(self, repository: MemorySqliteRepository):
        self.repository = repository
        self.fail_next_replace = True

    def read_document(self):
        return self.repository.read_document()

    def replace_document(self, document, *, action="replace_document", audit_payload=None):
        if self.fail_next_replace:
            self.fail_next_replace = False
            raise OSError("injected repository failure")
        return self.repository.replace_document(
            document,
            action=action,
            audit_payload=audit_payload,
        )

    def list_audit_events(self):
        return self.repository.list_audit_events()


class _FailConfirmedStatusTwiceStore(MemoryProposalStore):
    """Fail service status write and immediate reconciliation, then recover."""

    def __init__(self, file_path):
        super().__init__(file_path)
        self.remaining_failures = 2

    def set_status(self, proposal_id, status):
        if status is ProposalStatus.CONFIRMED and self.remaining_failures:
            self.remaining_failures -= 1
            raise OSError("injected proposal status failure")
        return super().set_status(proposal_id, status)


def _handler(repository, proposals):
    management = MemoryManagementService(repository)
    return MemoryIntentHandler(
        proposal_store=proposals,
        confirmed_memory=ConfirmedMemoryService(repository),
        memory_management=management,
        shared_continuity=SharedContinuityService(repository),
    )


def _add_temporal_reference(repository: MemorySqliteRepository) -> str:
    document = repository.read_document()
    assert document is not None
    source = next(item for item in document.commitments if item.status.value == "open")
    due_at = NOW - timedelta(minutes=1)
    changed = source.model_copy(update={"due_at": due_at})
    commitments = [changed if item.id == source.id else item for item in document.commitments]
    repository.replace_document(document.model_copy(update={"commitments": commitments}))
    context = TemporalRuntime(
        repository,
        TemporalEngine(FixedClock(NOW)),
    ).recover()
    assert any(event.source_commitment_id == source.id for event in context.events)
    return source.id


def _episode_proposal(handler: MemoryIntentHandler, conversation_id: str = "c"):
    result = handler.handle(
        "Маша, запомни наш разговор про звёзды",
        conversation_id=conversation_id,
        project_id=PROJECT_ID,
    )
    proposal = handler.proposal_store.current_for_conversation(conversation_id)
    assert result.handled is True
    assert proposal is not None and proposal.record_type == "episode"
    return proposal


def test_episode_confirmation_survives_real_temporal_foreign_key_and_is_idempotent(
    tmp_path,
    canonical_memory,
):
    repository = MemorySqliteRepository(tmp_path / "memory.sqlite3")
    repository.replace_document(canonical_memory)
    source_id = _add_temporal_reference(repository)
    proposals = MemoryProposalStore(tmp_path / "proposals.json")
    handler = _handler(repository, proposals)
    proposal = _episode_proposal(handler)

    first = handler.handle("Подтверждаю.", conversation_id="c", project_id=PROJECT_ID)
    second = handler.handle(f"да {proposal.id}", conversation_id="c", project_id=PROJECT_ID)

    document = repository.read_document()
    assert first.response == "Готово, сохранила."
    assert second.response == "Эта запись уже сохранена."
    assert sum(item.id == proposal.record_payload["id"] for item in document.episodes) == 1
    assert proposals.get(proposal.id).status is ProposalStatus.CONFIRMED
    with repository._connection() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM temporal_events WHERE source_id = ?",
            (source_id,),
        ).fetchone()[0] == 1


def test_deferred_foreign_key_still_rejects_removing_a_temporal_source(
    tmp_path,
    canonical_memory,
):
    repository = MemorySqliteRepository(tmp_path / "memory.sqlite3")
    repository.replace_document(canonical_memory)
    source_id = _add_temporal_reference(repository)
    before = repository.read_document()
    payload = before.model_dump(mode="json")
    payload["commitments"] = [
        item for item in payload["commitments"] if item["id"] != source_id
    ]
    for episode in payload["episodes"]:
        episode["produced"]["commitments"] = [
            item for item in episode["produced"]["commitments"] if item != source_id
        ]
        episode["updated"]["commitments"] = [
            item for item in episode["updated"]["commitments"] if item != source_id
        ]
    invalid = MemoryDocument.model_validate(payload)

    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        repository.replace_document(invalid)

    restored = repository.read_document()
    assert any(item.id == source_id for item in restored.commitments)
    with repository._connection() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM temporal_events WHERE source_id = ?",
            (source_id,),
        ).fetchone()[0] == 1


def test_forget_confirmation_hides_once_retains_history_and_audit(
    tmp_path,
    canonical_memory,
):
    repository = MemorySqliteRepository(tmp_path / "memory.sqlite3")
    repository.replace_document(canonical_memory)
    _add_temporal_reference(repository)
    proposals = MemoryProposalStore(tmp_path / "proposals.json")
    handler = _handler(repository, proposals)
    management = handler.memory_management
    target_id = "fact_001"
    proposal = management.propose(
        proposals,
        operation=MemoryMutationOperation.FORGET,
        record_id=target_id,
        conversation_id="c",
    )

    first = handler.handle("Подтверждаю", conversation_id="c", project_id=PROJECT_ID)
    second = handler.handle(f"да {proposal.id}", conversation_id="c", project_id=PROJECT_ID)
    historical = management.get(target_id)
    matching_audit = [
        event
        for event in repository.list_audit_events()
        if event["action"] == "memory_forget"
        and event["payload"].get("proposal_id") == proposal.id
    ]

    assert first.response == "Готово. Эта запись больше не используется как активная память."
    assert second.response == "Эта запись уже сохранена."
    assert historical is not None and historical.payload["visibility"] == "hidden"
    assert len(matching_audit) == 1
    assert proposals.get(proposal.id).status is ProposalStatus.CONFIRMED


def test_repository_failure_before_write_stays_pending_and_retry_succeeds(
    tmp_path,
    canonical_memory,
):
    durable = MemorySqliteRepository(tmp_path / "memory.sqlite3")
    durable.replace_document(canonical_memory)
    repository = _FailOnceRepository(durable)
    proposals = MemoryProposalStore(tmp_path / "proposals.json")
    handler = _handler(repository, proposals)
    proposal = _episode_proposal(handler)

    failed = handler.handle("Подтверждаю", conversation_id="c", project_id=PROJECT_ID)
    assert "Не смогла сохранить" in failed.response
    assert proposals.get(proposal.id).status is ProposalStatus.PENDING
    assert all(item.id != proposal.record_payload["id"] for item in durable.read_document().episodes)

    retried = handler.handle("Подтверждаю", conversation_id="c", project_id=PROJECT_ID)
    assert retried.response == "Готово, сохранила."
    assert proposals.get(proposal.id).status is ProposalStatus.CONFIRMED
    assert sum(
        item.id == proposal.record_payload["id"]
        for item in durable.read_document().episodes
    ) == 1
    diagnostic = json.loads(
        (tmp_path / "confirmation-failures.json").read_text(encoding="utf-8")
    )["failures"][-1]
    assert diagnostic["exception_type"] == "OSError"
    assert diagnostic["stage"] == "repository_write"


def test_memory_write_then_proposal_status_failure_reconciles_without_duplicate(
    tmp_path,
    canonical_memory,
):
    repository = MemorySqliteRepository(tmp_path / "memory.sqlite3")
    repository.replace_document(canonical_memory)
    proposals = _FailConfirmedStatusTwiceStore(tmp_path / "proposals.json")
    handler = _handler(repository, proposals)
    proposal = _episode_proposal(handler)

    partial = handler.handle("Подтверждаю", conversation_id="c", project_id=PROJECT_ID)
    assert "уже применено один раз" in partial.response
    assert proposals.get(proposal.id).status is ProposalStatus.PENDING
    assert sum(
        item.id == proposal.record_payload["id"]
        for item in repository.read_document().episodes
    ) == 1

    reconciled = handler.handle("Подтверждаю", conversation_id="c", project_id=PROJECT_ID)
    assert reconciled.response == "Готово, сохранила."
    assert proposals.get(proposal.id).status is ProposalStatus.CONFIRMED
    assert sum(
        item.id == proposal.record_payload["id"]
        for item in repository.read_document().episodes
    ) == 1
    assert len([
        event
        for event in repository.list_audit_events()
        if event["action"] == "confirmed_memory"
        and event["payload"].get("proposal_id") == proposal.id
    ]) == 1
    diagnostic = json.loads(
        (tmp_path / "confirmation-failures.json").read_text(encoding="utf-8")
    )["failures"][-1]
    assert diagnostic["stage"] == "proposal_status"


def test_malformed_episode_proposal_never_mutates_or_reports_success(
    tmp_path,
    canonical_memory,
):
    repository = MemorySqliteRepository(tmp_path / "memory.sqlite3")
    repository.replace_document(canonical_memory)
    proposals = MemoryProposalStore(tmp_path / "proposals.json")
    handler = _handler(repository, proposals)
    proposal = _episode_proposal(handler)
    malformed = proposal.model_copy(
        update={"record_payload": {**proposal.record_payload, "source": "model_inference"}}
    )
    proposals._proposals[proposal.id] = malformed
    proposals._save()

    result = handler.handle("Подтверждаю", conversation_id="c", project_id=PROJECT_ID)

    assert "Не смогла сохранить" in result.response
    assert proposals.get(proposal.id).status is ProposalStatus.PENDING
    assert all(item.id != proposal.record_payload["id"] for item in repository.read_document().episodes)
    diagnostic = json.loads(
        (tmp_path / "confirmation-failures.json").read_text(encoding="utf-8")
    )["failures"][-1]
    assert diagnostic["exception_type"] == "ValidationError"
    assert diagnostic["stage"] == "proposal_validation"


def test_application_episode_confirmation_is_truthful_with_temporal_rows(tmp_path):
    root = _isolated_root(tmp_path)
    repository = MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    _add_temporal_reference(repository)
    application = build_masha_application(
        project_root=root,
        router=ModelRouter([LocalProfileProvider()]),
    )
    conversation = application.send_message(
        "Поговорим о Бетельгейзе и наблюдении Луны?",
        project_id=PROJECT_ID,
    )
    proposed = application.send_message(
        "Маша, запомни наш разговор про звёзды",
        conversation_id=conversation.conversation_id,
        project_id=PROJECT_ID,
    )
    pending = proposed.pending_confirmation
    assert pending is not None
    proposal = application._conversation._conversation.memory_intent_handler.proposal_store.get(
        pending.proposal_id
    )

    resolved = application.resolve_confirmation(
        conversation_id=proposed.conversation_id,
        proposal_id=pending.proposal_id,
        decision="confirm",
        project_id=PROJECT_ID,
    )
    stored = MemorySqliteRepository(
        root / "local-data" / "memory" / "masha.sqlite3"
    ).read_document()
    assistant = application._conversation._conversation.history.messages(
        proposed.conversation_id
    )[-1]

    assert resolved.status.value == "confirmed"
    assert resolved.assistant_message.content == "Готово, сохранила."
    assert assistant.origin is ConversationMessageOrigin.APPLICATION
    assert sum(item.id == proposal.record_payload["id"] for item in stored.episodes) == 1
    assert proposal.record_type == "episode"


def test_application_forget_confirmation_hides_existing_record_with_temporal_rows(tmp_path):
    root = _isolated_root(tmp_path)
    repository = MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    _add_temporal_reference(repository)
    application = build_masha_application(
        project_root=root,
        router=ModelRouter([LocalProfileProvider()]),
    )
    created = application.send_message(
        "Запомни, что контрольная запись подтверждения — янтарный маяк",
        project_id=PROJECT_ID,
    )
    application.resolve_confirmation(
        conversation_id=created.conversation_id,
        proposal_id=created.pending_confirmation.proposal_id,
        decision="confirm",
        project_id=PROJECT_ID,
    )
    proposed = application.send_message(
        "Маша, забудь про янтарный маяк",
        conversation_id=created.conversation_id,
        project_id=PROJECT_ID,
    )
    pending = proposed.pending_confirmation
    assert pending is not None and pending.confirmation_type == "memory_forget"
    proposal = application._conversation._conversation.memory_intent_handler.proposal_store.get(
        pending.proposal_id
    )

    resolved = application.resolve_confirmation(
        conversation_id=proposed.conversation_id,
        proposal_id=pending.proposal_id,
        decision="confirm",
        project_id=PROJECT_ID,
    )
    management = MemoryManagementService(
        MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    )
    historical = management.get(proposal.target_record_id)
    assistant = application._conversation._conversation.history.messages(
        proposed.conversation_id
    )[-1]

    assert resolved.status.value == "confirmed"
    assert resolved.assistant_message.content == (
        "Готово. Эта запись больше не используется как активная память."
    )
    assert assistant.origin is ConversationMessageOrigin.APPLICATION
    assert historical is not None and historical.payload["visibility"] == "hidden"
    assert any(
        event["action"] == "memory_forget"
        and event["payload"].get("proposal_id") == proposal.id
        for event in historical.audit_events
    )
