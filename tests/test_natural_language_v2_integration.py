from __future__ import annotations

import shutil
import json
from datetime import datetime, timezone
from pathlib import Path

from backend.application import ConversationTurnStatus, build_masha_application
from backend.llm.fake_provider import FakeProvider
from backend.llm.model_router import ModelRouter
from backend.llm.model_models import ModelCapabilities
from backend.memory.sqlite_repository import MemorySqliteRepository
from backend.temporal.temporal_engine import FixedClock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ID = "project_masha_home"
FIXED_NOW = datetime(2026, 8, 28, 8, 0, tzinfo=timezone.utc)


class LocalProvider(FakeProvider):
    def __init__(self, response_text="Обычный разговор."):
        super().__init__(provider_id="ollama-local", response_text=response_text)
        self.available_models = {"qwen3.5:9b", "qwen3.5:4b"}

    def is_model_available(self, model_id: str) -> bool:
        return model_id in self.available_models


class SemanticThenConversationProvider(LocalProvider):
    def __init__(self, semantic_text: str, conversation_text: str):
        super().__init__()
        self.capabilities = ModelCapabilities(structured_output=True)
        self.semantic_text = semantic_text
        self.conversation_text = conversation_text

    def generate(self, request):
        self.response_text = (
            self.semantic_text
            if request.required_capabilities.structured_output
            else self.conversation_text
        )
        return super().generate(request)


def _root(tmp_path):
    root = tmp_path / "masha-home"
    shutil.copytree(PROJECT_ROOT / "identity", root / "identity")
    shutil.copytree(PROJECT_ROOT / "skills", root / "skills")
    repository = MemorySqliteRepository(
        root / "local-data" / "memory" / "masha.sqlite3"
    )
    repository.import_json(PROJECT_ROOT / "memory" / "test_memory.json")
    return root


def _application(tmp_path, *, root=None, provider=None):
    root = root or _root(tmp_path)
    provider = provider or LocalProvider()
    return root, provider, build_masha_application(
        project_root=root,
        router=ModelRouter([provider]),
    )


def test_live_wrapped_request_accumulates_into_calendar_proposal_without_slot_loss(
    tmp_path, monkeypatch,
):
    import socket

    provider = LocalProvider(json.dumps({
        "kind": "supported_action",
        "candidate_operation_ids": [
            "google_calendar.event.create",
            "home.timed_commitments",
        ],
        "nearby_operation_ids": [],
        "extracted_slots": [
            {"name": "subject", "evidence_text": "занятие"},
            {"name": "date", "evidence_text": "завтра"},
            {"name": "time", "evidence_text": "12"},
        ],
        "unresolved_referents": [],
        "ambiguity_hint": "capability",
        "operation_selection_evidence": None,
    }, ensure_ascii=False))
    provider.capabilities = ModelCapabilities(structured_output=True)
    _, _, application = _application(tmp_path, provider=provider)
    conversation = application._conversation._conversation
    conversation.temporal_engine.clock = FixedClock(FIXED_NOW)
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network")),
    )

    first = application.send_message(
        "Доброе утро, Маша! Запиши занятие завтра в 12",
        project_id=PROJECT_ID,
    )
    first_diagnostic = application.dialogue_diagnostics(first.conversation_id)
    model_calls_after_first = len(provider.requests)
    second = application.send_message(
        "Поставь в календарь",
        project_id=PROJECT_ID,
        conversation_id=first.conversation_id,
    )
    second_diagnostic = application.dialogue_diagnostics(first.conversation_id)
    third = application.send_message(
        "на час",
        project_id=PROJECT_ID,
        conversation_id=first.conversation_id,
    )

    assert first.assistant_message.content == (
        "Занятие — поставить в календарь или просто напомнить в 12:00?"
    )
    assert first_diagnostic.dialogue_state.last_decision.semantic_command_status == "accepted"
    assert first_diagnostic.dialogue_state.last_decision.proposed_semantic_command is not None
    assert second.pending_confirmation is None
    assert second.assistant_message.content == "На сколько времени поставить?"
    assert {
        slot.name: slot.value
        for slot in second_diagnostic.dialogue_state.flow_stack[0].validated_slots
    } == {
        "subject": "занятие",
        "date": "2026-08-29",
        "time": "12:00",
    }
    assert third.pending_confirmation is not None
    assert third.pending_confirmation.confirmation_type == "google_calendar_create"
    assert "занятие" in third.assistant_message.content.casefold()
    assert "12:00–13:00" in third.assistant_message.content
    assert len(provider.requests) == model_calls_after_first
    receipts = conversation.google_calendar_create_service.writer.receipt_store._items
    assert {item.status for item in receipts.values()} == {"proposed"}
    assert all(item.confirmed_at is None for item in receipts.values())


def test_unsupported_external_registration_gets_human_truthful_fallback(tmp_path):
    provider = SemanticThenConversationProvider(
        json.dumps({
            "kind": "unsupported_action",
            "candidate_operation_ids": [],
            "nearby_operation_ids": [
                "google_calendar.event.create",
                "home.timed_commitments"
            ],
            "extracted_slots": [],
            "unresolved_referents": [],
            "ambiguity_hint": "none",
            "operation_selection_evidence": None,
        }),
        "Я записала тебя на внешнее занятие.",
    )
    _, _, application = _application(tmp_path, provider=provider)

    turn = application.send_message(
        "Привет, моя хорошая! запиши меня на внешнее занятие завтра в 9",
        project_id=PROJECT_ID,
    )

    assert turn.pending_confirmation is None
    assert "пока не умею выполнять" in turn.assistant_message.content
    assert "календар" in turn.assistant_message.content.casefold()
    assert "напом" in turn.assistant_message.content.casefold()
    assert "записала тебя" not in turn.assistant_message.content.casefold()
    assert len(provider.requests) == 1


def test_calendar_choice_reaches_existing_preview_with_zero_provider_effects(tmp_path, monkeypatch):
    import socket

    root, model, application = _application(tmp_path)
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network")),
    )

    first = application.send_message(
        "Маша, запиши занятие завтра в 10 на час", project_id=PROJECT_ID
    )
    second = application.send_message(
        "В календарь",
        project_id=PROJECT_ID,
        conversation_id=first.conversation_id,
    )

    assert first.status is ConversationTurnStatus.COMPLETED
    assert first.assistant_message.content == (
        "Занятие — поставить в календарь или просто напомнить в 10:00?"
    )
    assert "Поставить «занятие»" in second.assistant_message.content
    assert "10:00–11:00" in second.assistant_message.content
    assert second.pending_confirmation is not None
    assert second.pending_confirmation.confirmation_type == "google_calendar_create"
    assert model.requests == []
    writer = application._conversation._conversation.google_calendar_create_service.writer
    assert {item.status for item in writer.receipt_store._items.values()} == {"proposed"}
    assert all(item.confirmed_at is None for item in writer.receipt_store._items.values())
    transcript = application.conversation(first.conversation_id).messages
    assert [item.content for item in transcript] == [
        "Маша, запиши занятие завтра в 10 на час",
        first.assistant_message.content,
        "В календарь",
        second.assistant_message.content,
    ]


def test_reminder_choice_uses_existing_confirmation_and_creates_nothing_yet(tmp_path):
    root, model, application = _application(tmp_path)
    commitments_before = application.commitments().items
    first = application.send_message(
        "Запиши проверку роутера завтра в 11", project_id=PROJECT_ID
    )

    second = application.send_message(
        "Просто напомни",
        project_id=PROJECT_ID,
        conversation_id=first.conversation_id,
    )

    assert second.pending_confirmation is not None
    assert second.pending_confirmation.confirmation_type == "commitment_create"
    assert second.pending_confirmation.subject == "проверку роутера"
    assert second.pending_confirmation.due_at is not None
    assert application.commitments().items == commitments_before
    assert model.requests == []
    assert application._conversation._conversation.google_calendar_create_service.writer.receipt_store._items == {}


def test_missing_subject_reaches_calendar_preview_without_losing_known_slots(tmp_path):
    provider = LocalProvider(json.dumps({
        "relation": "follow_up",
        "selected_operation_id": None,
        "slot_updates": [
            {"name": "subject", "evidence_text": "Занятие по AI", "mode": "add"},
        ],
    }, ensure_ascii=False))
    provider.capabilities = ModelCapabilities(structured_output=True)
    _, _, application = _application(tmp_path, provider=provider)
    first = application.send_message("Поставь завтра в 10", project_id=PROJECT_ID)
    second = application.send_message(
        "Занятие по AI",
        project_id=PROJECT_ID,
        conversation_id=first.conversation_id,
    )

    assert first.assistant_message.content == "Что именно поставить в календарь?"
    assert second.assistant_message.content == "На сколько времени поставить?"
    third = application.send_message(
        "на час",
        project_id=PROJECT_ID,
        conversation_id=first.conversation_id,
    )
    assert "Занятие по AI" in third.assistant_message.content
    assert "10:00–11:00" in third.assistant_message.content
    assert third.pending_confirmation.confirmation_type == "google_calendar_create"


def test_restart_recovers_pending_meaning_and_proposes_without_provider_mutation(tmp_path):
    root, provider, application = _application(tmp_path)
    first = application.send_message(
        "Запиши занятие завтра в 10 на час", project_id=PROJECT_ID
    )
    state_path = root / "local-data" / "runtime" / "pending-resolutions.json"
    assert state_path.exists()
    resolution_id = application.dialogue_diagnostics(
        first.conversation_id
    ).dialogue_state.active_flow_id

    restarted = build_masha_application(
        project_root=root,
        router=ModelRouter([provider]),
    )
    second = restarted.send_message(
        "В календарь",
        project_id=PROJECT_ID,
        conversation_id=first.conversation_id,
    )
    restarted_diagnostic = restarted.dialogue_diagnostics(first.conversation_id)

    assert second.pending_confirmation.confirmation_type == "google_calendar_create"
    assert restarted_diagnostic.dialogue_state.active_flow_id is None
    assert restarted_diagnostic.dialogue_state.last_decision.pending_resolution_id == resolution_id
    assert provider.requests == []
    receipts = restarted._conversation._conversation.google_calendar_create_service.writer.receipt_store._items
    assert {item.status for item in receipts.values()} == {"proposed"}
    assert all(item.confirmed_at is None for item in receipts.values())


def test_not_a_follow_up_reaches_model_and_pending_can_resolve_later(tmp_path):
    _, provider, application = _application(
        tmp_path, provider=LocalProvider("Завтра будет спокойно.")
    )
    first = application.send_message(
        "Запиши занятие завтра в 10 на час", project_id=PROJECT_ID
    )
    question = application.send_message(
        "Какая завтра погода?",
        project_id=PROJECT_ID,
        conversation_id=first.conversation_id,
    )
    coffee = application.send_message(
        "Маш, я кофе сделал",
        project_id=PROJECT_ID,
        conversation_id=first.conversation_id,
    )
    assert application.dialogue_diagnostics(
        first.conversation_id
    ).dialogue_state.active_flow_id is not None
    final = application.send_message(
        "В календарь",
        project_id=PROJECT_ID,
        conversation_id=first.conversation_id,
    )

    assert question.assistant_message.content == "Завтра будет спокойно."
    assert "поставить" not in coffee.assistant_message.content.casefold()
    assert final.pending_confirmation.confirmation_type == "google_calendar_create"


def test_new_schedule_supersedes_old_and_preview_uses_only_new_meaning(tmp_path):
    _, _, application = _application(tmp_path)
    first = application.send_message(
        "Запиши занятие завтра в 10 на час", project_id=PROJECT_ID
    )
    second = application.send_message(
        "Запиши тренировку завтра в 12 на час",
        project_id=PROJECT_ID,
        conversation_id=first.conversation_id,
    )
    preview = application.send_message(
        "В календарь",
        project_id=PROJECT_ID,
        conversation_id=first.conversation_id,
    )

    assert "Тренировку" in second.assistant_message.content
    assert "тренировку" in preview.assistant_message.content
    assert "12:00–13:00" in preview.assistant_message.content
    assert "занятие" not in preview.assistant_message.content


def test_ordinary_phrases_never_create_pending_semantic_state(tmp_path):
    _, provider, application = _application(tmp_path)
    for message in (
        "Короткий итог сегодняшнего занятия",
        "Маш, иди сюда, хочу немного побыть с тобой",
        "Сегодня мы продолжили делать наш Дом...",
    ):
        turn = application.send_message(message, project_id=PROJECT_ID)
        assert application.dialogue_diagnostics(
            turn.conversation_id
        ).dialogue_state.active_flow_id is None
        assert turn.pending_confirmation is None


def test_live_wrapped_schedule_uses_semantics_then_existing_clarification(tmp_path):
    provider = LocalProvider(json.dumps({
        "kind": "supported_action",
        "candidate_operation_ids": [
            "google_calendar.event.create",
            "home.timed_commitments",
        ],
        "nearby_operation_ids": [],
        "extracted_slots": [
            {"name": "subject", "evidence_text": "занятие"},
            {"name": "date", "evidence_text": "завтра"},
            {"name": "time", "evidence_text": "11"},
        ],
        "unresolved_referents": [],
        "ambiguity_hint": "capability",
        "operation_selection_evidence": None,
    }, ensure_ascii=False))
    provider.capabilities = ModelCapabilities(structured_output=True)
    _, _, application = _application(tmp_path, provider=provider)

    turn = application.send_message(
        "Доброе утро, Маша! Запиши занятие завтра в 11",
        project_id=PROJECT_ID,
    )

    assert turn.assistant_message.content == (
        "Занятие — поставить в календарь или просто напомнить в 11:00?"
    )
    assert turn.pending_confirmation is None
    assert provider.requests[-1].required_capabilities.structured_output is True
    assert application._conversation._conversation.google_calendar_create_service.writer.receipt_store._items == {}


def test_semantically_resolved_indirect_reminder_still_requires_confirmation(tmp_path):
    provider = LocalProvider(json.dumps({
        "kind": "supported_action",
        "candidate_operation_ids": ["home.timed_commitments"],
        "nearby_operation_ids": [],
        "extracted_slots": [
            {"name": "subject", "evidence_text": "занятие"},
            {"name": "date", "evidence_text": "завтра"},
            {"name": "time", "evidence_text": "одиннадцать"},
        ],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
        "operation_selection_evidence": {
            "operation_id": "home.timed_commitments",
            "evidence_text": "надо не забыть",
        },
    }, ensure_ascii=False))
    provider.capabilities = ModelCapabilities(structured_output=True)
    _, _, application = _application(tmp_path, provider=provider)
    before = application.commitments().items

    turn = application.send_message(
        "Маш, у меня завтра в одиннадцать занятие, надо не забыть",
        project_id=PROJECT_ID,
    )

    assert turn.pending_confirmation is not None
    assert turn.pending_confirmation.confirmation_type == "commitment_create"
    assert application.commitments().items == before


def test_public_dialogue_diagnostics_reports_handoff_without_private_store_access(tmp_path):
    _, _, application = _application(tmp_path)
    first = application.send_message(
        "Запиши занятие завтра в 10 на час",
        project_id=PROJECT_ID,
    )
    second = application.send_message(
        "В календарь",
        project_id=PROJECT_ID,
        conversation_id=first.conversation_id,
    )

    diagnostic = application.dialogue_diagnostics(first.conversation_id)

    assert second.pending_confirmation is not None
    assert diagnostic.dialogue_state.active_flow_id is None
    assert diagnostic.application_handoff_type == "google_calendar.event.create"
    assert diagnostic.response_projection_state == "waiting_confirmation"
    serialized = diagnostic.model_dump_json()
    assert "proposal_id" not in serialized
    assert "provider" not in serialized
