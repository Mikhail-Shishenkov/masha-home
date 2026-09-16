"""Proposal revision preserves confirmation and real provider identity."""

import json
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import Mock

import pytest

from backend.conversation.clarification import FollowUpResolutionEngine, DeterministicClarificationBuilder
from backend.conversation.memory_intent import MemoryProposalStore
from backend.conversation.pending_resolution import PendingResolutionStore
from backend.conversation.resolution_coordinator import DialogueCore
from backend.temporal.temporal_engine import TemporalEngine, FixedClock
from tests.test_human_reference_resolution import _service as conversation_service, PROJECT
from tests.test_semantic_resolver import _boundaries
from tests.test_google_calendar_create import _service as create_service
from tests.test_google_calendar_update import _service as update_service


@pytest.mark.parametrize("kind", ["create", "update"])
@pytest.mark.parametrize("verified", [True, False])
def test_only_verified_calendar_result_becomes_shared_conversation_object(tmp_path, kind, verified, monkeypatch):
    from backend.connectors.presented_read_sets import PresentedReadSetRegistry
    from backend.connectors.google_calendar.service import GoogleCalendarConversationService
    from backend.connectors.google_calendar.reader import CalendarReadOutcome

    registry = PresentedReadSetRegistry()
    now = datetime(2026, 8, 25, 12, tzinfo=ZoneInfo("Europe/Saratov"))
    if kind == "create":
        owner, transport, writer = create_service(tmp_path)
        command = "Поставь встречу завтра в 19:00 на час"
        method = "create_and_verify"
    else:
        owner, writer, transport, _ = update_service(tmp_path)
        command = "Перенеси занятие по AI завтра на 13:00"
        method = "update_and_verify"
    owner.presented_read_sets = registry
    owner.propose(command, conversation_id="current", now_local=now)
    proposal = owner.proposal_store.current_for_conversation("current")
    assert registry.current_context("current") is None  # Target/proposal is not execution.
    if not verified:
        if kind == "update":
            # An indeterminate edit invalidates even a previously shown event.
            registry.present("current", "google_calendar", ("previously shown event",))
        receipt = writer.receipt_store.get(proposal.record_payload["operation_id"])
        uncertain = "created_unverified" if kind == "create" else "updated_unverified"
        monkeypatch.setattr(writer, method, Mock(return_value=(uncertain, receipt.model_copy(update={"status": uncertain}))))
    owner.resolve("да", conversation_id="current")
    context = registry.current_context("current")
    if not verified:
        assert context is None
        return
    receipt = writer.receipt_store.get(proposal.record_payload["operation_id"])
    assert receipt.status == "verified" and receipt.verified_at is not None
    assert context.owner == "google_calendar" and context.focused_position == 1
    event = context.items[0]
    expected = receipt.operation if kind == "create" else receipt.operation.desired
    assert (event.title, event.start, event.end) == (expected.title, expected.start, expected.end)
    hints = registry.model_safe_hints("current")
    assert hints[0]["owner_operation_id"] == "google_calendar.read"
    assert hints[0]["focused"] is True
    assert event.event_id not in str(hints)
    assert registry.model_safe_hints("another-conversation") == ()
    calls = len(transport.calls)
    assert owner.resolve("да", conversation_id="current") is None
    assert len(transport.calls) == calls
    # A subsequent empty read replaces the old action focus, rather than
    # presenting yesterday's verified result as the current query's answer.
    reader = Mock()
    reader.read.return_value = CalendarReadOutcome(status="completed")
    read_service = GoogleCalendarConversationService(reader=reader, presented_read_sets=registry)
    read_service.observe_period("завтра", now_local=now, conversation_id="current")
    assert registry.model_safe_hints("current") == ()


@pytest.mark.parametrize("kind", ["create", "update"])
@pytest.mark.parametrize("case", ["correct", "uncertain", "receipt_failure", "preview_failure", "retire_failure", "stale_event"])
def test_calendar_draft_revision_keeps_confirmation_and_receipt_truth(tmp_path, memory_path, monkeypatch, kind, case):
    conversation, _, ordinary = conversation_service(tmp_path, memory_path)
    now = datetime(2026, 8, 25, 12, tzinfo=ZoneInfo("Europe/Saratov"))
    temporal = TemporalEngine(clock=FixedClock(now))
    conversation.temporal_engine = temporal
    cid = conversation.history.create().id
    if kind == "create":
        owner, transport, writer = create_service(tmp_path / "calendar")
        owner.propose("Поставь встречу завтра в 19:00 на час", conversation_id=cid, now_local=now)
        conversation.google_calendar_create_service = owner
        execute = writer.create_and_verify
    else:
        owner, writer, transport, _ = update_service(tmp_path / "calendar")
        owner.propose("Перенеси занятие по AI завтра на 13:00", conversation_id=cid, now_local=now)
        conversation.google_calendar_update_service = owner
        execute = writer.update_and_verify
    conversation.memory_intent_handler.proposal_store = owner.proposal_store
    old = owner.proposal_store.current_for_conversation(cid)
    assert old is not None
    old_receipt = writer.receipt_store.get(old.record_payload["operation_id"])
    provider, resolver, validator, hybrid, _ = _boundaries(tmp_path / "semantic")
    provider.response_text = json.dumps({
        "relation": "follow_up", "selected_operation_id": None,
        "operation_selection_evidence": None, "referent_updates": [],
        "slot_updates": [{"name": "time", "mode": "correct", "evidence_text": "10 утра"}],
    })
    conversation.dialogue_core = DialogueCore(
        discovery=hybrid, builder=DeterministicClarificationBuilder(catalog=validator.catalog),
        engine=FollowUpResolutionEngine(semantic_resolver=resolver, semantic_validator=validator),
        store=PendingResolutionStore(tmp_path / "dialogue.json"),
    )
    if case == "uncertain":
        writer.receipt_store.put(old_receipt.model_copy(update={"status": "executing", "confirmed_at": now}))
    if case == "receipt_failure":
        monkeypatch.setattr(writer.receipt_store, "put", Mock(side_effect=OSError("disk full")))
    if case == "preview_failure":
        monkeypatch.setattr(owner.proposal_store, "_save", Mock(side_effect=OSError("disk full")))
    if case == "retire_failure":
        monkeypatch.setattr(writer, "reject", Mock(side_effect=OSError("disk full")))
    calls_before = len(transport.calls)
    _, response = conversation.send("Нет, лучше в 10 утра", conversation_id=cid, project_id=PROJECT)
    assert len(transport.calls) == calls_before  # No OAuth, lookup, create or PATCH.
    assert ordinary.requests == []
    assert not any(word in response.lower() for word in ("готово", "сделано", "перенесла"))
    assert conversation.dialogue_core.store.active_for_conversation(cid) is None
    current = owner.proposal_store.current_for_conversation(cid)
    assert current.status.value == "pending"
    if case in {"uncertain", "receipt_failure", "preview_failure"}:
        assert current == old
        assert MemoryProposalStore(owner.proposal_store.file_path).current_for_conversation(cid) == old
        if case == "uncertain":
            assert not provider.requests
        return
    revised = writer.receipt_store.get(current.record_payload["operation_id"])
    assert revised.status == "proposed" and revised.confirmed_at is None
    assert current.id != old.id and revised.operation.operation_id != old_receipt.operation.operation_id
    assert "10:00" in response and "Подтверждаешь?" in response
    if kind == "update":
        assert revised.operation.provider_event_id == old_receipt.operation.provider_event_id
        assert revised.operation.before == old_receipt.operation.before
        assert revised.operation.etag == old_receipt.operation.etag
        assert revised.operation.desired.title == old_receipt.operation.desired.title
    prompt = provider.last_request.model_dump_json()
    assert old.id not in prompt and old_receipt.operation.operation_id not in prompt
    if kind == "update":
        assert old_receipt.operation.provider_event_id not in prompt and old_receipt.operation.etag not in prompt
    # Reopen both durable stores; no in-memory hidden revision state is needed.
    owner.proposal_store = MemoryProposalStore(owner.proposal_store.file_path)
    conversation.memory_intent_handler.proposal_store = owner.proposal_store
    writer.receipt_store = type(writer.receipt_store)(writer.receipt_store.path)
    conversation.resolve_proposal_confirmation(conversation_id=cid, proposal_id=old.id, confirm=True, project_id=PROJECT)
    assert len(transport.calls) == calls_before
    if case == "stale_event" and kind == "update":
        transport.events[revised.operation.provider_event_id]["etag"] = '"changed"'
        transport.events[revised.operation.provider_event_id]["summary"] = "Другое событие"
    _, response = conversation.send("Да", conversation_id=cid, project_id=PROJECT)
    mutation_calls = [c for c in transport.calls[calls_before:] if c[1] in {"POST", "PATCH"} and "oauth2" not in c[0]]
    if case == "stale_event" and kind == "update":
        assert not mutation_calls and "изменилось" in response
        return
    assert len(mutation_calls) == 1
    assert writer.receipt_store.get(revised.operation.operation_id).status == "verified"
    assert "Готово" in response
    count = len(transport.calls)
    assert execute(revised.operation)[0] == "verified"
    assert len(transport.calls) == count
    if case != "retire_failure":
        assert execute(old_receipt.operation)[0] == "rejected"
        assert len(transport.calls) == count


def test_update_revision_cannot_retarget_and_keeps_desired_date(tmp_path):
    from backend.connectors.google_calendar.draft_revision import calendar_draft, replace_calendar_draft

    owner, writer, transport, _ = update_service(tmp_path)
    now = datetime(2026, 8, 25, 12, tzinfo=ZoneInfo("Europe/Saratov"))
    owner.propose("Перенеси занятие по AI завтра на 13:00", conversation_id="fixture", now_local=now)
    old = owner.proposal_store.current_for_conversation("fixture")
    _, receipt, values = calendar_draft(owner, old)
    count = len(transport.calls)
    with pytest.raises(ValueError, match="bound target"):
        replace_calendar_draft(owner, old, {**values, "subject": "другая встреча"}, now_local=now)
    assert owner.proposal_store.current_for_conversation("fixture") == old
    assert writer.receipt_store.get(receipt.operation.operation_id) == receipt
    response = replace_calendar_draft(owner, old, {**values, "date": "2026-08-27", "duration_minutes": "30"}, now_local=now)
    current = owner.proposal_store.current_for_conversation("fixture")
    revised = writer.receipt_store.get(current.record_payload["operation_id"]).operation
    assert revised.before == receipt.operation.before and revised.provider_event_id == receipt.operation.provider_event_id
    assert revised.desired.start.isoformat() == "2026-08-27T13:00:00+04:00"
    assert revised.desired.end.isoformat() == "2026-08-27T13:30:00+04:00"
    assert "27.08.2026" in response
    assert len(transport.calls) == count
