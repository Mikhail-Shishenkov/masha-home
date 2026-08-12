from __future__ import annotations

import hashlib
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.application import (
    ApplicationBoundaryError,
    ApplicationErrorCode,
    ConversationTurnStatus,
    MashaApplication,
    build_masha_application,
)
from backend.application.catalogs import error_label, proactive_reason_label
from backend.application.contracts import ModelAvailabilityCode, ModelSwitchStatus
from backend.llm.fake_provider import FakeProvider
from backend.llm.model_router import ModelRouter
from backend.memory.sqlite_repository import MemorySqliteRepository
from backend.memory.memory_models import CommitmentStatus
from backend.presentation import PresenceActivity
from backend.temporal.temporal_engine import FixedClock, TemporalEngine


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ID = "project_masha_home"


class LocalProfileProvider(FakeProvider):
    def __init__(
        self,
        *,
        available: bool = True,
        available_models: set[str] | None = None,
        simulate_timeout: bool = False,
        response_text: str = "Привет, Миша.",
    ):
        super().__init__(
            provider_id="ollama-local",
            available=available,
            simulate_timeout=simulate_timeout,
            response_text=response_text,
        )
        self.available_models = available_models or {"qwen3.5:9b", "qwen3.5:4b"}

    def is_model_available(self, model_id: str) -> bool:
        return model_id in self.available_models


def _isolated_root(tmp_path: Path) -> Path:
    root = tmp_path / "masha-home"
    shutil.copytree(PROJECT_ROOT / "identity", root / "identity")
    shutil.copytree(PROJECT_ROOT / "skills", root / "skills")
    repository = MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    repository.import_json(PROJECT_ROOT / "memory" / "test_memory.json")
    return root


def _application(tmp_path: Path, provider: LocalProfileProvider | None = None):
    root = _isolated_root(tmp_path)
    selected = provider or LocalProfileProvider()
    application = build_masha_application(
        project_root=root,
        router=ModelRouter([selected]),
    )
    return root, selected, application


def test_public_composition_root_builds_without_cli(tmp_path):
    root, _, application = _application(tmp_path)

    assert isinstance(application, MashaApplication)
    assert application.current_model().profile_id == "primary"
    assert (root / "local-data" / "conversations" / "history.json").exists() is False


def test_completed_turn_returns_ui_safe_messages_and_survives_restart(tmp_path):
    root, provider, application = _application(tmp_path)

    result = application.send_message("Привет", project_id=PROJECT_ID)

    assert result.status is ConversationTurnStatus.COMPLETED
    assert result.error_code is None
    assert result.active_profile_id == "primary"
    assert result.user_message.persisted is True
    assert result.user_message.message_id
    assert result.assistant_message is not None
    assert result.assistant_message.content == provider.response_text
    view = application.conversation(result.conversation_id)
    assert tuple(message.message_id for message in view.messages) == (
        result.user_message.message_id,
        result.assistant_message.message_id,
    )

    restarted = build_masha_application(
        project_root=root,
        router=ModelRouter([provider]),
    )
    assert restarted.conversation(result.conversation_id) == view


@pytest.mark.parametrize(
    ("provider", "status", "code"),
    [
        (
            LocalProfileProvider(available=False),
            ConversationTurnStatus.MODEL_UNAVAILABLE,
            ApplicationErrorCode.MODEL_UNAVAILABLE,
        ),
        (
            LocalProfileProvider(simulate_timeout=True),
            ConversationTurnStatus.TIMEOUT,
            ApplicationErrorCode.MODEL_TIMEOUT,
        ),
    ],
)
def test_controlled_model_errors_preserve_user_message(tmp_path, provider, status, code):
    _, _, application = _application(tmp_path, provider)

    result = application.send_message("Ты здесь?", project_id=PROJECT_ID)

    assert result.status is status
    assert result.error_code is code
    assert result.error_label == error_label(code)
    assert result.user_message.persisted is True
    assert result.assistant_message is None
    assert application.conversation(result.conversation_id).messages == (result.user_message,)


def test_unknown_conversation_is_a_failed_transient_turn(tmp_path):
    _, _, application = _application(tmp_path)

    result = application.send_message(
        "Привет",
        project_id=PROJECT_ID,
        conversation_id="missing-conversation",
    )

    assert result.status is ConversationTurnStatus.FAILED
    assert result.error_code is ApplicationErrorCode.CONVERSATION_FAILED
    assert result.user_message.persisted is False
    assert result.assistant_message is None
    with pytest.raises(ApplicationBoundaryError) as error:
        application.conversation("missing-conversation")
    assert error.value.code is ApplicationErrorCode.CONVERSATION_NOT_FOUND


def test_model_settings_check_before_switch_and_preserve_domain_state(tmp_path):
    root, provider, application = _application(tmp_path)
    initial_turn = application.send_message("Начинаем", project_id=PROJECT_ID)
    identity_path = root / "identity" / "masha.identity.json"
    memory_path = root / "local-data" / "memory" / "masha.sqlite3"
    history_path = root / "local-data" / "conversations" / "history.json"
    before = {
        "identity": identity_path.read_bytes(),
        "memory": hashlib.sha256(memory_path.read_bytes()).digest(),
        "history": history_path.read_bytes(),
    }

    switched = application.use_model("fast")

    assert switched.status is ModelSwitchStatus.APPLIED
    assert switched.active_profile.profile_id == "fast"
    assert identity_path.read_bytes() == before["identity"]
    assert hashlib.sha256(memory_path.read_bytes()).digest() == before["memory"]
    assert history_path.read_bytes() == before["history"]
    continuation = application.send_message(
        "Продолжаем",
        project_id=PROJECT_ID,
        conversation_id=initial_turn.conversation_id,
    )
    assert continuation.active_profile_id == "fast"
    assert provider.last_request.execution_model_id == "qwen3.5:4b"


def test_failed_model_switch_keeps_previous_profile(tmp_path):
    provider = LocalProfileProvider(available_models={"qwen3.5:9b"})
    _, _, application = _application(tmp_path, provider)

    result = application.use_model("fast")

    assert result.status is ModelSwitchStatus.REJECTED
    assert result.error_code is ApplicationErrorCode.MODEL_UNAVAILABLE
    assert result.active_profile.profile_id == "primary"
    assert application.current_model().profile_id == "primary"


def test_status_keeps_proactive_stop_and_model_failure_distinct(tmp_path):
    _, provider, application = _application(tmp_path)

    initial = application.status()
    assert initial.proactive_enabled is False
    assert initial.emergency_stop_engaged is False
    assert initial.model_available is True

    application.emergency_stop("ui_test")
    provider.available = False
    stopped = application.status()

    assert stopped.proactive_enabled is False
    assert stopped.emergency_stop_engaged is True
    assert stopped.model_available is False
    assert stopped.model_availability_code is ModelAvailabilityCode.PROVIDER_UNAVAILABLE
    assert stopped.safety_label != stopped.proactive_label
    assert not any(
        forbidden in stopped.model_dump_json().casefold()
        for forbidden in ("sqlite", "local-data", ".json", "lock", "path")
    )

    resumed = application.resume_autonomy()
    assert resumed.emergency_stop_engaged is False
    assert application.status().proactive_enabled is False


def test_visual_resolver_hides_paths_and_checks_canonical_integrity(tmp_path):
    root, _, application = _application(tmp_path)

    assets = application.canonical_visual_assets()
    assert len(assets) == 2
    assert all("path" not in item.model_dump() for item in assets)
    resolved = application.resolve_visual_asset(assets[0].asset_id)
    assert resolved.asset == assets[0]
    assert resolved.asset.media_type == "image/png"
    assert resolved.content.startswith(b"\x89PNG\r\n\x1a\n")

    manifest_asset = root / "identity" / "visual_assets" / "masha-concert-2026-06-20.png"
    manifest_asset.write_bytes(manifest_asset.read_bytes() + b"tampered")
    with pytest.raises(ApplicationBoundaryError) as error:
        application.resolve_visual_asset("masha_concert_2026_06_20")
    assert error.value.code is ApplicationErrorCode.VISUAL_ASSET_INTEGRITY_FAILED


def test_read_views_and_ordinary_chat_do_not_mutate_long_term_memory(tmp_path):
    root, _, application = _application(tmp_path)
    repository = MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    before = repository.read_document()

    application.model_profiles()
    application.canonical_visual_assets()
    application.status()
    application.send_message("Обычный разговор", project_id=PROJECT_ID)

    assert repository.read_document() == before


def test_commitment_projection_uses_temporal_engine_and_keeps_exact_due_open(tmp_path):
    root, _, application = _application(tmp_path)
    repository = MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    document = repository.read_document()
    now = datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc)
    template = document.commitments[0]
    commitments = [
        template.model_copy(update={"text": "Сдать макет", "due_at": now}),
        template.model_copy(update={"id": "commitment_future", "text": "Проверить интерфейс", "due_at": now + timedelta(hours=2)}),
        template.model_copy(update={"id": "commitment_overdue", "text": "Ответить на письмо", "due_at": now - timedelta(seconds=1)}),
        template.model_copy(
            update={
                "id": "commitment_done",
                "text": "Подготовить основу",
                "status": CommitmentStatus.COMPLETED,
                "due_at": now - timedelta(days=1),
                "completed_at": now - timedelta(hours=1),
                "updated_at": now - timedelta(hours=1),
            }
        ),
    ]
    repository.replace_document(
        document.model_copy(update={"commitments": commitments}),
        action="test_commitment_projection",
    )
    application._commitments._conversation.temporal_engine = TemporalEngine(FixedClock(now))
    before = repository.read_document()

    view = application.commitments()

    by_id = {item.commitment_id: item for item in view.items}
    assert by_id[template.id].status == "open"
    assert by_id["commitment_future"].status == "upcoming"
    assert by_id["commitment_overdue"].status == "overdue"
    assert by_id["commitment_done"].status == "completed"
    assert by_id["commitment_done"].can_propose_completion is False
    assert repository.read_document() == before


def test_selected_commitment_enters_existing_confirmation_flow_and_survives_restart(tmp_path):
    root, provider, application = _application(tmp_path)
    repository = MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    before = repository.read_document()
    commitment = before.commitments[0]

    proposed = application.propose_commitment_completion(
        commitment_id=commitment.id,
        conversation_id=None,
        project_id=PROJECT_ID,
    )

    assert proposed.pending_confirmation.confirmation_type == "commitment_complete"
    assert proposed.pending_confirmation.subject == commitment.text
    assert proposed.pending_confirmation.proposal_id not in proposed.assistant_message.content
    assert provider.last_request is None
    assert repository.read_document() == before

    restarted = build_masha_application(project_root=root, router=ModelRouter([provider]))
    assert restarted.pending_confirmation(proposed.conversation_id) == proposed.pending_confirmation
    resolved = restarted.resolve_confirmation(
        conversation_id=proposed.conversation_id,
        proposal_id=proposed.pending_confirmation.proposal_id,
        decision="confirm",
        project_id=PROJECT_ID,
    )

    assert resolved.status.value == "confirmed"
    stored = repository.read_document()
    updated = next(item for item in stored.commitments if item.id == commitment.id)
    assert updated.status is CommitmentStatus.COMPLETED
    assert updated.completed_at is not None
    with pytest.raises(ValueError, match="not open"):
        restarted.propose_commitment_completion(
            commitment_id=commitment.id,
            conversation_id=proposed.conversation_id,
            project_id=PROJECT_ID,
        )


def test_commitment_confirmation_projection_uses_existing_proposal_flow(tmp_path):
    root, provider, application = _application(tmp_path)
    repository = MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    before = repository.read_document()

    proposal_turn = application.send_message(
        "Маша, запомни, что завтра в 18:00 нужно отправить отчёт",
        project_id=PROJECT_ID,
    )

    assert proposal_turn.status is ConversationTurnStatus.COMPLETED
    assert proposal_turn.pending_confirmation is not None
    pending = proposal_turn.pending_confirmation
    assert pending.confirmation_type == "commitment_create"
    assert pending.subject == "отправить отчёт"
    assert pending.due_at is not None
    assert pending.allowed_actions == ("confirm", "reject")
    assert pending.proposal_id not in proposal_turn.assistant_message.content
    assert repository.read_document() == before
    assert provider.last_request is None

    resolved = application.resolve_confirmation(
        conversation_id=proposal_turn.conversation_id,
        proposal_id=pending.proposal_id,
        decision="confirm",
        project_id=PROJECT_ID,
    )

    assert resolved.status.value == "confirmed"
    assert resolved.pending_confirmation is None
    assert resolved.user_message.content == "Подтверждаю."
    assert resolved.assistant_message.content == "Готово, сохранила."
    document = repository.read_document()
    assert len(document.commitments) == len(before.commitments) + 1
    assert any(item.text == "отправить отчёт" for item in document.commitments)


def test_commitment_confirmation_reject_and_restart_are_honest(tmp_path):
    root, provider, application = _application(tmp_path)
    repository = MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    before = repository.read_document()
    turn = application.send_message(
        "Маша, запомни как обязательство отправить письмо",
        project_id=PROJECT_ID,
    )
    pending = turn.pending_confirmation
    assert pending is not None

    restarted = build_masha_application(
        project_root=root,
        router=ModelRouter([provider]),
    )
    assert restarted.pending_confirmation(turn.conversation_id) == pending

    resolved = restarted.resolve_confirmation(
        conversation_id=turn.conversation_id,
        proposal_id=pending.proposal_id,
        decision="reject",
        project_id=PROJECT_ID,
    )

    assert resolved.status.value == "rejected"
    assert resolved.user_message.content == "Не сейчас."
    assert resolved.assistant_message.content == "Хорошо, не сохраняю."
    assert repository.read_document() == before


def test_home_snapshot_is_a_read_only_application_owned_projection(tmp_path):
    root, _, application = _application(tmp_path)
    repository = MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    before = repository.read_document()

    snapshot = application.home_snapshot()

    assert snapshot.status.active_profile_id == "primary"
    assert snapshot.active_model.profile_id == "primary"
    assert snapshot.presentation.overlays.active_profile_id == "primary"
    assert snapshot.presentation.presence.visual_identity.asset_ids == tuple(
        asset.asset_id for asset in snapshot.visual_assets
    )
    assert snapshot.composition.source_revision == snapshot.presentation.revision
    assert snapshot.composition.primary_surface_id is None
    assert "sqlite" not in snapshot.model_dump_json().casefold()
    assert repository.read_document() == before


def test_home_presentation_session_is_deterministic_and_has_no_domain_mutation(tmp_path):
    root, _, application = _application(tmp_path)
    repository = MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    before = repository.read_document()
    session = application.open_home_session()

    opened = session.opened()
    listening = session.user_sent()
    thinking = session.assistant_thinking()
    responded = session.assistant_responded()

    assert opened.presentation.opened is True
    assert opened.presentation.active_surface_id == "home.conversation"
    assert listening.presentation.presence.activity is PresenceActivity.WAITING
    assert thinking.presentation.presence.activity is PresenceActivity.PROCESSING
    assert responded.presentation.presence.activity is PresenceActivity.SPEAKING
    assert responded.composition.primary_surface_id == "home.conversation"
    assert repository.read_document() == before


def test_home_attention_exposes_only_active_conversation_model_and_safety(tmp_path):
    root, _, application = _application(tmp_path)
    first = application.send_message("Первый разговор", project_id=PROJECT_ID)
    second = application.send_message("Вторая ветка", project_id=PROJECT_ID)

    attention = application.home_attention(conversation_id=first.conversation_id)

    assert attention.active_conversation is not None
    assert attention.active_conversation.conversation_id == first.conversation_id
    assert attention.model_available is True
    assert attention.emergency_stop_engaged is False
    assert set(attention.model_dump()) == {
        "observed_at",
        "active_conversation",
        "model_available",
        "model_label",
        "emergency_stop_engaged",
        "safety_label",
        "commitments_count",
    }
    assert attention.commitments_count == 1
    assert application.home_attention(conversation_id=None).active_conversation is None
    assert second.conversation_id != first.conversation_id

    application.emergency_stop()
    restarted = build_masha_application(
        project_root=root,
        router=ModelRouter([LocalProfileProvider()]),
    )
    assert restarted.home_attention(
        conversation_id=first.conversation_id
    ).emergency_stop_engaged is True


def test_recent_conversation_summaries_use_existing_history_order(tmp_path):
    _, _, application = _application(tmp_path)
    first = application.send_message("Первый разговор", project_id=PROJECT_ID)
    second = application.send_message("Второй разговор", project_id=PROJECT_ID)

    recent = application.recent_conversations()

    assert [item.conversation_id for item in recent[:2]] == [
        second.conversation_id,
        first.conversation_id,
    ]
    assert recent[0].preview == "Привет, Миша."


def test_human_catalogs_do_not_replace_machine_codes():
    assert error_label(ApplicationErrorCode.MODEL_UNAVAILABLE) == "Локальная модель недоступна"
    assert proactive_reason_label("quiet_hours") == "Сейчас тихие часы"
    assert proactive_reason_label("new_future_reason") == "Причина пока не переведена"
    assert ApplicationErrorCode.MODEL_UNAVAILABLE.value == "MODEL_UNAVAILABLE"
