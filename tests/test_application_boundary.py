from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.application import (
    ApplicationBoundaryError,
    ApplicationErrorCode,
    ConversationTurnStatus,
    MashaApplication,
    build_masha_application,
    HumanSearchRequest,
    RecallMode,
)
from backend.application.catalogs import error_label, proactive_reason_label
from backend.application.contracts import ModelAvailabilityCode, ModelSwitchStatus
from backend.llm.fake_provider import FakeProvider
from backend.llm.model_models import ModelCapabilities
from backend.llm.model_router import ModelRouter
from backend.memory.sqlite_repository import MemorySqliteRepository
from backend.memory.memory_management import MemoryManagementService, MemoryMutationOperation
from backend.memory.memory_models import CommitmentStatus
from backend.presentation import HomeMoment, HomeProximity, PresenceActivity
from backend.skills.agent_loop import (
    AgentRunReceipt,
    AgentRunStatus,
    AgentRunStore,
    AgentStepReceipt,
    AgentStepStatus,
)
from backend.skills.autonomy import ActionDecision
from backend.temporal.proactive_events import (
    ProactiveEvent,
    ProactiveEventState,
    ProactiveEventStore,
    ProactiveEventType,
    check_in_event_id,
)
from backend.temporal.proactive_interaction import ProactiveInteractionStore
from backend.temporal.temporal_models import CheckInCandidate
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


def test_conversation_core_import_does_not_depend_on_application_import_order():
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from backend.conversation.resolution_coordinator "
                "import V2LiveAdoptionPolicy; "
                "assert V2LiveAdoptionPolicy().supported_operation_ids"
            ),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_public_composition_root_builds_without_cli(tmp_path):
    root, _, application = _application(tmp_path)

    assert isinstance(application, MashaApplication)
    assert application.current_model().profile_id == "primary"
    assert (root / "local-data" / "conversations" / "history.json").exists() is False
    conversation = application._conversation._conversation
    assert (
        conversation.resolved_capability_adapters.operation_ids
        == conversation.dialogue_core.adoption.supported_operation_ids
    )
    assert "web.fetch" in conversation.resolved_capability_adapters.operation_ids


def test_workbench_projects_four_local_read_connections_without_network(tmp_path, monkeypatch):
    import socket

    _, _, application = _application(tmp_path)
    monkeypatch.setattr(socket, "create_connection", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network")))

    connections = application.workbench().connections

    assert [(item.connector_id, item.state, item.access) for item in connections] == [
        ("google-calendar", "disconnected", "read_only"),
        ("google-drive", "disconnected", "read_only"),
        ("yandex-mail", "disconnected", "read_only"),
        ("yandex-disk", "disconnected", "read_only"),
    ]
    rendered = str([item.model_dump() for item in connections])
    assert "secret_ref" not in rendered and "oauth" not in rendered.casefold()


def test_calendar_create_is_a_pending_application_confirmation_before_any_network_or_model(tmp_path, monkeypatch):
    import socket

    _, provider, application = _application(tmp_path)
    monkeypatch.setattr(socket, "create_connection", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network")))
    turn = application.send_message(
        "Маша, поставь занятие по AI в календарь завтра в 19:00 на час",
        project_id=PROJECT_ID,
    )
    pending = application.pending_confirmation(turn.conversation_id)
    assert turn.status is ConversationTurnStatus.COMPLETED
    assert pending is not None and pending.confirmation_type == "google_calendar_create"
    assert "занятие по AI" in pending.subject
    assert provider.requests == []


def test_typed_human_information_api_searches_and_proposes_restore_without_fake_command(tmp_path):
    root, _, application = _application(tmp_path)
    repository = MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    management = MemoryManagementService(repository)
    fact = next(item for item in management.list(record_type="fact") if item.payload["status"] == "active")
    management.apply(
        operation=MemoryMutationOperation.FORGET,
        record_id=fact.record_id,
        proposal_id="typed-api-test-setup",
    )
    turn = application.send_message("Привет", project_id=PROJECT_ID)

    normal = application.search_information(HumanSearchRequest(query=fact.payload["key"]))
    forgotten = application.search_information(HumanSearchRequest(
        query=fact.payload["key"], mode=RecallMode.FORGOTTEN_REVIEW,
    ))
    pending = application.restore_information(
        record_id=fact.record_id,
        conversation_id=turn.conversation_id,
    )

    assert fact.record_id not in {item.ref.entity_id for item in normal.items}
    assert fact.record_id in {item.ref.entity_id for item in forgotten.items}
    assert pending.confirmation_type == "memory_restore"
    resolution = application.resolve_confirmation(
        conversation_id=turn.conversation_id,
        proposal_id=pending.proposal_id,
        decision="confirm",
        project_id=PROJECT_ID,
    )
    assert resolution.status.value == "confirmed"
    assert management.get(fact.record_id).payload["visibility"] == "visible"


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


def test_ordinary_llm_turn_cannot_claim_unreceipted_mutation(tmp_path):
    provider = LocalProfileProvider(
        response_text="Сохранила второе обязательство — купить билеты на фестиваль."
    )
    _, _, application = _application(tmp_path, provider)
    before = application._conversation._conversation.memory_retriever.memory_store.read_document()

    result = application.send_message(
        "Как тебе идея фестиваля?",
        project_id=PROJECT_ID,
    )

    assert result.status is ConversationTurnStatus.COMPLETED
    assert result.pending_confirmation is None
    assert result.assistant_message is not None
    assert "Я пока ничего не меняла" in result.assistant_message.content
    assert "в этом сообщении Дом" not in result.assistant_message.content
    after = application._conversation._conversation.memory_retriever.memory_store.read_document()
    assert after.commitments == before.commitments
    assert application.conversation(result.conversation_id).messages[-1].content == result.assistant_message.content


@pytest.mark.parametrize(
    "claim",
    (
        "Эту нить удаляю.",
        "Сейчас сохраню это как дело.",
        "Закрываю задачу.",
        "Я это уже изменила.",
        "Занятие на завтра в 11 уже запланировано.",
    ),
)
def test_ordinary_llm_turn_blocks_present_and_near_future_mutation_claims(tmp_path, claim):
    _, _, application = _application(tmp_path, LocalProfileProvider(response_text=claim))

    result = application.send_message("Расскажи, что ты думаешь", project_id=PROJECT_ID)

    assert result.assistant_message is not None
    assert "Я пока ничего не меняла" in result.assistant_message.content
    assert "в этом сообщении Дом" not in result.assistant_message.content


def test_response_contract_allows_discussion_and_receipted_success():
    from backend.conversation.response_contract import render_model_response

    discussion = "Я думаю, стоит удалить эту тему, если ты этого захочешь."
    execution = "Сейчас сохраню это как дело."

    assert render_model_response(discussion) == discussion
    assert render_model_response(execution) != execution
    assert render_model_response(execution, application_receipts=("receipt",)) == execution


def test_response_contract_allows_grounded_completed_task_readout_but_not_unrelated_write():
    from backend.conversation.response_contract import render_model_response

    readout = "Дело «Проверить батарею MacBook» уже выполнено."
    unrelated = "Готово, задача создана: купить билеты."
    grounded = ("Дело · завершено: Проверить батарею MacBook",)

    assert render_model_response(readout, grounded_completed_items=grounded) == readout
    assert render_model_response(unrelated, grounded_completed_items=grounded) != unrelated


def test_response_contract_does_not_treat_do_not_forget_advice_as_completed_mutation():
    from backend.conversation.response_contract import render_model_response

    advice = "Дело уже открыто. Не забудь проверить новый вариант."
    assert render_model_response(advice) == advice


@pytest.mark.parametrize(
    "answer",
    (
        "Бетельгейзе находится в Млечном Пути. Её яркость изменяется со временем.",
        "Яркость звезды изменяется.",
        "Модель обновляется раз в месяц.",
        "Если изменить настройку, результат будет другим.",
        "Можно удалить запись после подтверждения.",
        "Я изменила мнение после разговора.",
        "Мы обновили подход к выбору модели.",
        "Всё со временем изменилось.",
    ),
)
def test_response_contract_allows_non_application_change_language(answer):
    from backend.conversation.response_contract import render_model_response

    assert render_model_response(answer) == answer


@pytest.mark.parametrize(
    "claim",
    (
        "Я сохранила это в память.",
        "Я сейчас изменяю запись.",
        "Готово, задача создана.",
        "Запись уже удалена.",
    ),
)
def test_response_contract_still_blocks_application_mutation_claims_with_safe_diagnostic(claim):
    from backend.conversation.response_contract import (
        render_model_response,
        response_guard_diagnostics,
    )

    before = len(response_guard_diagnostics())
    assert render_model_response(claim) != claim
    diagnostic = response_guard_diagnostics()[-1]
    assert len(response_guard_diagnostics()) == before + 1
    assert diagnostic["rule"]
    assert diagnostic["character_count"] == len(claim)
    assert "content" not in diagnostic


def test_response_contract_blocks_unverified_planning_claim_generically():
    from backend.conversation.response_contract import (
        UNRECEIPTED_MUTATION_RESPONSE,
        render_model_response,
    )

    claim = "Занятие на завтра в 11 уже запланировано."

    assert render_model_response(claim) == UNRECEIPTED_MUTATION_RESPONSE
    assert render_model_response(
        claim,
        application_receipts=("verified-calendar-receipt",),
    ) == claim


def test_ambiguous_follow_up_neither_creates_nor_claims_commitment(tmp_path):
    _, provider, application = _application(tmp_path)
    before = application._conversation._conversation.memory_retriever.memory_store.read_document()

    result = application.send_message(
        "и ещё одно — купить билеты на фестиваль",
        project_id=PROJECT_ID,
    )

    assert result.pending_confirmation is None
    assert "пока ничего не добавляю" in result.assistant_message.content
    assert provider.last_request is None
    after = application._conversation._conversation.memory_retriever.memory_store.read_document()
    assert after.commitments == before.commitments


def test_natural_commitment_variants_strip_service_words_and_require_confirmation(tmp_path):
    _, _, application = _application(tmp_path)
    phrases = (
        "дело добавь купить билеты в Москву",
        "добавь обязательство купить билеты в Москву",
        "добавь нам дело купить билеты в Москву",
        "и ещё задача купить билеты в Москву",
    )

    for phrase in phrases:
        result = application.send_message(phrase, project_id=PROJECT_ID)
        assert result.pending_confirmation is not None
        assert result.pending_confirmation.confirmation_type == "commitment_create"
        assert result.pending_confirmation.subject == "купить билеты в Москву"
        application.resolve_confirmation(
            conversation_id=result.conversation_id,
            proposal_id=result.pending_confirmation.proposal_id,
            decision="reject",
            project_id=PROJECT_ID,
        )


def test_timed_task_without_explicit_reminder_keeps_policy_controlled_origin(tmp_path):
    _, _, application = _application(tmp_path)
    result = application.send_message(
        "добавь дело закрыть окно завтра в 10:30",
        project_id=PROJECT_ID,
    )
    application.resolve_confirmation(
        conversation_id=result.conversation_id,
        proposal_id=result.pending_confirmation.proposal_id,
        decision="confirm",
        project_id=PROJECT_ID,
    )

    commitment = next(
        item
        for item in application._conversation._conversation.memory_retriever.memory_store.read_document().commitments
        if "закрыть окно" in item.text
    )
    assert commitment.reminder_delivery_mode.value == "policy_controlled"


def test_command_typo_can_use_semantic_ingress_but_bare_action_is_not_a_command(tmp_path):
    semantic = LocalProfileProvider(response_text=json.dumps({
        "kind": "supported_action",
        "candidate_operation_ids": ["home.commitments.create"],
        "nearby_operation_ids": [],
        "extracted_slots": [
            {"name": "subject", "evidence_text": "купить корм собаке"},
        ],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
        "action_request_evidence": {"evidence_text": "добвь задачу"},
        "operation_selection_evidence": {
            "operation_id": None,
            "evidence_text": None,
        },
    }, ensure_ascii=False))
    semantic.capabilities = ModelCapabilities(structured_output=True)
    _, _, application = _application(tmp_path / "typo", semantic)
    repository = application._conversation._conversation.memory_retriever.memory_store
    before = repository.read_document()

    typo = application.send_message("добвь задачу купить корм собаке", project_id=PROJECT_ID)

    assert typo.pending_confirmation is not None
    assert typo.pending_confirmation.subject == "купить корм собаке"
    assert repository.read_document().commitments == before.commitments

    ordinary_provider = LocalProfileProvider(response_text="Звучит как понятное дело.")
    _, _, ordinary_application = _application(tmp_path / "bare", ordinary_provider)
    ordinary_repository = ordinary_application._conversation._conversation.memory_retriever.memory_store
    ordinary_before = ordinary_repository.read_document()
    bare = ordinary_application.send_message("купить корм собаке", project_id=PROJECT_ID)

    assert bare.pending_confirmation is None
    assert bare.assistant_message.content == "Звучит как понятное дело."
    assert ordinary_repository.read_document().commitments == ordinary_before.commitments


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
    assert initial.proactive_reason_code == "proactive_disabled"
    assert initial.proactive_reason_label == "Инициативность выключена"
    assert initial.emergency_stop_engaged is False
    assert initial.model_available is True

    application.emergency_stop("ui_test")
    provider.available = False
    stopped = application.status()

    assert stopped.proactive_enabled is False
    assert stopped.emergency_stop_engaged is True
    assert stopped.model_available is False
    assert stopped.model_availability_code is ModelAvailabilityCode.PROVIDER_UNAVAILABLE
    assert stopped.proactive_reason_code == "emergency_stop_engaged"
    assert stopped.safety_label != stopped.proactive_label
    assert not any(
        forbidden in stopped.model_dump_json().casefold()
        for forbidden in ("sqlite", "local-data", ".json", "lock", "path")
    )

    resumed = application.resume_autonomy()
    assert resumed.emergency_stop_engaged is False
    assert application.status().proactive_enabled is False


def test_application_resume_restores_eligible_background_daemon(tmp_path):
    from backend.temporal.proactive import ProactivePolicy, ProactivePolicyStore

    root, _, application = _application(tmp_path)
    ProactivePolicyStore(
        root / "local-data" / "config" / "proactive-policy.json"
    ).save(ProactivePolicy(
        enabled=True, proactive_level=1, allow_commitment_reminders=True,
        runtime_mode="background",
    ))
    launches = []
    application._status._daemon._launcher = lambda *args, **kwargs: launches.append((args, kwargs))

    application.emergency_stop("test")
    resumed = application.resume_autonomy()

    assert resumed.emergency_stop_engaged is False
    assert len(launches) == 1


def test_visual_resolver_hides_paths_and_checks_canonical_integrity(tmp_path):
    root, _, application = _application(tmp_path)

    assets = application.canonical_visual_assets()
    assert len(assets) == 1
    assert all("path" not in item.model_dump() for item in assets)
    resolved = application.resolve_visual_asset(assets[0].asset_id)
    assert resolved.asset == assets[0]
    assert resolved.asset.media_type == "image/png"
    assert resolved.content.startswith(b"\x89PNG\r\n\x1a\n")

    manifest_asset = root / "identity" / "visual_assets" / "masha-home-2026-07-01.png"
    manifest_asset.write_bytes(manifest_asset.read_bytes() + b"tampered")
    with pytest.raises(ApplicationBoundaryError) as error:
        application.resolve_visual_asset("masha_home_2026_07_01")
    assert error.value.code is ApplicationErrorCode.VISUAL_ASSET_INTEGRITY_FAILED


def test_read_views_and_ordinary_chat_do_not_mutate_long_term_memory(tmp_path):
    root, _, application = _application(tmp_path)
    repository = MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    before = repository.read_document()

    application.model_profiles()
    workbench = application.workbench()
    application.canonical_visual_assets()
    application.status()
    application.send_message("Обычный разговор", project_id=PROJECT_ID)

    assert repository.read_document() == before
    assert workbench.profiles
    assert all("grant_id" not in item.model_dump_json() for item in workbench.grants)
    assert "local-data" not in workbench.model_dump_json()


def test_workbench_model_selection_is_manual_and_keeps_other_domains_unchanged(tmp_path):
    root, _, application = _application(tmp_path)
    identity_path = root / "identity" / "masha.identity.json"
    memory_path = root / "local-data" / "memory" / "masha.sqlite3"
    history_path = root / "local-data" / "conversations" / "history.json"
    before = {
        "identity": identity_path.read_bytes(),
        "memory": hashlib.sha256(memory_path.read_bytes()).digest(),
        "history_exists": history_path.exists(),
    }

    workbench = application.workbench()
    fast = next(item for item in workbench.profiles if item.profile_id == "fast")
    result = application.use_model(fast.profile_id)

    assert fast.active is False
    assert fast.available is True
    assert result.status is ModelSwitchStatus.APPLIED
    assert application.workbench().profiles[1].active is True
    assert identity_path.read_bytes() == before["identity"]
    assert hashlib.sha256(memory_path.read_bytes()).digest() == before["memory"]
    assert history_path.exists() is before["history_exists"]


def test_workbench_filters_empty_profile_projection_before_renderer_boundary(tmp_path):
    from backend.llm.model_profiles import ModelProfileStore

    root = _isolated_root(tmp_path)
    store = ModelProfileStore(root / "local-data" / "config" / "models.json")
    data = json.loads(store.path.read_text(encoding="utf-8"))
    data["profiles"].append({
        "profile_id": "empty-option",
        "display_name": "",
        "provider_id": "ollama-local",
        "model_id": "",
        "timeout_seconds": 30,
        "think": False,
        "capabilities": ["text"],
        "enabled": False,
        "description": "",
    })
    store.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    application = build_masha_application(
        project_root=root,
        router=ModelRouter([LocalProfileProvider()]),
    )

    profiles = application.workbench().profiles

    assert profiles
    assert all(item.profile_id.strip() and item.display_name.strip() and item.model_id.strip() for item in profiles)
    assert all(item.profile_id != "empty-option" for item in profiles)


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
    assert "commitment_done" not in by_id



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


def test_fact_confirmation_is_projected_and_survives_restart(tmp_path):
    root, _, application = _application(tmp_path)
    proposed = application.send_message(
        "Запомни, что мой тестовый напиток — какао",
        project_id=PROJECT_ID,
    )

    assert proposed.pending_confirmation is not None
    assert proposed.pending_confirmation.confirmation_type == "memory_create"
    resolved = application.resolve_confirmation(
        conversation_id=proposed.conversation_id,
        proposal_id=proposed.pending_confirmation.proposal_id,
        decision="confirm",
        project_id=PROJECT_ID,
    )
    assert resolved.status.value == "confirmed"

    restarted = build_masha_application(
        project_root=root,
        router=ModelRouter([LocalProfileProvider()]),
    )
    read = restarted.send_message("Что ты обо мне помнишь?", project_id=PROJECT_ID)
    assert "какао" in read.assistant_message.content


def test_shared_history_contains_only_real_moments_and_threads(tmp_path):
    _, _, application = _application(tmp_path)
    empty = application.shared_continuity()
    assert empty.confirmed_memories == ()
    assert empty.moments == ()

    proposed = application.send_message(
        "Маша, запомни как часть нашей истории, что мы впервые проверили живой Дом",
        project_id=PROJECT_ID,
    )
    application.resolve_confirmation(
        conversation_id=proposed.conversation_id,
        proposal_id=proposed.pending_confirmation.proposal_id,
        decision="confirm",
        project_id=PROJECT_ID,
    )
    view = application.shared_continuity()
    assert [item.text for item in view.moments] == ["мы впервые проверили живой Дом"]
    assert view.confirmed_memories == ()


def test_workbench_installs_existing_supported_skill_contract_and_survives_restart(tmp_path):
    root, _, application = _application(tmp_path)
    source = root / "skills" / "project_observer"
    # The bundled copy is already discoverable, so isolate the selected package
    # from the registry's bundled root as a normal user package source.
    package = tmp_path / "observer-package"
    shutil.copytree(source, package)
    shutil.rmtree(source)

    preview = application.propose_skill_install(str(package))
    assert preview.skill_id == "project_observer"
    assert preview.runtime_supported is True
    result = application.resolve_skill_install(preview.proposal_id, "confirm")
    assert result.status == "confirmed"
    assert any(item.skill_id == "project_observer" for item in result.workbench.skills)

    restarted = build_masha_application(
        project_root=root,
        router=ModelRouter([LocalProfileProvider()]),
    )
    assert any(item.skill_id == "project_observer" for item in restarted.workbench().skills)


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

def test_special_evening_is_explicit_session_only_and_expires_at_day(tmp_path):
    root, _, application = _application(tmp_path)
    repository = MemorySqliteRepository(
        root / "local-data" / "memory" / "masha.sqlite3"
    )
    before = repository.read_document()

    current_time = [
        datetime(
            2026,
            8,
            19,
            22,
            0,
            tzinfo=timezone(timedelta(hours=3)),
        )
    ]

    application._home_snapshot._clock = lambda: current_time[0]

    session = application.open_home_session()
    session.opened()

    special = session.enter_special_evening()

    assert special is not None
    assert (
        special.presentation.home_moment
        is HomeMoment.SPECIAL_EVENING
    )

    current_time[0] = datetime(
        2026,
        8,
        20,
        9,
        0,
        tzinfo=timezone(timedelta(hours=3)),
    )

    daytime = session.observe_time()

    assert (
        daytime.presentation.home_moment
        is HomeMoment.ORDINARY
    )

    assert session.enter_special_evening() is None
    assert repository.read_document() == before

def test_home_session_model_change_updates_only_execution_overlay(tmp_path):
    _, _, application = _application(tmp_path)
    session = application.open_home_session()
    opened = session.opened()
    before = opened.presentation
    switched = application.use_model("fast")

    changed = session.model_changed(
        active_model=switched.active_profile,
        status=application.status(),
    )

    assert changed.active_model.profile_id == "fast"
    assert changed.presentation.overlays.active_profile_id == "fast"
    assert changed.presentation.presence == before.presence
    assert changed.presentation.surfaces == before.surfaces
    assert changed.presentation.activities == before.activities


def test_agent_runs_are_bounded_read_only_receipts_and_survive_restart(tmp_path):
    root, provider, application = _application(tmp_path)
    repository = MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    before = repository.read_document()
    now = datetime(2026, 8, 12, 7, 30, tzinfo=timezone.utc)
    store = AgentRunStore(root / "local-data" / "runtime" / "agent-runs.json")
    store.save(
        AgentRunReceipt(
            plan_id="plan_ui_slice_a",
            plan_sha256="a" * 64,
            goal="Подготовить локальный отчёт",
            status=AgentRunStatus.COMPLETED,
            started_at=now,
            updated_at=now + timedelta(minutes=2),
            finished_at=now + timedelta(minutes=2),
            steps=(
                AgentStepReceipt(
                    step_id="step_report",
                    title="Собрать проверенные результаты",
                    tool_id="local_report",
                    operation="build",
                    status=AgentStepStatus.VERIFIED,
                    policy_decision=ActionDecision.ALLOW,
                    policy_reason="standing_permission",
                    started_at=now,
                    finished_at=now + timedelta(minutes=2),
                    result_summary="Отчёт подготовлен локально",
                    verification_code="verified",
                ),
            ),
        )
    )

    view = application.agent_runs()

    assert len(view.items) == 1
    assert view.items[0].status == "completed"
    assert view.items[0].status_label == "Завершено и проверено"
    serialized = view.model_dump_json()
    assert "local_report" not in serialized
    assert "standing_permission" not in serialized
    assert "plan_sha256" not in serialized
    assert repository.read_document() == before
    restarted = build_masha_application(project_root=root, router=ModelRouter([provider]))
    assert restarted.agent_runs() == view


def test_proactive_projection_resolves_existing_lifecycle_without_memory_mutation(tmp_path):
    root, provider, application = _application(tmp_path)
    repository = MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    before = repository.read_document()
    now = datetime(2026, 8, 12, 7, 30, tzinfo=timezone.utc)
    event_id = check_in_event_id("ui-slice-a-anchor")
    events = ProactiveEventStore(repository)
    events.create(
        ProactiveEvent(
            event_id=event_id,
            event_type=ProactiveEventType.CHECK_IN,
            source_type="absence",
            source_id="ui-slice-a-anchor",
            created_at=now,
            detected_at=now,
            payload={
                "absence_seconds": 7_200,
                "anchor_created_at": (now - timedelta(hours=2)).isoformat(),
            },
        )
    )
    events.update_state(event_id, ProactiveEventState.CANDIDATE, now)
    interactions = ProactiveInteractionStore(repository)
    interactions.ensure_candidate(
        CheckInCandidate(
            event_id=event_id,
            absence_duration_seconds=7_200,
            last_message_at=now - timedelta(hours=2),
            current_local_time=now,
            proactive_level=2,
        )
    )
    interactions.mark_delivered(event_id, "Миша, я рядом. Как ты?", now)

    view = application.proactive_interactions()

    assert len(view.items) == 1
    assert view.items[0].interaction_type == "check_in"
    assert view.items[0].message == "Миша, я рядом. Как ты?"
    assert view.items[0].allowed_actions == ("acknowledge", "dismiss")
    assert "absence_seconds" not in view.model_dump_json()
    assert repository.read_document() == before

    resolved = application.resolve_proactive(event_id, "dismiss")
    assert resolved.state == "dismissed"
    assert application.proactive_interactions().items == ()
    assert repository.read_document() == before
    restarted = build_masha_application(project_root=root, router=ModelRouter([provider]))
    assert restarted.proactive_interactions().items == ()


def test_memory_and_shared_continuity_projection_is_bounded_read_only_and_restart_safe(tmp_path):
    root, provider, application = _application(tmp_path)
    repository = MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    before = repository.read_document()

    view = application.shared_continuity()

    assert len(view.confirmed_memories) <= 10
    assert len(view.open_threads) <= 8
    assert all(item.memory_type in {"fact", "decision", "episode"} for item in view.confirmed_memories)
    assert not any("memory_schema.json" in item.summary for item in view.open_threads)
    assert not any("Python-модели" in item.summary for item in view.open_threads)
    serialized = view.model_dump_json()
    assert "audit_events" not in serialized
    assert "identity_version" not in serialized
    assert "source_memory_ids" not in serialized
    assert repository.read_document() == before
    restarted = build_masha_application(project_root=root, router=ModelRouter([provider]))
    assert restarted.shared_continuity() == view


def test_empty_reflection_workspace_is_read_only(tmp_path):
    root, provider, application = _application(tmp_path)
    repository = MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    before = repository.read_document()

    workspace = application.reflection_workspace()

    assert workspace.adopted == ()
    assert workspace.pending == ()
    assert workspace.help_offers == ()
    assert repository.read_document() == before
    restarted = build_masha_application(project_root=root, router=ModelRouter([provider]))
    assert restarted.reflection_workspace() == workspace


def test_shared_reflection_requires_explicit_application_decision(tmp_path):
    from backend.memory.reflection import ReflectionScope

    provider = LocalProfileProvider(
        response_text=json.dumps(
            {
                "text": "Наша близость держится на честном споре, а не на постоянном согласии.",
                "meaning": "Конфликт не разрушает близость, если сохраняются тепло и верность.",
                "confidence": 0.82,
                "importance": 0.74,
                "help_offer": None,
            },
            ensure_ascii=False,
        )
    )
    root, provider, application = _application(tmp_path, provider)
    repository = MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    conversation = application._conversation._conversation.history.create()  # noqa: SLF001
    result = application._reflections._reflections.reflect(  # noqa: SLF001
        scope=ReflectionScope.SHARED,
        topic="как мы спорим",
        project_id=PROJECT_ID,
        conversation_id=conversation.id,
        evidence_message_ids=("message-test",),
        conversation_messages=(),
    )

    workspace = application.reflection_workspace()

    assert result.adopted is False
    assert len(workspace.pending) == 1
    candidate = workspace.pending[0]
    before_resolution = repository.read_document()
    assert before_resolution.reflections == []
    resolved = application.resolve_reflection(candidate.candidate_id, "adopt")
    assert resolved.status == "adopted"
    assert len(repository.read_document().reflections) == 1
    assert provider.last_request is not None


def test_honest_help_runs_only_after_explicit_application_acceptance(tmp_path):
    from backend.memory.reflection import ReflectionScope

    provider = LocalProfileProvider(
        response_text=json.dumps(
            {
                "text": "Мне кажется, задачу лучше сначала разложить на проверяемые части.",
                "meaning": "Так легче увидеть ближайший честный шаг.",
                "confidence": 0.84,
                "importance": 0.72,
                "help_offer": {
                    "observation": "Задача пока выглядит слишком большой и смешивает несколько решений.",
                    "offer": "Могу помочь разложить её на три проверяемых шага.",
                    "expected_benefit": "Станет понятен ближайший конкретный ход.",
                    "why_now": "Тема уже поднята в нашем текущем разговоре.",
                    "capability": "conversation",
                },
            },
            ensure_ascii=False,
        )
    )
    root, provider, application = _application(tmp_path, provider)
    repository = MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    conversation = application._conversation._conversation.history.create()  # noqa: SLF001
    application._reflections._reflections.reflect(  # noqa: SLF001
        scope=ReflectionScope.SELF,
        topic="большая задача",
        project_id=PROJECT_ID,
        conversation_id=conversation.id,
        evidence_message_ids=("message-help",),
        conversation_messages=(),
    )
    before_help = repository.read_document()
    workspace = application.reflection_workspace()

    assert len(workspace.help_offers) == 1
    assert application.conversation(conversation.id).messages == ()
    result = application.resolve_honest_help(
        workspace.help_offers[0].candidate_id,
        "accept",
    )

    assert result.status == "delivered"
    assert result.conversation_id == conversation.id
    history = application.conversation(conversation.id).messages
    assert [item.role for item in history] == ["user", "assistant"]
    assert history[0].content == "Давай, помоги."
    assert application.reflection_workspace().help_offers == ()
    after_help = repository.read_document()
    assert after_help.facts == before_help.facts
    assert after_help.decisions == before_help.decisions
    assert after_help.commitments == before_help.commitments
    assert provider.last_request.private_context["task"] == "accepted_honest_help_offer"


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
        "overdue_commitments_count",
        "upcoming_commitments_count",
        "unscheduled_commitments_count",
        "stale_overdue_commitments_count",
        "pending_interactions_count",
        "attention_items",
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


def test_conversation_projection_exposes_full_scrollable_history_and_all_summaries(tmp_path):
    _, _, application = _application(tmp_path)
    turns = []
    for index in range(12):
        turns.append(application.send_message(f"Разговор {index}", project_id=PROJECT_ID))

    first_id = turns[0].conversation_id
    for index in range(10):
        application.send_message(
            f"Продолжение {index}",
            project_id=PROJECT_ID,
            conversation_id=first_id,
        )

    recent = application.recent_conversations()
    assert len(recent) == 12
    assert recent[0].conversation_id == first_id
    assert len(application.conversation(first_id).messages) == 22


def test_commitment_projection_has_explicit_group_and_recency_order(tmp_path):
    _, _, application = _application(tmp_path)
    repository = application._conversation._conversation.memory_retriever.memory_store
    document = repository.read_document()
    template = document.commitments[0]
    now = datetime(2026, 8, 13, 10, 0, tzinfo=timezone.utc)
    rows = [
        template.model_copy(update={"id": "overdue", "text": "Просрочено", "due_at": now - timedelta(minutes=1)}),
        template.model_copy(update={"id": "due-later", "text": "Позже", "due_at": now + timedelta(hours=2)}),
        template.model_copy(update={"id": "due-near", "text": "Ближе", "due_at": now + timedelta(minutes=10)}),
        template.model_copy(update={"text": "Без срока старое", "due_at": None, "created_at": now - timedelta(days=2), "updated_at": now - timedelta(days=2)}),
        template.model_copy(update={"id": "open-new", "text": "Без срока новое", "due_at": None, "created_at": now - timedelta(days=1), "updated_at": now - timedelta(days=1)}),
        template.model_copy(update={"id": "done-old", "text": "Готово старое", "status": CommitmentStatus.COMPLETED, "due_at": None, "completed_at": now - timedelta(days=2), "updated_at": now - timedelta(days=2)}),
        template.model_copy(update={"id": "done-new", "text": "Готово новое", "status": CommitmentStatus.COMPLETED, "due_at": None, "completed_at": now - timedelta(days=1), "updated_at": now - timedelta(days=1)}),
    ]
    repository.replace_document(
        document.model_copy(update={"commitments": rows}),
        action="test_deterministic_projection_order",
    )
    application._commitments._conversation.temporal_engine = TemporalEngine(FixedClock(now))

    assert [item.commitment_id for item in application.commitments().items] == [
        "overdue",
        "due-near",
        "due-later",
        "open-new",
        template.id,
    ]


def test_today_query_accepts_production_utc_z_timestamps(tmp_path):
    _, _, application = _application(tmp_path)
    repository = application._conversation._conversation.memory_retriever.memory_store
    document = repository.read_document()
    now = datetime(2026, 8, 13, 10, 0, tzinfo=timezone.utc)
    commitment = document.commitments[0].model_copy(
        update={"text": "Проверить UTC", "due_at": now + timedelta(hours=1)}
    )
    repository.replace_document(
        document.model_copy(update={"commitments": [commitment]}),
        action="test_utc_z_query",
    )
    engine = TemporalEngine(FixedClock(now))
    application._conversation._conversation.temporal_engine = engine
    application._conversation._conversation.memory_intent_handler.temporal_engine = engine

    result = application.send_message("Что у нас сегодня?", project_id=PROJECT_ID)

    assert result.status is ConversationTurnStatus.COMPLETED
    assert "Проверить UTC" in result.assistant_message.content


def test_proactive_status_explains_second_due_reminder_suppression(tmp_path):
    from backend.temporal.proactive import ProactivePolicy, ProactivePolicyStore

    root, _, application = _application(
        tmp_path,
        LocalProfileProvider(response_text="Миша, это первое напоминание."),
    )
    repository = application._conversation._conversation.memory_retriever.memory_store
    document = repository.read_document()
    template = document.commitments[0]
    now = datetime(2026, 8, 13, 8, 0, tzinfo=timezone.utc)
    first = template.model_copy(update={"text": "Первое дело", "due_at": now - timedelta(minutes=1)})
    second = template.model_copy(update={"id": "commitment_second_due", "text": "Второе дело", "due_at": now + timedelta(minutes=5)})
    repository.replace_document(document.model_copy(update={"commitments": [first, second]}))
    clock = FixedClock(now)
    engine = TemporalEngine(clock)
    conversation = application._conversation._conversation
    conversation.temporal_engine = engine
    conversation.memory_intent_handler.temporal_engine = engine
    application._proactive._clock = clock
    application._proactive._runtime.temporal_engine = engine
    application._proactive._runtime.controlled.temporal_engine = engine
    ProactivePolicyStore(root / "local-data" / "config" / "proactive-policy.json").save(
        ProactivePolicy(
            enabled=True,
            proactive_level=1,
            allow_commitment_reminders=True,
            maximum_reminders=1,
            daily_message_limit=1,
            cooldown_seconds=0,
            runtime_mode="background",
            cycle_interval_seconds=10,
        )
    )

    delivered = application.refresh_proactive_interactions()
    assert len(delivered.items) == 1
    application.resolve_proactive(delivered.items[0].interaction_id, "acknowledge")
    clock.value = now + timedelta(minutes=6)
    second_projection = application.refresh_proactive_interactions()

    assert second_projection.items == ()
    status = application.status()
    reasons = [item.reason_code for item in status.proactive_diagnostics]
    assert "daily_limit" in reasons
    suppressed = next(item for item in status.proactive_diagnostics if item.reason_code == "daily_limit")
    assert suppressed.state == "suppressed"
    assert suppressed.reason_label == "Дневной лимит сообщений исчерпан"


def test_opted_in_natural_two_minute_reminder_reaches_home_once(tmp_path):
    from backend.temporal.proactive import ProactivePolicy, ProactivePolicyStore

    root, _, application = _application(
        tmp_path,
        LocalProfileProvider(response_text="Миша, пора поставить чайник."),
    )
    now = datetime(2026, 8, 13, 8, 0, tzinfo=timezone.utc)
    clock = FixedClock(now)
    engine = TemporalEngine(clock)
    conversation = application._conversation._conversation
    conversation.temporal_engine = engine
    conversation.memory_intent_handler.temporal_engine = engine
    application._proactive._clock = clock
    application._proactive._runtime.temporal_engine = engine
    application._proactive._runtime.controlled.temporal_engine = engine
    policy_store = ProactivePolicyStore(
        root / "local-data" / "config" / "proactive-policy.json"
    )
    policy_store.save(
        ProactivePolicy(
            enabled=True,
            proactive_level=1,
            allow_commitment_reminders=True,
            maximum_reminders=1,
            daily_message_limit=1,
            cooldown_seconds=0,
            runtime_mode="background",
            cycle_interval_seconds=10,
        )
    )

    proposed = application.send_message(
        "Маша, напомни, чтобы я поставил чайник через 2 минуты",
        project_id=PROJECT_ID,
    )
    assert proposed.pending_confirmation.subject == "чтобы я поставил чайник"
    assert proposed.pending_confirmation.due_at == now + timedelta(minutes=2)
    application.resolve_confirmation(
        conversation_id=proposed.conversation_id,
        proposal_id=proposed.pending_confirmation.proposal_id,
        decision="confirm",
        project_id=PROJECT_ID,
    )
    commitment = next(
        item
        for item in application._conversation._conversation.memory_retriever.memory_store.read_document().commitments
        if "чайник" in item.text
    )
    assert commitment.reminder_delivery_mode.value == "explicit_user_reminder"
    clock.value = now + timedelta(minutes=2, seconds=1)

    first = application.refresh_proactive_interactions()
    second = application.refresh_proactive_interactions()

    assert len(first.items) == len(second.items) == 1
    assert first.items[0].interaction_id == second.items[0].interaction_id
    assert first.items[0].message == "Миша, пора поставить чайник."
    assert len(application._proactive._store.list()) == 1
    status = application.status()
    assert status.proactive_enabled is True
    assert status.proactive_level == 1
    assert status.runtime_mode == "background"
    assert status.commitment_reminders_allowed is True


def test_home_attention_projects_and_resolves_only_its_visible_proactive_item(tmp_path):
    from backend.temporal.proactive import ProactiveDecisionEngine
    from backend.temporal.temporal_models import ProactiveDecision
    from backend.temporal.temporal_runtime import TemporalRuntime

    _, _, application = _application(tmp_path)
    repository = application._conversation._conversation.memory_retriever.memory_store
    now = datetime(2026, 8, 13, 8, 0, tzinfo=timezone.utc)
    clock = FixedClock(now)
    engine = TemporalEngine(clock)
    document = repository.read_document()
    commitment = document.commitments[0].model_copy(update={"due_at": now - timedelta(minutes=1)})
    repository.replace_document(document.model_copy(update={"commitments": [commitment]}))
    application._conversation._conversation.temporal_engine = engine
    application._conversation._conversation.memory_intent_handler.temporal_engine = engine
    application._proactive._clock = clock
    event = TemporalRuntime(repository, engine).recover().events[0]
    candidate = ProactiveDecisionEngine.candidate(
        event,
        commitment_text=commitment.text,
        temporal_context=engine.context(None),
        decision=ProactiveDecision.REMIND,
        generated_at=now,
    )
    application._proactive._store.ensure_candidate(candidate)
    application._proactive._store.mark_delivered(event.event_id, "Пора поставить чайник.", now)

    before = application._proactive._store.list()
    attention = application.home_attention()
    item = next(item for item in attention.attention_items if item.kind == "proactive_interaction")
    assert item.interaction_id == event.event_id
    assert item.allowed_actions == ("acknowledge", "dismiss")
    assert all(
        row.interaction_id is None and row.allowed_actions == ()
        for row in attention.attention_items if row.kind != "proactive_interaction"
    )
    assert application.home_attention().model_dump() == attention.model_dump()
    assert application._proactive._store.list() == before

    application.resolve_proactive(item.interaction_id, "acknowledge")
    refreshed = application.home_attention()
    assert refreshed.pending_interactions_count == 0
    assert not any(row.kind == "proactive_interaction" for row in refreshed.attention_items)


def test_open_continuity_threads_are_newest_first_and_restart_safe(tmp_path):
    root, provider, application = _application(tmp_path)
    for text in ("первая открытая тема", "вторая открытая тема"):
        proposed = application.send_message(
            f"Оставь это как открытую нить: {text}",
            project_id=PROJECT_ID,
        )
        application.resolve_confirmation(
            conversation_id=proposed.conversation_id,
            proposal_id=proposed.pending_confirmation.proposal_id,
            decision="confirm",
            project_id=PROJECT_ID,
        )

    assert [item.summary for item in application.shared_continuity().open_threads[:2]] == [
        "вторая открытая тема",
        "первая открытая тема",
    ]
    restarted = build_masha_application(project_root=root, router=ModelRouter([provider]))
    assert restarted.shared_continuity().open_threads == application.shared_continuity().open_threads


def test_natural_resolve_routes_to_existing_thread_and_ambiguous_match_stays_open(tmp_path):
    _, _, application = _application(tmp_path)
    created = []
    for summary in ("мяу и вечерний корм", "мяу и поездка к врачу"):
        proposed = application.send_message(
            f"Оставь это как открытую нить: {summary}", project_id=PROJECT_ID
        )
        application.resolve_confirmation(
            conversation_id=proposed.conversation_id,
            proposal_id=proposed.pending_confirmation.proposal_id,
            decision="confirm",
            project_id=PROJECT_ID,
        )
        created.append(summary)

    ambiguous = application.send_message("удали нить про мяу", project_id=PROJECT_ID)
    assert ambiguous.pending_confirmation is None
    assert "несколько похожих нитей" in ambiguous.assistant_message.content
    assert [item.summary for item in application.shared_continuity().open_threads] == list(reversed(created))

    unknown = application.send_message("убери нить про несуществующий маяк", project_id=PROJECT_ID)
    assert unknown.pending_confirmation is None
    assert "Не нашла такую открытую нить" in unknown.assistant_message.content

    exact = application.send_message("заверши нить про вечерний корм", project_id=PROJECT_ID)
    assert exact.pending_confirmation is not None
    assert exact.pending_confirmation.subject == "мяу и вечерний корм"
    application.resolve_confirmation(
        conversation_id=exact.conversation_id,
        proposal_id=exact.pending_confirmation.proposal_id,
        decision="confirm",
        project_id=PROJECT_ID,
    )
    assert [item.summary for item in application.shared_continuity().open_threads] == [
        "мяу и поездка к врачу"
    ]


@pytest.mark.parametrize(
    ("decision", "expected", "still_open"),
    (("reject", "Нет, не закрыла", True), ("confirm", "Да, закрыла", False)),
)
def test_continuity_confirmation_outcome_owns_immediate_follow_up_truth(
    tmp_path,
    decision,
    expected,
    still_open,
):
    _, provider, application = _application(tmp_path)
    created = application.send_message(
        "Оставь это как открытую нить: выбор модели для длинных разговоров",
        project_id=PROJECT_ID,
    )
    application.resolve_confirmation(
        conversation_id=created.conversation_id,
        proposal_id=created.pending_confirmation.proposal_id,
        decision="confirm",
        project_id=PROJECT_ID,
    )
    proposed = application.send_message(
        "Маша, закрой нить про выбор модели для длинных разговоров",
        project_id=PROJECT_ID,
        conversation_id=created.conversation_id,
    )
    application.resolve_confirmation(
        conversation_id=created.conversation_id,
        proposal_id=proposed.pending_confirmation.proposal_id,
        decision=decision,
        project_id=PROJECT_ID,
    )

    result = application.send_message(
        "Ну всё, значит закрыла",
        project_id=PROJECT_ID,
        conversation_id=created.conversation_id,
    )

    assert expected in result.assistant_message.content
    assert provider.last_request is None
    assert (
        "выбор модели для длинных разговоров"
        in [item.summary for item in application.shared_continuity().open_threads]
    ) is still_open


def test_ordinary_close_discussion_after_rejection_remains_a_model_turn(tmp_path):
    provider = LocalProfileProvider(response_text="Давай сначала обсудим, готова ли тема завершиться.")
    _, _, application = _application(tmp_path, provider)
    created = application.send_message(
        "Оставь это как открытую нить: архитектура разговора",
        project_id=PROJECT_ID,
    )
    application.resolve_confirmation(
        conversation_id=created.conversation_id,
        proposal_id=created.pending_confirmation.proposal_id,
        decision="confirm",
        project_id=PROJECT_ID,
    )
    proposed = application.send_message(
        "закрой нить про архитектуру разговора",
        project_id=PROJECT_ID,
        conversation_id=created.conversation_id,
    )
    application.resolve_confirmation(
        conversation_id=created.conversation_id,
        proposal_id=proposed.pending_confirmation.proposal_id,
        decision="reject",
        project_id=PROJECT_ID,
    )

    result = application.send_message(
        "может, эту тему стоит закрыть",
        project_id=PROJECT_ID,
        conversation_id=created.conversation_id,
    )

    assert result.assistant_message.content == provider.response_text
    assert provider.last_request is not None
    assert application.shared_continuity().open_threads[0].summary == "архитектура разговора"


def test_live_background_daemon_does_not_prevent_home_session_open(tmp_path):
    from backend.temporal.proactive import ProactivePolicy, ProactivePolicyStore

    root, _, application = _application(tmp_path)
    ProactivePolicyStore(root / "local-data" / "config" / "proactive-policy.json").save(
        ProactivePolicy(runtime_mode="manual", cycle_interval_seconds=10)
    )
    daemon = application._status._daemon
    child = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "backend.temporal.proactive_daemon",
            "--project-root",
            str(root),
        ],
        cwd=PROJECT_ROOT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        deadline = time.monotonic() + 10
        while not daemon.is_running() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert daemon.is_running() is True

        opened = application.open_home_session().opened()

        assert opened.status.daemon_running is True
        assert child.poll() is None
    finally:
        daemon.request_stop()
        child.wait(timeout=10)
    assert daemon.is_running() is False


def test_home_start_degrades_when_daemon_probe_is_unknown(tmp_path):
    _, _, application = _application(tmp_path)
    daemon = application._status._daemon
    daemon.lock_path.write_text("987654", encoding="ascii")
    daemon._process_probe = lambda _pid: (_ for _ in ()).throw(
        RuntimeError("unexpected probe failure")
    )

    report = application._status._health.inspect()
    opened = application.open_home_session().opened()

    daemon_check = next(item for item in report.checks if item.name == "daemon")
    assert daemon_check.status == "warning"
    assert "состояние неизвестно" in daemon_check.detail
    assert opened.status.runtime_status == "degraded"
    assert opened.status.daemon_running is False


def test_infinitive_continuity_resolve_keeps_typed_clarification_context(tmp_path):
    _, provider, application = _application(tmp_path)
    for summary in ("мяу и вечерний корм", "мяу и поездка к врачу"):
        proposed = application.send_message(
            f"Оставь это как открытую нить: {summary}", project_id=PROJECT_ID
        )
        application.resolve_confirmation(
            conversation_id=proposed.conversation_id,
            proposal_id=proposed.pending_confirmation.proposal_id,
            decision="confirm",
            project_id=PROJECT_ID,
        )

    ambiguous = application.send_message("Маша, удалить нить мяу", project_id=PROJECT_ID)
    assert ambiguous.pending_confirmation is None
    assert "несколько похожих нитей" in ambiguous.assistant_message.content
    assert provider.last_request is None

    still_ambiguous = application.send_message(
        "мяу",
        project_id=PROJECT_ID,
        conversation_id=ambiguous.conversation_id,
    )
    assert still_ambiguous.pending_confirmation is None
    assert "несколько похожих нитей" in still_ambiguous.assistant_message.content

    refined = application.send_message(
        "та, где про вечер",
        project_id=PROJECT_ID,
        conversation_id=still_ambiguous.conversation_id,
    )
    assert refined.pending_confirmation is not None
    assert refined.pending_confirmation.subject == "мяу и вечерний корм"
    assert provider.last_request is None
    assert len(application.shared_continuity().open_threads) == 2

    application.resolve_confirmation(
        conversation_id=refined.conversation_id,
        proposal_id=refined.pending_confirmation.proposal_id,
        decision="confirm",
        project_id=PROJECT_ID,
    )
    assert [item.summary for item in application.shared_continuity().open_threads] == [
        "мяу и поездка к врачу"
    ]


def test_unrelated_explicit_action_clears_continuity_clarification(tmp_path):
    _, provider, application = _application(tmp_path)
    conversation_id = None
    for summary in ("мяу вечером", "мяу утром"):
        proposed = application.send_message(
            f"Оставь это как открытую нить: {summary}",
            project_id=PROJECT_ID,
            conversation_id=conversation_id,
        )
        conversation_id = proposed.conversation_id
        application.resolve_confirmation(
            conversation_id=conversation_id,
            proposal_id=proposed.pending_confirmation.proposal_id,
            decision="confirm",
            project_id=PROJECT_ID,
        )

    ambiguous = application.send_message(
        "удалить нить мяу",
        project_id=PROJECT_ID,
        conversation_id=conversation_id,
    )
    assert "несколько похожих нитей" in ambiguous.assistant_message.content

    commitment = application.send_message(
        "Добавь дело купить чай",
        project_id=PROJECT_ID,
        conversation_id=conversation_id,
    )
    application.resolve_confirmation(
        conversation_id=conversation_id,
        proposal_id=commitment.pending_confirmation.proposal_id,
        decision="reject",
        project_id=PROJECT_ID,
    )
    ordinary = application.send_message(
        "вечером",
        project_id=PROJECT_ID,
        conversation_id=conversation_id,
    )
    assert ordinary.pending_confirmation is None
    assert ordinary.assistant_message.content == provider.response_text


def test_resumed_continuity_context_keeps_deictic_follow_up_on_original_thread(tmp_path):
    _, _, application = _application(
        tmp_path, LocalProfileProvider(response_text="Давай спокойно продолжим эту тему.")
    )
    proposed = application.send_message(
        "Оставь это как открытую нить: какую модель использовать для длинных разговоров",
        project_id=PROJECT_ID,
    )
    application.resolve_confirmation(
        conversation_id=proposed.conversation_id,
        proposal_id=proposed.pending_confirmation.proposal_id,
        decision="confirm",
        project_id=PROJECT_ID,
    )
    original = application.shared_continuity().open_threads[0]

    resumed = application.continue_continuity_thread(
        original.thread_id,
        conversation_id=None,
        project_id=PROJECT_ID,
    )
    kept_open = application.send_message(
        "Да, эту тему пока оставляем открытой",
        project_id=PROJECT_ID,
        conversation_id=resumed.conversation_id,
    )

    assert kept_open.pending_confirmation is None
    assert "оставляем эту тему открытой" in kept_open.assistant_message.content
    assert application.shared_continuity().open_threads == (original,)

    resolve = application.send_message(
        "С этой темой закончили",
        project_id=PROJECT_ID,
        conversation_id=resumed.conversation_id,
    )
    assert resolve.pending_confirmation is not None
    assert resolve.pending_confirmation.subject == original.summary
    application.resolve_confirmation(
        conversation_id=resolve.conversation_id,
        proposal_id=resolve.pending_confirmation.proposal_id,
        decision="confirm",
        project_id=PROJECT_ID,
    )
    assert application.shared_continuity().open_threads == ()


def test_generic_continuity_reference_cannot_become_stored_follow_up(tmp_path):
    _, _, application = _application(tmp_path)

    result = application.send_message("Оставь эту тему", project_id=PROJECT_ID)

    assert result.pending_confirmation is None
    assert "Какую именно тему" in result.assistant_message.content
    assert application.shared_continuity().open_threads == ()


def test_human_catalogs_do_not_replace_machine_codes():
    assert error_label(ApplicationErrorCode.MODEL_UNAVAILABLE) == "Локальная модель недоступна"
    assert proactive_reason_label("quiet_hours") == "Сейчас тихие часы"
    assert proactive_reason_label("new_future_reason") == "Причина пока не переведена"
    assert ApplicationErrorCode.MODEL_UNAVAILABLE.value == "MODEL_UNAVAILABLE"

def test_special_evening_personal_sentence_reaches_model_instead_of_shelf_router(tmp_path):
    _, provider, application = _application(tmp_path)
    phrase = (
        "Маш, всё, дела на сегодня закончились. "
        "Иди сюда, хочу просто немного побыть с тобой."
    )

    result = application.send_message(
        phrase,
        project_id=PROJECT_ID,
        home_moment="special_evening",
    )

    assert result.status is ConversationTurnStatus.COMPLETED
    assert result.assistant_message is not None
    assert result.assistant_message.content == provider.response_text
    conversation_requests = [
        request
        for request in provider.requests
        if request.private_context.get("home_moment") == "special_evening"
    ]

    assert conversation_requests
    conversation_request = conversation_requests[-1]
    assert "РЕЖИМ «ВДВОЁМ»" in (
        conversation_request.private_context["home_moment_contract"]
    )

def test_selected_continuity_thread_is_context_not_synthetic_turn(tmp_path):
    _, provider, application = _application(tmp_path)

    first = application.send_message("Привет, Маш.", project_id=PROJECT_ID)
    conversation_id = first.conversation_id

    handler = application._conversation._conversation.memory_intent_handler
    assert handler is not None
    continuity = handler.shared_continuity
    assert continuity is not None

    proposal = continuity.propose_open_thread(
        handler.proposal_store,
        text="Обсудить нашу будущую поездку к морю",
        conversation_id=conversation_id,
        reason_to_return="Вернуться к выбору места и времени",
    )
    continuity.confirm_proposal(proposal, handler.proposal_store)

    thread = next(
        item
        for item in application.shared_continuity().open_threads
        if item.summary == "Обсудить нашу будущую поездку к морю"
    )

    requests_before = len(provider.requests)
    messages_before = len(application.conversation(conversation_id).messages)

    selected = application.activate_continuity_thread(
        thread.thread_id,
        conversation_id=conversation_id,
    )

    assert selected.thread_id == thread.thread_id
    assert len(provider.requests) == requests_before
    assert len(application.conversation(conversation_id).messages) == messages_before

    result = application.send_message(
        "Я бы начал с места, где вечером можно просто гулять у воды.",
        project_id=PROJECT_ID,
        conversation_id=conversation_id,
    )
    assert result.status is ConversationTurnStatus.COMPLETED

    conversation_requests = [
        request
        for request in provider.requests
        if request.private_context.get("active_continuity")
    ]
    assert conversation_requests
    active = conversation_requests[-1].private_context["active_continuity"]
    assert active["summary"] == "Обсудить нашу будущую поездку к морю"
    assert active["reason_to_return"] == "Вернуться к выбору места и времени"

    application.clear_continuity_thread(conversation_id=conversation_id)
    assert application.active_continuity_thread(conversation_id=conversation_id) is None



def test_special_evening_boundary_pause_is_session_only_and_manual_closeness_resumes(tmp_path):
    root, _, application = _application(tmp_path)
    current_time = [datetime(2026, 8, 28, 20, 0, tzinfo=timezone.utc)]
    application._home_snapshot._clock = lambda: current_time[0]

    repository = MemorySqliteRepository(
        root / "local-data" / "memory" / "masha.sqlite3"
    )
    before = repository.read_document()

    session = application.open_home_session()
    session.opened()
    assert session.enter_special_evening() is not None
    assert session.set_special_proximity(HomeProximity.NEAR) is not None

    paused = session.pause_special_evening_closeness()
    assert paused is not None
    assert paused.presentation.home_proximity is HomeProximity.WIDE
    assert session.special_evening_boundary_paused is True

    session.user_sent()
    assert session.special_evening_boundary_paused is True

    resumed = session.set_special_proximity(HomeProximity.CLOSE)
    assert resumed is not None
    assert resumed.presentation.home_proximity is HomeProximity.CLOSE
    assert session.special_evening_boundary_paused is False

    assert repository.read_document() == before


def test_special_evening_model_proximity_hint_is_one_step_home_owned_and_pause_safe(tmp_path):
    _, _, application = _application(tmp_path)
    current_time = [datetime(2026, 8, 28, 20, 0, tzinfo=timezone.utc)]
    application._home_snapshot._clock = lambda: current_time[0]

    session = application.open_home_session()
    session.opened()

    # Ordinary mode ignores model proximity hints.
    assert session.apply_special_proximity_suggestion("closer") is None
    assert session.home_proximity is HomeProximity.WIDE

    assert session.enter_special_evening() is not None

    first = session.apply_special_proximity_suggestion("closer")
    assert first is not None
    assert first.presentation.home_proximity is HomeProximity.CLOSE

    second = session.apply_special_proximity_suggestion("closer")
    assert second is not None
    assert second.presentation.home_proximity is HomeProximity.NEAR

    # Never jump beyond an edge.
    assert session.apply_special_proximity_suggestion("closer") is None
    assert session.home_proximity is HomeProximity.NEAR

    back = session.apply_special_proximity_suggestion("farther")
    assert back is not None
    assert back.presentation.home_proximity is HomeProximity.CLOSE

    # Step 2 boundary remains absolute for model-origin hints.
    assert session.pause_special_evening_closeness() is not None
    assert session.special_evening_boundary_paused is True
    assert session.home_proximity is HomeProximity.WIDE
    assert session.apply_special_proximity_suggestion("closer") is None
    assert session.home_proximity is HomeProximity.WIDE
    assert session.special_evening_boundary_paused is True

    # Explicit manual UI closeness is still the re-entry authority.
    assert session.set_special_proximity(HomeProximity.CLOSE) is not None
    assert session.special_evening_boundary_paused is False
    resumed = session.apply_special_proximity_suggestion("closer")
    assert resumed is not None
    assert resumed.presentation.home_proximity is HomeProximity.NEAR
