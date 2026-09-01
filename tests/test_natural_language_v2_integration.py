from __future__ import annotations

import shutil
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.application import ConversationTurnStatus, build_masha_application
from backend.llm.fake_provider import FakeProvider
from backend.llm.model_router import ModelRouter
from backend.llm.model_models import ModelCapabilities
from backend.memory.sqlite_repository import MemorySqliteRepository
from backend.temporal.temporal_engine import FixedClock
from backend.conversation.resolution_coordinator import ResolvedCapabilityAdapterRegistry
from backend.conversation.memory_intent import ProposalStatus
from backend.application.resolved_capabilities import (
    CalendarDeleteHandoffAdapter,
    CalendarUpdateHandoffAdapter,
    GoogleDriveReadHandoffAdapter,
    WebSearchHandoffAdapter,
    YandexMailDeleteHandoffAdapter,
    YandexMailMoveHandoffAdapter,
)
from backend.application.resolved_capabilities import CalendarReadHandoffAdapter
from backend.connectors.google_calendar.reader import CalendarReadOutcome
from backend.connectors.google_drive.reader import DriveFileCandidate, DriveReadOutcome
from backend.connectors.yandex_mail.models import (
    MailMessageContent,
    MailMessageSummary,
    MailOutcome,
    ResolvedMailRequest,
)
from backend.external_observation.models import (
    ExternalObservation,
    FreshnessRequirement,
    FreshnessStatus,
    InvocationAuthority,
    ObservationRequest,
    ObservationStatus,
    SearchEvidence,
    SourceTime,
)


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


class SequencedSemanticProvider(LocalProvider):
    """A local-model stand-in that keeps fresh and follow-up semantics distinct."""

    def __init__(self, semantic_responses: list[dict], conversation_text="Обычный разговор."):
        super().__init__(conversation_text)
        self.capabilities = ModelCapabilities(structured_output=True)
        self._semantic_responses = list(semantic_responses)
        self._conversation_text = conversation_text

    def generate(self, request):
        if request.required_capabilities.structured_output:
            assert self._semantic_responses
            self.response_text = json.dumps(
                self._semantic_responses.pop(0), ensure_ascii=False,
            )
        else:
            self.response_text = self._conversation_text
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
        "action_request_evidence": {"evidence_text": "Запиши"},
        "operation_selection_evidence": {"operation_id": None, "evidence_text": None},
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

    assert first.assistant_message.content == (
        "Занятие — поставить в календарь или просто напомнить в 12:00?"
    )
    assert first_diagnostic.dialogue_state.last_decision.semantic_command_status == "accepted"
    assert first_diagnostic.dialogue_state.last_decision.proposed_semantic_command is not None
    context_summary = first_diagnostic.dialogue_state.last_decision.turn_context
    assert context_summary is not None
    assert context_summary.local_date == "2026-08-28"
    assert context_summary.recent_turn_count == 0
    assert context_summary.capability_count > 0
    assert context_summary.active_continuity_present is False
    assert "Bounded Home turn context" in provider.requests[0].messages[0].content
    assert second.pending_confirmation is not None
    assert second.pending_confirmation.confirmation_type == "google_calendar_create"
    assert "12:00–13:00" in second.assistant_message.content
    assert second_diagnostic.dialogue_state.active_flow_id is None
    assert second_diagnostic.application_handoff_type == "google_calendar.event.create"
    assert len(provider.requests) == model_calls_after_first
    receipts = conversation.google_calendar_create_service.writer.receipt_store._items
    assert {item.status for item in receipts.values()} == {"proposed"}
    assert all(item.confirmed_at is None for item in receipts.values())


def _calendar_semantics(*, subject: str | None) -> dict:
    slots = [
        {"name": "date", "evidence_text": "завтра"},
        {"name": "time", "evidence_text": "10 утра"},
    ]
    if subject is not None:
        slots.insert(0, {"name": "subject", "evidence_text": subject})
    return {
        "kind": "supported_action",
        "candidate_operation_ids": ["google_calendar.event.create"],
        "nearby_operation_ids": [],
        "extracted_slots": slots,
        "unresolved_referents": [],
        "ambiguity_hint": "none" if subject is not None else "slot",
        "action_request_evidence": {"evidence_text": "запиши"},
        "operation_selection_evidence": {
            "operation_id": "google_calendar.event.create",
            "evidence_text": "в календарь",
        },
    }


def test_explicit_connector_request_runs_semantics_and_reaches_calendar_preview(tmp_path):
    provider = SequencedSemanticProvider([_calendar_semantics(subject="занятие")])
    _, _, application = _application(tmp_path, provider=provider)

    turn = application.send_message(
        "Привет, запиши занятие на завтра в календарь в 10 утра",
        project_id=PROJECT_ID,
    )
    diagnostic = application.dialogue_diagnostics(turn.conversation_id)

    assert turn.pending_confirmation is not None
    assert turn.pending_confirmation.confirmation_type == "google_calendar_create"
    assert "10:00–11:00" in turn.assistant_message.content
    assert len(provider.requests) == 1
    decision = diagnostic.dialogue_state.last_decision
    assert decision.information_space == "explicit_connector"
    assert decision.semantic_command_status == "accepted"
    assert decision.semantic_validation is not None
    assert decision.semantic_validation.operation_selection.accepted is True
    assert diagnostic.application_handoff_type == "google_calendar.event.create"


def test_presented_mail_context_selects_read_owner_without_exposing_provider_identity(
    tmp_path,
):
    provider = SequencedSemanticProvider([{
        "kind": "supported_action",
        "candidate_operation_ids": ["yandex_mail.read"],
        "nearby_operation_ids": [],
        "extracted_slots": [],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
        "action_request_evidence": {"evidence_text": "Прочитай"},
        "operation_selection_evidence": {
            "operation_id": None,
            "evidence_text": None,
        },
    }], conversation_text="Анна пишет, что занятие перенесли.")
    _, _, application = _application(tmp_path, provider=provider)
    conversation = application._conversation._conversation
    conversation_id = conversation.history.create().id
    summary = MailMessageSummary(
        provider="yandex",
        message_ref="provider-message-42",
        subject="Занятие перенесли",
        sender="Анна",
        received_at=FIXED_NOW,
        size=120,
        has_attachments=False,
    )
    conversation.yandex_mail_service.presented_read_sets.present(
        conversation_id,
        "yandex_mail",
        (summary,),
        entity_kind="письмо",
        presentation_kind="recent",
    )

    class Reader:
        def __init__(self):
            self.calls = []

        def read(self, item):
            self.calls.append(item)
            return MailOutcome(
                "read_completed",
                content=MailMessageContent(
                    summary=item,
                    body="Занятие перенесли на 11:00.",
                ),
                resolved_request=ResolvedMailRequest(
                    subject=item.subject,
                    sender=item.sender,
                ),
            )

    reader = Reader()
    conversation.yandex_mail_service.reader = reader

    turn = application.send_message(
        "Прочитай его",
        project_id=PROJECT_ID,
        conversation_id=conversation_id,
    )
    diagnostic = application.dialogue_diagnostics(conversation_id)

    assert turn.assistant_message.content == "Анна пишет, что занятие перенесли."
    assert reader.calls == [summary]
    assert diagnostic.application_handoff_type == "yandex_mail.read"
    semantic_prompt = provider.requests[0].messages[0].content
    assert "Занятие перенесли" in semantic_prompt
    assert '"reference":"P1"' in semantic_prompt
    assert "provider-message-42" not in semantic_prompt
    assert "provider_id" not in semantic_prompt


def test_natural_mail_request_uses_semantic_view_without_legacy_phrase_grammar(
    tmp_path,
):
    provider = SequencedSemanticProvider([{
        "kind": "supported_action",
        "candidate_operation_ids": ["yandex_mail.read"],
        "nearby_operation_ids": [],
        "extracted_slots": [{
            "name": "view",
            "evidence_text": "что-то новое",
        }],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
        "action_request_evidence": {
            "evidence_text": "не могла бы заглянуть",
        },
        "operation_selection_evidence": {
            "operation_id": None,
            "evidence_text": None,
        },
    }])
    _, _, application = _application(tmp_path, provider=provider)
    conversation = application._conversation._conversation

    class Reader:
        def __init__(self):
            self.searches = []

        def search(self, kind, query):
            self.searches.append((kind, query))
            return MailOutcome(
                "search_completed",
                messages=(MailMessageSummary(
                    provider="yandex",
                    message_ref="private-provider-ref",
                    subject="Новая тема",
                    sender="Анна",
                    received_at=FIXED_NOW,
                    size=100,
                    has_attachments=False,
                ),),
            )

    reader = Reader()
    conversation.yandex_mail_service.reader = reader
    phrase = "Маш, не могла бы заглянуть, появилось ли в почте что-то новое?"

    turn = application.send_message(phrase, project_id=PROJECT_ID)
    diagnostic = application.dialogue_diagnostics(turn.conversation_id)

    assert reader.searches == [("unread", None)]
    assert turn.assistant_message.content == (
        "Нашла в Яндекс Почте:\n1. Новая тема — Анна"
    )
    assert turn.pending_confirmation is None
    assert len(provider.requests) == 1
    assert diagnostic.application_handoff_type == "yandex_mail.read"
    assert diagnostic.response_projection_state == "completed_read"
    assert "private-provider-ref" not in turn.model_dump_json()


def test_subject_follow_up_stays_in_the_same_calendar_flow(tmp_path):
    provider = SequencedSemanticProvider([
        _calendar_semantics(subject=None),
        {
            "relation": "follow_up",
            "selected_operation_id": None,
            "operation_selection_evidence": None,
            "slot_updates": [{
                "name": "subject",
                "evidence_text": "обучение Миши AI",
                "mode": "add",
            }],
            "referent_updates": [],
        },
    ])
    _, _, application = _application(tmp_path, provider=provider)

    first = application.send_message(
        "Привет, запиши на завтра в календарь в 10 утра",
        project_id=PROJECT_ID,
    )
    second = application.send_message(
        "Тема занятия - обучение Миши AI",
        project_id=PROJECT_ID,
        conversation_id=first.conversation_id,
    )
    diagnostic = application.dialogue_diagnostics(first.conversation_id)

    assert first.assistant_message.content == "Что именно поставить в календарь?"
    assert second.pending_confirmation is not None
    assert "обучение Миши AI" in second.assistant_message.content
    assert "10:00–11:00" in second.assistant_message.content
    assert diagnostic.dialogue_state.active_flow_id is None
    assert diagnostic.application_handoff_type == "google_calendar.event.create"
    assert len(provider.requests) == 2
    assert "Bounded Home turn context" in provider.requests[1].messages[0].content


def _calendar_update_semantics(*, operation_id="google_calendar.event.update") -> dict:
    return {
        "kind": "supported_action",
        "candidate_operation_ids": [operation_id],
        "nearby_operation_ids": [],
        "extracted_slots": [
            {"name": "subject", "evidence_text": "созвон с мамой"},
            {"name": "date", "evidence_text": "завтра"},
            {"name": "old_time", "evidence_text": "12"},
            {"name": "time", "evidence_text": "14"},
        ],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
        "action_request_evidence": {"evidence_text": "Перенеси"},
        "operation_selection_evidence": {"operation_id": None, "evidence_text": None},
    }


def test_semantic_calendar_update_handoff_fails_closed_without_real_proposal(tmp_path):
    class UpdateService:
        def __init__(self): self.calls = []
        def prepare_from_resolved_intent(self, **kwargs):
            self.calls.append(kwargs)
            from backend.runtime.action_contracts import (
                ProposalPreparation,
                ProposalPreparationStatus,
            )
            return ProposalPreparation(
                response="Перенести «созвониться с мамой» в Основном календаре: 12:00 → 14:00?",
                status=ProposalPreparationStatus.PENDING_CONFIRMATION,
                application_operation="google_calendar_update",
            )

    provider = SequencedSemanticProvider([_calendar_update_semantics()])
    _, _, application = _application(tmp_path, provider=provider)
    conversation = application._conversation._conversation
    conversation.temporal_engine.clock = FixedClock(FIXED_NOW)
    update = UpdateService()
    conversation.resolved_capability_adapters = ResolvedCapabilityAdapterRegistry((
        CalendarUpdateHandoffAdapter(update),
    ))

    turn = application.send_message(
        "Перенеси в гугл календаре созвон с мамой завтра с 12 на 14 часов",
        project_id=PROJECT_ID,
    )

    assert turn.assistant_message.content == (
        "Не смогла безопасно подготовить это действие. Ничего не выполняю."
    )
    assert len(update.calls) == 1
    assert update.calls[0]["subject"] == "созвон с мамой"
    assert update.calls[0]["date"] == "2026-08-29"
    assert update.calls[0]["start_time"] == "14:00"
    assert update.calls[0]["old_time"] == "12:00"
    assert turn.pending_confirmation is None
    assert application.dialogue_diagnostics(turn.conversation_id).application_handoff_type == "google_calendar.event.update"
    assert application.dialogue_diagnostics(
        turn.conversation_id
    ).response_projection_state == "failed"


def test_calendar_read_missing_period_clarifies_then_uses_same_flow(tmp_path):
    provider = SequencedSemanticProvider([
        {
            "kind": "supported_action",
            "candidate_operation_ids": ["google_calendar.read"],
            "nearby_operation_ids": [],
            "extracted_slots": [],
            "unresolved_referents": [],
            "ambiguity_hint": "slot",
            "action_request_evidence": {"evidence_text": "Какие события есть"},
            "operation_selection_evidence": {
                "operation_id": None, "evidence_text": None,
            },
        },
        {
            "relation": "follow_up",
            "selected_operation_id": None,
            "operation_selection_evidence": None,
            "slot_updates": [{
                "name": "period", "evidence_text": "завтра", "mode": "add",
            }],
            "referent_updates": [],
        },
    ], conversation_text="Завтра календарь свободен.")
    _, _, application = _application(tmp_path, provider=provider)

    class Calendar:
        def __init__(self): self.periods = []
        def observe_period(self, period, *, now_local):
            self.periods.append(period)
            return CalendarReadOutcome(
                "completed", (), start=now_local, end=now_local,
            )
        def observe(self, *_args, **_kwargs):
            raise AssertionError("legacy parser must not own the follow-up")
        def human_failure(self, _outcome): return "unavailable"

    calendar = Calendar()
    application._conversation._conversation.google_calendar_service = calendar
    application._conversation._conversation.resolved_capability_adapters = (
        ResolvedCapabilityAdapterRegistry((CalendarReadHandoffAdapter(calendar),))
    )

    first = application.send_message(
        "Какие события есть в календаре?", project_id=PROJECT_ID,
    )
    second = application.send_message(
        "завтра", project_id=PROJECT_ID, conversation_id=first.conversation_id,
    )
    diagnostic = application.dialogue_diagnostics(first.conversation_id)

    assert first.assistant_message.content == (
        "За какой период посмотреть — сегодня, завтра или ближайшую неделю?"
    )
    assert calendar.periods == ["завтра"]
    assert second.assistant_message.content == "Завтра календарь свободен."
    assert diagnostic.dialogue_state.active_flow_id is None
    assert diagnostic.application_handoff_type == "google_calendar.read"
    assert diagnostic.response_projection_state == "completed_read"


def test_unseen_polite_drive_read_uses_semantic_handoff_not_legacy_parser(tmp_path):
    provider = SemanticThenConversationProvider(
        json.dumps({
            "kind": "supported_action",
            "candidate_operation_ids": ["google_drive.read"],
            "nearby_operation_ids": [],
            "extracted_slots": [{
                "name": "mode", "evidence_text": "последним",
            }],
            "unresolved_referents": [],
            "ambiguity_hint": "none",
            "action_request_evidence": {"evidence_text": "не могла бы показать"},
            "operation_selection_evidence": {
                "operation_id": None, "evidence_text": None,
            },
        }, ensure_ascii=False),
        "ordinary model must not own a file list",
    )
    _, _, application = _application(tmp_path, provider=provider)

    class Drive:
        reader = type("Reader", (), {"document_store": None})()

        def __init__(self):
            self.calls = []

        def observe(self, *_args, **_kwargs):
            raise AssertionError("legacy phrase parser must not run")

        def observe_resolved(self, **request):
            self.calls.append(request)
            return DriveReadOutcome("search_completed", files=(
                DriveFileCandidate(
                    "provider-id-must-not-escape", "Планы.pdf",
                    "application/pdf", None, 100, True,
                ),
            ))

        @staticmethod
        def human_result(outcome):
            return "Нашла в Google Drive:\n1. " + outcome.files[0].name

    drive = Drive()
    conversation = application._conversation._conversation
    conversation.google_drive_service = drive
    conversation.resolved_capability_adapters = ResolvedCapabilityAdapterRegistry((
        GoogleDriveReadHandoffAdapter(drive),
    ))

    turn = application.send_message(
        "Маш, не могла бы показать, что из файлов на Гугл Диске менялось последним?",
        project_id=PROJECT_ID,
    )
    diagnostic = application.dialogue_diagnostics(turn.conversation_id)

    assert drive.calls[0]["mode"] == "recent"
    assert turn.assistant_message.content == "Нашла в Google Drive:\n1. Планы.pdf"
    assert "provider-id-must-not-escape" not in turn.assistant_message.content
    assert diagnostic.application_handoff_type == "google_drive.read"
    assert diagnostic.response_projection_state == "completed_read"
    assert len(provider.requests) == 1


@pytest.mark.parametrize(("message", "operation_id", "slots", "expected"), (
    (
        "Маш, можешь напомнить, что ты помнишь про локальные модели?",
        "home.memory.recall",
        [{"name": "query", "evidence_text": "локальные модели"}],
        "локальные модели",
    ),
    (
        "Маш, к каким нашим темам мы собирались ещё вернуться?",
        "home.continuity.read",
        [],
        "сохранённой истории",
    ),
))
def test_home_reads_use_one_semantic_ingress_without_legacy_classifier(
    tmp_path, monkeypatch, message, operation_id, slots, expected,
):
    provider = SemanticThenConversationProvider(
        json.dumps({
            "kind": "supported_action",
            "candidate_operation_ids": [operation_id],
            "nearby_operation_ids": [],
            "extracted_slots": slots,
            "unresolved_referents": [],
            "ambiguity_hint": "none",
            "action_request_evidence": {"evidence_text": message.split(", ", 1)[1].rstrip("?")},
            "operation_selection_evidence": {
                "operation_id": None, "evidence_text": None,
            },
        }, ensure_ascii=False),
        "ordinary model must not own Home recall",
    )
    _, _, application = _application(tmp_path, provider=provider)
    handler = application._conversation._conversation.memory_intent_handler
    monkeypatch.setattr(
        handler,
        "handle",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("legacy memory language router must not run")
        ),
    )

    turn = application.send_message(message, project_id=PROJECT_ID)
    diagnostic = application.dialogue_diagnostics(turn.conversation_id)

    assert expected.casefold() in turn.assistant_message.content.casefold()
    assert diagnostic.application_handoff_type == operation_id
    assert diagnostic.response_projection_state == "completed_read"
    assert len(provider.requests) == 1


@pytest.mark.parametrize(("service_name", "method_names", "message"), (
    ("google_calendar_service", ("observe",), "Что у меня завтра?"),
    ("google_drive_service", ("observe",), "Покажи файлы в Drive"),
    ("yandex_mail_service", ("observe",), "Проверь почту"),
    ("yandex_disk_service", ("observe",), "Покажи файлы на Яндекс Диске"),
    ("memory_intent_handler", ("handle",), "Запомни, что мне нравятся локальные модели"),
    (
        "external_observation_service",
        ("observe_fetch_request", "observe_explicit_request"),
        "Проверь в интернете свежие новости Ollama",
    ),
))
def test_dialogue_core_pass_through_never_reparses_raw_turn_in_legacy_handlers(
    tmp_path, monkeypatch, service_name, method_names, message,
):
    provider = SemanticThenConversationProvider(
        json.dumps({
            "kind": "ordinary",
            "candidate_operation_ids": [],
            "nearby_operation_ids": [],
            "extracted_slots": [],
            "unresolved_referents": [],
            "ambiguity_hint": "none",
            "action_request_evidence": {"evidence_text": None},
            "operation_selection_evidence": {
                "operation_id": None, "evidence_text": None,
            },
        }),
        "Не уверена, что ты просишь выполнить действие.",
    )
    _, _, application = _application(tmp_path, provider=provider)

    service = getattr(application._conversation._conversation, service_name)
    for method_name in method_names:
        monkeypatch.setattr(
            service,
            method_name,
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("legacy connector reparsed a DialogueCore turn")
            ),
        )

    turn = application.send_message(message, project_id=PROJECT_ID)

    assert turn.assistant_message.content == (
        "Не уверена, что ты просишь выполнить действие."
    )
    assert any(
        not request.required_capabilities.structured_output
        for request in provider.requests
    )


def test_current_public_question_uses_resolved_web_evidence_before_answer(tmp_path):
    provider = SemanticThenConversationProvider(
        json.dumps({
            "kind": "supported_action",
            "candidate_operation_ids": ["web.search"],
            "nearby_operation_ids": [],
            "extracted_slots": [{
                "name": "query", "evidence_text": "последняя версия Ollama",
            }],
            "unresolved_referents": [],
            "ambiguity_hint": "none",
            "action_request_evidence": {"evidence_text": "какая сейчас"},
            "operation_selection_evidence": {
                "operation_id": None, "evidence_text": None,
            },
        }, ensure_ascii=False),
        "По свежему источнику это версия 1.2.3.",
    )
    _, _, application = _application(tmp_path, provider=provider)
    observation = ExternalObservation(
        request=ObservationRequest(
            observation_id="obs_current",
            query="Ollama latest release",
            authority=InvocationAuthority.ASSISTANT_AUTO,
            freshness=FreshnessRequirement.CURRENT,
            reason="semantic_current_information_need",
            requested_at=FIXED_NOW,
            origin_message_id="placeholder",
        ),
        status=ObservationStatus.COMPLETED,
        evidence=(SearchEvidence(
            source_id="S1",
            provider_id="fake-web",
            search_backend="fake",
            title="Ollama 1.2.3 release",
            url="https://example.test/ollama-1-2-3",
            canonical_url="https://example.test/ollama-1-2-3",
            domain="example.test",
            snippet="Ollama 1.2.3 is the current release.",
            source_time=SourceTime(),
            retrieved_at=FIXED_NOW,
            observation_started_at=FIXED_NOW,
            provider_rank=1,
            freshness_status=FreshnessStatus.FRESH,
        ),),
        provider_calls=1,
        provider_id="fake-web",
        search_backend="fake",
        completed_at=FIXED_NOW,
    )

    class Store:
        def __init__(self): self.item = observation
        def get(self, _observation_id): return self.item

    class Web:
        def __init__(self): self.store, self.calls, self.attachments = Store(), [], []
        def observe_resolved_search(self, message, **kwargs):
            self.calls.append((message, kwargs))
            return observation.model_copy(update={
                "request": observation.request.model_copy(update={
                    "origin_message_id": kwargs["origin_message_id"],
                }),
            })
        @staticmethod
        def model_context(_observation):
            return [{
                "kind": "web_search",
                "source_id": "S1",
                "title": "Ollama 1.2.3 release",
                "domain": "example.test",
                "snippet": "Ollama 1.2.3 is the current release.",
            }]
        @staticmethod
        def human_failure(_observation): return "web failure"
        @staticmethod
        def document_receipt(_observation): return None
        def observations_for_message(self, message_id):
            return (self.store.item,) if self.attachments and self.attachments[-1][1] == message_id else ()
        def attach_assistant_message(self, observation_id, message_id):
            self.attachments.append((observation_id, message_id))

    web = Web()
    conversation = application._conversation._conversation
    conversation.external_observation_service = web
    conversation.resolved_capability_adapters = ResolvedCapabilityAdapterRegistry((
        WebSearchHandoffAdapter(web),
    ))

    turn = application.send_message(
        "Маш, какая сейчас последняя версия Ollama?",
        project_id=PROJECT_ID,
    )

    assert turn.assistant_message.content == "По свежему источнику это версия 1.2.3."
    assert web.calls and web.calls[0][1]["query_hint"] == "последняя версия Ollama"
    assert web.attachments[0][0] == "obs_current"
    evidence_requests = [
        request for request in provider.requests
        if request.private_context.get("external_information")
    ]
    assert len(evidence_requests) == 1
    model_request = evidence_requests[0]
    assert model_request.required_capabilities.structured_output is False
    assert model_request.private_context["external_information"][0]["kind"] == "web_search"
    assert "ВНЕШНЯЯ ИНФОРМАЦИЯ" in model_request.private_context[
        "external_information_contract"
    ]


@pytest.mark.parametrize(("utterance", "semantic", "operation_id", "record_type"), (
    (
        "Сохрани, пожалуйста, что я читаю по вечерам",
        {
            "kind": "supported_action",
            "candidate_operation_ids": ["home.memory.remember"],
            "nearby_operation_ids": [],
            "extracted_slots": [{
                "name": "memory_content", "evidence_text": "я читаю по вечерам",
            }],
            "unresolved_referents": [],
            "ambiguity_hint": "none",
            "action_request_evidence": {"evidence_text": "Сохрани, пожалуйста"},
            "operation_selection_evidence": {
                "operation_id": None, "evidence_text": None,
            },
        },
        "home.memory.remember",
        "fact",
    ),
    (
        "Добавь в дела разобрать фотографии",
        {
            "kind": "supported_action",
            "candidate_operation_ids": ["home.commitments.create"],
            "nearby_operation_ids": [],
            "extracted_slots": [{
                "name": "subject", "evidence_text": "разобрать фотографии",
            }],
            "unresolved_referents": [],
            "ambiguity_hint": "none",
            "action_request_evidence": {"evidence_text": "Добавь в дела"},
            "operation_selection_evidence": {
                "operation_id": None, "evidence_text": None,
            },
        },
        "home.commitments.create",
        "commitment",
    ),
    (
        "Убери из памяти запись про локальные модели",
        {
            "kind": "supported_action",
            "candidate_operation_ids": ["home.memory.forget"],
            "nearby_operation_ids": [],
            "extracted_slots": [{
                "name": "target", "evidence_text": "локальные модели",
            }],
            "unresolved_referents": [],
            "ambiguity_hint": "none",
            "action_request_evidence": {"evidence_text": "Убери из памяти"},
            "operation_selection_evidence": {
                "operation_id": None, "evidence_text": None,
            },
        },
        "home.memory.forget",
        "fact",
    ),
    (
        "Оставь открытой тему про спокойные переходы между сценами",
        {
            "kind": "supported_action",
            "candidate_operation_ids": ["home.continuity.open"],
            "nearby_operation_ids": [],
            "extracted_slots": [{
                "name": "topic",
                "evidence_text": "спокойные переходы между сценами",
            }],
            "unresolved_referents": [],
            "ambiguity_hint": "none",
            "action_request_evidence": {"evidence_text": "Оставь открытой тему"},
            "operation_selection_evidence": {
                "operation_id": None, "evidence_text": None,
            },
        },
        "home.continuity.open",
        "continuity_state",
    ),
    (
        "Отметь дело про разработку Masha Home выполненным",
        {
            "kind": "supported_action",
            "candidate_operation_ids": ["home.commitments.complete"],
            "nearby_operation_ids": [],
            "extracted_slots": [{
                "name": "target", "evidence_text": "разработку Masha Home",
            }],
            "unresolved_referents": [],
            "ambiguity_hint": "none",
            "action_request_evidence": {"evidence_text": "Отметь дело"},
            "operation_selection_evidence": {
                "operation_id": None, "evidence_text": None,
            },
        },
        "home.commitments.complete",
        "commitment",
    ),
    (
        "Закрой открытую тему про спокойные переходы",
        {
            "kind": "supported_action",
            "candidate_operation_ids": ["home.continuity.resolve"],
            "nearby_operation_ids": [],
            "extracted_slots": [{
                "name": "target", "evidence_text": "спокойные переходы",
            }],
            "unresolved_referents": [],
            "ambiguity_hint": "none",
            "action_request_evidence": {"evidence_text": "Закрой открытую тему"},
            "operation_selection_evidence": {
                "operation_id": None, "evidence_text": None,
            },
        },
        "home.continuity.resolve",
        "continuity_state",
    ),
))
def test_local_mutations_use_one_semantic_handoff_and_durable_proposal(
    tmp_path, utterance, semantic, operation_id, record_type,
):
    provider = SemanticThenConversationProvider(
        json.dumps(semantic, ensure_ascii=False),
        "Я уже всё сделала.",
    )
    _, _, application = _application(tmp_path, provider=provider)
    conversation = application._conversation._conversation
    if operation_id == "home.continuity.resolve":
        conversation.memory_intent_handler._propose_open_thread(
            "Продумать спокойные переходы",
            "seed-conversation",
        )
        conversation.memory_intent_handler.handle(
            "да",
            conversation_id="seed-conversation",
            project_id=PROJECT_ID,
        )

    turn = application.send_message(utterance, project_id=PROJECT_ID)
    assert not hasattr(
        conversation.memory_intent_handler.capability_router,
        "classifier",
    )
    proposal = conversation.memory_intent_handler.proposal_store.current_for_conversation(
        turn.conversation_id,
    )
    diagnostic = application.dialogue_diagnostics(turn.conversation_id)

    assert proposal is not None and proposal.record_type == record_type
    assert proposal.status is ProposalStatus.PENDING
    assert turn.pending_confirmation is not None
    assert diagnostic.application_handoff_type == operation_id
    assert diagnostic.response_projection_state == "waiting_confirmation"
    assert "Я уже всё сделала" not in turn.assistant_message.content
    assert all(request.required_capabilities.structured_output for request in provider.requests)


def test_semantic_create_misclassification_of_clear_update_uses_update_owner(tmp_path):
    provider = SequencedSemanticProvider([
        _calendar_update_semantics(operation_id="google_calendar.event.create"),
    ], conversation_text="Созвон уже перенесён.")
    _, _, application = _application(tmp_path, provider=provider)

    turn = application.send_message(
        "Перенеси в гугл календаре созвон с мамой завтра с 12 на 14 часов",
        project_id=PROJECT_ID,
    )

    assert turn.pending_confirmation is None
    assert application.dialogue_diagnostics(
        turn.conversation_id
    ).application_handoff_type == "google_calendar.event.update"
    assert "перенесён" not in turn.assistant_message.content
    assert len(provider.requests) == 1
    assert application._conversation._conversation.google_calendar_create_service.writer.receipt_store._items == {}


def test_live_calendar_update_stays_pending_then_mutates_only_after_confirmation(tmp_path):
    from tests.test_google_calendar_update import (
        NOW as UPDATE_NOW,
        _Transport,
        _event,
        _event_patches,
        _service,
    )

    provider = SequencedSemanticProvider([{
        "kind": "supported_action",
        "candidate_operation_ids": ["google_calendar.event.update"],
        "nearby_operation_ids": [],
        "extracted_slots": [
            {"name": "subject", "evidence_text": "созвониться с мамой"},
            {"name": "date", "evidence_text": "завтра"},
            {"name": "old_time", "evidence_text": "14"},
            {"name": "time", "evidence_text": "13"},
        ],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
        "action_request_evidence": {"evidence_text": "перенеси"},
        "operation_selection_evidence": {
            "operation_id": "google_calendar.event.update",
            "evidence_text": "перенеси",
        },
    }])
    _, _, application = _application(tmp_path, provider=provider)
    conversation = application._conversation._conversation
    conversation.temporal_engine.clock = FixedClock(UPDATE_NOW)
    event = _event(
        title="созвон с мамой",
        start="2026-08-26T10:00:00Z",
        end="2026-08-26T11:00:00Z",
    )
    service, updater, transport, _ = _service(
        tmp_path / "live-update",
        _Transport([event]),
    )
    service.proposal_store = conversation.memory_intent_handler.proposal_store
    conversation.google_calendar_update_service = service
    conversation.resolved_capability_adapters = ResolvedCapabilityAdapterRegistry((
        CalendarUpdateHandoffAdapter(service),
    ))

    proposed = application.send_message(
        "Маш, перенеси завтра созвониться с мамой с 14 на 13 часов",
        project_id=PROJECT_ID,
    )

    assert proposed.pending_confirmation is not None
    assert proposed.pending_confirmation.confirmation_type == "google_calendar_update"
    assert "14:00–15:00 → 13:00–14:00" in proposed.assistant_message.content
    assert _event_patches(transport) == []
    assert application.dialogue_diagnostics(
        proposed.conversation_id
    ).response_projection_state == "waiting_confirmation"

    confirmed = application.resolve_confirmation(
        conversation_id=proposed.conversation_id,
        proposal_id=proposed.pending_confirmation.proposal_id,
        decision="confirm",
        project_id=PROJECT_ID,
    )

    assert confirmed.status.value == "confirmed"
    assert confirmed.pending_confirmation is None
    assert confirmed.assistant_message.content == (
        "Готово: «созвон с мамой» обновила в Основном календаре."
    )
    assert len(_event_patches(transport)) == 1
    receipt = next(iter(updater.receipt_store._items.values()))
    assert receipt.status == "verified"
    assert receipt.verified_at is not None


def test_calendar_delete_uses_real_target_preview_and_verified_confirmation(tmp_path):
    from tests.test_google_calendar_delete import _delete_calls, _service

    provider = SequencedSemanticProvider([{
        "kind": "supported_action",
        "candidate_operation_ids": ["google_calendar.event.delete"],
        "nearby_operation_ids": [],
        "extracted_slots": [
            {"name": "subject", "evidence_text": "встречу команды"},
            {"name": "date", "evidence_text": "завтра"},
            {"name": "time", "evidence_text": "16:00"},
        ],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
        "action_request_evidence": {"evidence_text": "Удали"},
        "operation_selection_evidence": {
            "operation_id": None, "evidence_text": None,
        },
    }])
    _, _, application = _application(tmp_path, provider=provider)
    conversation = application._conversation._conversation
    conversation.temporal_engine.clock = FixedClock(
        datetime(2026, 8, 31, 9, 0, tzinfo=timezone.utc)
    )
    service, deleter, transport = _service(tmp_path / "live-delete")
    service.proposal_store = conversation.memory_intent_handler.proposal_store
    conversation.google_calendar_delete_service = service
    conversation.resolved_capability_adapters = ResolvedCapabilityAdapterRegistry((
        CalendarDeleteHandoffAdapter(service),
    ))

    proposed = application.send_message(
        "Удали из календаря завтра встречу команды в 16:00",
        project_id=PROJECT_ID,
    )

    assert proposed.pending_confirmation is not None, (
        proposed.assistant_message.content,
        application.dialogue_diagnostics(proposed.conversation_id),
        transport.calls,
    )
    assert proposed.pending_confirmation.confirmation_type == "google_calendar_delete"
    assert proposed.assistant_message.content.startswith("Удалить «встреча команды»")
    assert _delete_calls(transport) == []

    confirmed = application.resolve_confirmation(
        conversation_id=proposed.conversation_id,
        proposal_id=proposed.pending_confirmation.proposal_id,
        decision="confirm",
        project_id=PROJECT_ID,
    )

    assert confirmed.status.value == "confirmed"
    assert confirmed.assistant_message.content == (
        "Готово: «встреча команды» удалено из Основного календаря."
    )
    assert len(_delete_calls(transport)) == 1
    assert next(iter(deleter.receipt_store._items.values())).status == "verified"


def test_mail_delete_uses_presented_target_and_cannot_move_before_confirmation(tmp_path):
    from tests.test_yandex_mail_mutations import _service, _summary
    provider = SequencedSemanticProvider([{
        "kind": "supported_action",
        "candidate_operation_ids": ["yandex_mail.message.delete"],
        "nearby_operation_ids": [],
        "extracted_slots": [{
            "name": "target", "evidence_text": "это письмо",
        }],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
        "action_request_evidence": {"evidence_text": "Удали"},
        "operation_selection_evidence": {
            "operation_id": None, "evidence_text": None,
        },
    }])
    _, _, application = _application(tmp_path, provider=provider)
    conversation = application._conversation._conversation
    service, writer, mailbox, _, _, _ = _service(tmp_path / "live-mail-delete")
    created = conversation.history.create()
    service.presented_read_sets.present(
        created.id,
        "yandex_mail",
        (_summary(),),
        entity_kind="письмо",
        presentation_kind="unread",
    )
    service.proposal_store = conversation.memory_intent_handler.proposal_store
    conversation.yandex_mail_mutation_service = service
    conversation.presented_context_provider = (
        service.presented_read_sets.model_safe_hints
    )
    conversation.resolved_capability_adapters = ResolvedCapabilityAdapterRegistry((
        YandexMailDeleteHandoffAdapter(service),
    ))

    proposed = application.send_message(
        "Удали это письмо",
        project_id=PROJECT_ID,
        conversation_id=created.id,
    )

    assert proposed.pending_confirmation is not None
    assert proposed.pending_confirmation.confirmation_type == "yandex_mail_delete"
    assert "Переместить в корзину" in proposed.assistant_message.content
    assert mailbox.move_calls == []

    confirmed = application.resolve_confirmation(
        conversation_id=created.id,
        proposal_id=proposed.pending_confirmation.proposal_id,
        decision="confirm",
        project_id=PROJECT_ID,
    )

    assert confirmed.status.value == "confirmed"
    assert "переместила в корзину" in confirmed.assistant_message.content
    assert mailbox.move_calls == [("42", "Trash")]
    assert next(iter(writer.receipt_store._items.values())).status == "verified"


def test_uncertain_mail_move_projects_recovery_and_defer_keeps_receipt_truth(tmp_path):
    from tests.test_yandex_mail_mutations import _service, _summary
    provider = SequencedSemanticProvider([{
        "kind": "supported_action",
        "candidate_operation_ids": ["yandex_mail.message.move"],
        "nearby_operation_ids": [],
        "extracted_slots": [{
            "name": "target", "evidence_text": "это письмо",
        }],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
        "action_request_evidence": {"evidence_text": "Убери в архив"},
        "operation_selection_evidence": {
            "operation_id": None, "evidence_text": None,
        },
    }])
    _, _, application = _application(tmp_path, provider=provider)
    conversation = application._conversation._conversation
    service, writer, mailbox, _, _, _ = _service(tmp_path / "mail-uncertain")
    created = conversation.history.create()
    service.presented_read_sets.present(
        created.id,
        "yandex_mail",
        (_summary(),),
        entity_kind="письмо",
        presentation_kind="unread",
    )
    service.proposal_store = conversation.memory_intent_handler.proposal_store
    conversation.yandex_mail_mutation_service = service
    conversation.presented_context_provider = (
        service.presented_read_sets.model_safe_hints
    )
    conversation.resolved_capability_adapters = ResolvedCapabilityAdapterRegistry((
        YandexMailMoveHandoffAdapter(service),
    ))

    proposed = application.send_message(
        "Убери в архив это письмо",
        project_id=PROJECT_ID,
        conversation_id=created.id,
    )
    mailbox.fail_after_move = True
    uncertain = application.resolve_confirmation(
        conversation_id=created.id,
        proposal_id=proposed.pending_confirmation.proposal_id,
        decision="confirm",
        project_id=PROJECT_ID,
    )

    assert uncertain.status.value == "failed"
    assert uncertain.pending_confirmation.confirmation_type == (
        "yandex_mail_mutation_recovery"
    )
    assert uncertain.pending_confirmation.title == "Проверить перемещение письма?"
    assert mailbox.move_calls == [("42", "Archive")]

    deferred = application.resolve_confirmation(
        conversation_id=created.id,
        proposal_id=proposed.pending_confirmation.proposal_id,
        decision="reject",
        project_id=PROJECT_ID,
    )
    receipt = next(iter(writer.receipt_store._items.values()))

    assert deferred.status.value == "rejected"
    assert deferred.pending_confirmation is None
    assert "могло уже примениться" in deferred.assistant_message.content
    assert receipt.status == "moved_unverified"
    assert mailbox.move_calls == [("42", "Archive")]


def test_exact_update_never_reaches_ordinary_success_prose_without_proposal(tmp_path):
    provider = SemanticThenConversationProvider(
        json.dumps({
            "kind": "ordinary",
            "candidate_operation_ids": [],
            "nearby_operation_ids": [],
            "extracted_slots": [],
            "unresolved_referents": [],
            "ambiguity_hint": "none",
            "action_request_evidence": {"evidence_text": None},
            "operation_selection_evidence": {
                "operation_id": None, "evidence_text": None,
            },
        }),
        "Сделано. Созвон с мамой теперь в 13:00 завтра.",
    )
    _, _, application = _application(tmp_path, provider=provider)

    turn = application.send_message(
        "Маш, перенеси завтра созвониться с мамой с 14 на 13 часов",
        project_id=PROJECT_ID,
    )

    assert "Сделано" not in turn.assistant_message.content
    assert "теперь в 13" not in turn.assistant_message.content
    assert turn.pending_confirmation is None
    assert len(provider.requests) == 1
    diagnostic = application.dialogue_diagnostics(turn.conversation_id)
    assert diagnostic.response_projection_state == "unsupported"
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
            "action_request_evidence": {"evidence_text": "запиши"},
            "operation_selection_evidence": {"operation_id": None, "evidence_text": None},
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
    first = application.send_message(
        "Поставь в календарь завтра в 10",
        project_id=PROJECT_ID,
    )
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
        "action_request_evidence": {"evidence_text": "Запиши"},
        "operation_selection_evidence": {"operation_id": None, "evidence_text": None},
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
        "action_request_evidence": {"evidence_text": "надо не забыть"},
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
