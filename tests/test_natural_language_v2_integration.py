from __future__ import annotations

import shutil
from pathlib import Path

from backend.application import ConversationTurnStatus, build_masha_application
from backend.llm.fake_provider import FakeProvider
from backend.llm.model_router import ModelRouter
from backend.memory.sqlite_repository import MemorySqliteRepository


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ID = "project_masha_home"


class LocalProvider(FakeProvider):
    def __init__(self, response_text="Обычный разговор."):
        super().__init__(provider_id="ollama-local", response_text=response_text)
        self.available_models = {"qwen3.5:9b", "qwen3.5:4b"}

    def is_model_available(self, model_id: str) -> bool:
        return model_id in self.available_models


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


def test_calendar_choice_reaches_existing_preview_with_zero_provider_effects(tmp_path, monkeypatch):
    import socket

    root, model, application = _application(tmp_path)
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network")),
    )

    first = application.send_message(
        "Маша, запиши занятие завтра в 10", project_id=PROJECT_ID
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
        "Маша, запиши занятие завтра в 10",
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
    _, _, application = _application(tmp_path)
    first = application.send_message("Поставь завтра в 10", project_id=PROJECT_ID)
    second = application.send_message(
        "Занятие по AI",
        project_id=PROJECT_ID,
        conversation_id=first.conversation_id,
    )

    assert first.assistant_message.content == "Что именно поставить в календарь?"
    assert "Занятие по AI" in second.assistant_message.content
    assert "10:00–11:00" in second.assistant_message.content
    assert second.pending_confirmation.confirmation_type == "google_calendar_create"


def test_restart_recovers_pending_meaning_and_proposes_without_provider_mutation(tmp_path):
    root, provider, application = _application(tmp_path)
    first = application.send_message(
        "Запиши занятие завтра в 10", project_id=PROJECT_ID
    )
    state_path = root / "local-data" / "runtime" / "pending-resolutions.json"
    assert state_path.exists()
    resolution_id = application._conversation._conversation.natural_language_coordinator.store.active_for_conversation(
        first.conversation_id
    ).resolution_id

    restarted = build_masha_application(
        project_root=root,
        router=ModelRouter([provider]),
    )
    second = restarted.send_message(
        "В календарь",
        project_id=PROJECT_ID,
        conversation_id=first.conversation_id,
    )
    stored = restarted._conversation._conversation.natural_language_coordinator.store.get(
        resolution_id
    )

    assert second.pending_confirmation.confirmation_type == "google_calendar_create"
    assert stored.status.value == "resolved"
    assert provider.requests == []
    receipts = restarted._conversation._conversation.google_calendar_create_service.writer.receipt_store._items
    assert {item.status for item in receipts.values()} == {"proposed"}
    assert all(item.confirmed_at is None for item in receipts.values())


def test_not_a_follow_up_reaches_model_and_pending_can_resolve_later(tmp_path):
    _, provider, application = _application(
        tmp_path, provider=LocalProvider("Завтра будет спокойно.")
    )
    first = application.send_message(
        "Запиши занятие завтра в 10", project_id=PROJECT_ID
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
    store = application._conversation._conversation.natural_language_coordinator.store
    assert store.active_for_conversation(first.conversation_id) is not None
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
        "Запиши занятие завтра в 10", project_id=PROJECT_ID
    )
    second = application.send_message(
        "Запиши тренировку завтра в 12",
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
        store = application._conversation._conversation.natural_language_coordinator.store
        assert store.active_for_conversation(turn.conversation_id) is None
        assert turn.pending_confirmation is None
