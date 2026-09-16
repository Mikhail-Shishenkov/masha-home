"""Acceptance coverage for application-owned human reference resolution."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.conversation.conversation_service import ConversationService
from backend.conversation.conversation_store import ConversationStore
from backend.conversation.conversation_models import ConversationRole
from backend.conversation.human_reference import HumanEntityKind
from backend.conversation.memory_intent import MemoryIntentHandler, MemoryProposalStore
from backend.connectors.presented_read_sets import PresentedReadSetRegistry
from backend.conversation.response_contract import (
    UNRECEIPTED_MUTATION_RESPONSE,
    render_model_response,
)
from backend.identity.identity_kernel import IdentityKernel
from backend.identity.identity_store import IdentityStore
from backend.llm.fake_provider import FakeProvider
from backend.llm.model_router import ModelRouter
from backend.memory.confirmed_memory_service import ConfirmedMemoryService
from backend.memory.memory_management import MemoryManagementService
from backend.memory.memory_retriever import MemoryRetriever
from backend.memory.shared_continuity import SharedContinuityService
from backend.memory.sqlite_repository import MemorySqliteRepository
from backend.memory.working_memory import WorkingMemory


ROOT = Path(__file__).resolve().parents[1]
PROJECT = "project_masha_home"


@pytest.mark.parametrize("space", ["ordinary", "special_evening"])
def test_application_clarification_preserves_topic_without_replaying_actions(tmp_path, memory_path, space):
    import json
    from backend.conversation.conversation_models import ConversationMessageOrigin

    service, repository, provider = _service(tmp_path, memory_path)
    cid = service.history.create(space=space).id
    rows = [
        (ConversationRole.USER, "Обсуждаем засолку форели.", ConversationMessageOrigin.USER),
        (ConversationRole.ASSISTANT, "Мы обсуждаем форель.", ConversationMessageOrigin.MODEL),
        (ConversationRole.USER, "А в интернете есть что-то про это?", ConversationMessageOrigin.USER),
        (ConversationRole.ASSISTANT, "Уточни тему поиска.", ConversationMessageOrigin.APPLICATION),
    ]
    for role, text, origin in rows:
        service.history.append(cid, role, text, origin=origin)
    before = repository.read_document()
    # Even if the model invents success, preserving history grants no authority.
    provider.response_text = "Я создала событие в календаре."
    returned, response = service.send(
        "А о чём мы сейчас говорим?", conversation_id=cid, project_id=PROJECT,
        home_moment=space, allow_capability_routing=False,
    )
    assert returned == cid
    messages = provider.last_request.messages
    assert any("засолку форели" in m.content for m in messages)
    application = next(json.loads(m.content) for m in messages if '"source": "home_application_history"' in m.content)
    assert application["text"] == "Уточни тему поиска."
    assert application["recorded_at"]
    assert messages[-1].content == "А о чём мы сейчас говорим?"
    assert response == UNRECEIPTED_MUTATION_RESPONSE
    assert repository.read_document() == before
    assert service.memory_intent_handler.proposal_store.current_for_conversation(cid) is None
    assert provider.last_request.required_capabilities.tools is False


@pytest.mark.parametrize("case", ["confirm", "reject", "ambiguous", "wrong_old_time"])
def test_saved_reminder_reschedule_reuses_record_and_requires_confirmation(tmp_path, memory_path, case):
    from datetime import datetime, timezone
    from backend.application.resolved_capabilities import TimedCommitmentUpdateHandoffAdapter
    from backend.conversation.resolution_coordinator import ResolvedCapabilityHandoff, DomainProposalContext
    from backend.conversation.interpretation_v2 import InterpretationSlot
    from backend.temporal.temporal_engine import TemporalEngine, FixedClock

    service, repository, provider = _service(tmp_path, memory_path)
    handler = service.memory_intent_handler
    handler.temporal_engine = TemporalEngine(clock=FixedClock(datetime(2026, 9, 15, 4, tzinfo=timezone.utc)))
    cid = service.history.create().id
    for _ in range(2 if case == "ambiguous" else 1):
        handler.propose_timed_commitment_from_resolved_intent(
            subject="позвонить маме", date="2026-09-16", time="09:00",
            conversation_id=cid, project_id=PROJECT,
        )
        handler.handle("да", conversation_id=cid, project_id=PROJECT)
    before = repository.read_document()
    original = next(row for row in before.commitments if row.text == "позвонить маме")
    slots = [InterpretationSlot(name=name, value=value, origin="semantic") for name, value in (
        ("subject", "напоминание про маму"), ("time", "14:00"),
    )]
    if case == "wrong_old_time":
        slots.append(InterpretationSlot(name="old_time", value="12:00", origin="semantic"))
    handoff = ResolvedCapabilityHandoff(
        operation_id="home.timed_commitments.update", conversation_id=cid,
        original_utterance="Хочу, чтобы напоминание позвонить маме сработало в 14:00",
        slots=tuple(slots),
    )
    result = TimedCommitmentUpdateHandoffAdapter(handler).resolve(handoff, DomainProposalContext(
        project_id=PROJECT, now_local=handler.temporal_engine.now_local(),
    ))
    assert repository.read_document() == before
    assert not provider.requests
    proposal = handler.proposal_store.current_for_conversation(cid)
    if case in {"ambiguous", "wrong_old_time"}:
        assert result.projection_state == "failed" and proposal is None
        return
    assert result.projection_state == "waiting_confirmation"
    assert proposal.operation == "edit" and proposal.target_record_id == original.id
    assert "14:00" in result.response and "16.09.2026" in result.response
    from backend.application.conversation import ConversationApplicationService
    service.temporal_engine = handler.temporal_engine
    kind, title, detail = ConversationApplicationService._confirmation_copy(
        SimpleNamespace(_conversation=service), proposal,
    )
    assert kind == "commitment_reschedule" and "выполненным" not in title
    assert "14:00" in detail
    handler.handle("не сейчас" if case == "reject" else "да", conversation_id=cid, project_id=PROJECT)
    after = repository.read_document()
    if case == "reject":
        assert after == before
    else:
        updated = next(row for row in after.commitments if row.id == original.id)
        assert updated.due_at == datetime(2026, 9, 16, 10, tzinfo=timezone.utc)
        assert updated.text == original.text and updated.status == original.status
        assert updated.reminder_delivery_mode == original.reminder_delivery_mode
        assert len(after.commitments) == len(before.commitments)
        handler.handle("да", conversation_id=cid, project_id=PROJECT)
        assert repository.read_document() == after


def test_answer_uses_same_entity_projection_as_understanding_without_retaining_old_selection(tmp_path, memory_path):
    from backend.conversation.turn_context import TurnContextEnvelopeBuilder

    service, repository, provider = _service(tmp_path, memory_path)
    current = [{
        "position": 1, "owner_operation_id": "yandex_mail.read", "kind": "письмо",
        "human_label": "Поездка на выходных", "focused": True,
        "provider_id": "private-provider-id",
    }]
    service.presented_context_provider = lambda cid: tuple(current)
    before = repository.read_document()
    provider.response_text = "Я создала событие в календаре."
    cid, response = service.send("О чём этот заголовок?", project_id=PROJECT, allow_capability_routing=False)
    assert response == UNRECEIPTED_MUTATION_RESPONSE
    semantic_context = TurnContextEnvelopeBuilder().build(
        temporal_context=service.temporal_engine.context(None), presented_context=tuple(current),
    )
    projected = provider.last_request.private_context["presented_entities"]
    assert projected == semantic_context.model_safe_value()["presented_entities"]
    assert projected[0]["focused"] is True
    assert "private-provider-id" not in str(provider.last_request)
    assert provider.last_request.private_context["external_information"] == []
    assert repository.read_document() == before
    assert service.memory_intent_handler.proposal_store.current_for_conversation(cid) is None

    current.clear()  # An empty/new list must not resurrect the earlier focus.
    service.send("А сейчас?", conversation_id=cid, project_id=PROJECT, allow_capability_routing=False)
    assert provider.last_request.private_context["presented_entities"] == []


@pytest.mark.parametrize("case", ["correct", "invented", "ambiguous", "foreign_operation", "timeout", "save_failure", "ordinary"])
def test_pending_reminder_revision_is_not_confirmation(tmp_path, memory_path, monkeypatch, case):
    from datetime import datetime, timezone
    from unittest.mock import Mock
    from backend.application.home_capabilities import default_home_capability_catalog
    from backend.conversation.clarification import FollowUpResolutionEngine, DeterministicClarificationBuilder
    from backend.conversation.interpretation_v2 import CapabilityCandidateDiscovery
    from backend.conversation.pending_resolution import PendingResolutionStore
    from backend.conversation.resolution_coordinator import DialogueCore
    from backend.conversation.semantic_resolver import SemanticProposalValidator, SemanticFollowUpResult
    from backend.temporal.temporal_engine import TemporalEngine, FixedClock

    service, repository, ordinary = _service(tmp_path, memory_path)
    temporal = TemporalEngine(clock=FixedClock(datetime(2026, 9, 15, 4, tzinfo=timezone.utc)))
    service.temporal_engine = temporal
    handler = service.memory_intent_handler
    handler.temporal_engine = temporal
    conversation = service.history.create()
    handler.propose_timed_commitment_from_resolved_intent(
        subject="позвонить маме", date="2026-09-16", time="09:00",
        conversation_id=conversation.id, project_id=PROJECT,
    )
    old = handler.proposal_store.current_for_conversation(conversation.id)
    before = repository.read_document()
    discovery = CapabilityCandidateDiscovery(catalog=default_home_capability_catalog())
    validator = SemanticProposalValidator(
        catalog=discovery.catalog, specifications=discovery.specifications,
        known_operation_ids=frozenset(discovery.specifications.operation_ids),
    )
    resolver = Mock()
    resolver.resolve_follow_up.return_value = SemanticFollowUpResult.model_validate(
        {"failure": "timeout", "latency_ms": 0} if case == "timeout" else {"latency_ms": 0, "proposal": {
            "relation": "not_a_follow_up" if case == "ordinary" else "follow_up",
            "selected_operation_id": "google_calendar.event.create" if case == "foreign_operation" else None,
            "operation_selection_evidence": "лучше" if case == "foreign_operation" else None,
            "slot_updates": [] if case == "ordinary" else [{
                "name": "time", "mode": "correct",
                "evidence_text": "11 утра" if case == "invented" else "вечером" if case == "ambiguous" else "10 утра",
            }], "referent_updates": [],
        }}
    )
    service.dialogue_core = DialogueCore(
        discovery=discovery, builder=DeterministicClarificationBuilder(catalog=discovery.catalog),
        engine=FollowUpResolutionEngine(semantic_resolver=resolver, semantic_validator=validator),
        store=PendingResolutionStore(tmp_path / "pending.json"),
    )
    if case == "save_failure":
        monkeypatch.setattr(handler.proposal_store, "_save", Mock(side_effect=OSError("disk full")))
    reply = "Хочу поговорить о книгах" if case == "ordinary" else "Нет, лучше вечером" if case == "ambiguous" else "Нет, лучше в 10 утра"
    _, response = service.send(reply, conversation_id=conversation.id, project_id=PROJECT)
    current = handler.proposal_store.current_for_conversation(conversation.id)
    assert repository.read_document() == before
    assert service.dialogue_core.store.active_for_conversation(conversation.id) is None
    assert len(handler.proposal_store.pending_for_conversation(conversation.id)) == 1
    context = resolver.resolve_follow_up.call_args.args[2].model_dump_json()
    assert old.id not in context and old.record_payload["id"] not in context
    if case == "ordinary":
        assert current == old
        return
    assert ordinary.requests == []  # Application preview cannot be rewritten as success.
    assert not any(word in response.lower() for word in ("готово", "сделано", "сохранила напоминание"))
    assert service.history.messages(conversation.id)[-1].origin.value == "application"
    if case != "correct":
        assert current == old
        assert "09:00" in response
        assert MemoryProposalStore(handler.proposal_store.file_path).current_for_conversation(conversation.id) == old
        return
    assert current.id != old.id and current.status.value == "pending"
    assert current.record_payload["id"] == old.record_payload["id"]
    assert "10:00" in response and "Подтверждаешь?" in response
    assert handler.proposal_store.get(old.id).status.value == "cancelled"
    from backend.application.conversation import ConversationApplicationService
    projected = ConversationApplicationService(conversation=service, models=Mock()).pending_confirmation(conversation.id)
    assert projected.proposal_id == current.id
    assert projected.subject == current.record_payload["text"]
    assert projected.due_at == datetime.fromisoformat(current.record_payload["due_at"].replace("Z", "+00:00"))
    handler.proposal_store = MemoryProposalStore(handler.proposal_store.file_path)
    assert handler.proposal_store.current_for_conversation(conversation.id) == current
    # An obsolete UI confirmation must not approve the revised preview.
    service.resolve_proposal_confirmation(
        conversation_id=conversation.id, proposal_id=old.id, confirm=True, project_id=PROJECT,
    )
    assert repository.read_document() == before
    _, confirmed = service.send("Да", conversation_id=conversation.id, project_id=PROJECT)
    assert "сохранила" in confirmed
    saved = next(item for item in repository.read_document().commitments if item.id == current.record_payload["id"])
    assert saved.text == "позвонить маме"
    assert saved.due_at.astimezone(temporal.home_timezone.tzinfo).hour == 10
    assert handler.proposal_store.current_for_conversation(conversation.id) is None
    assert resolver.resolve_follow_up.call_count == 1


def test_evening_is_separate_history_and_never_passively_saved(tmp_path, memory_path):
    from unittest.mock import Mock
    service, _, provider = _service(tmp_path, memory_path)
    service.passive_memory_service = Mock()
    first, _ = service.send("ORDINARY SECRET", project_id=PROJECT, allow_capability_routing=False)
    evening, _ = service.send("EVENING PRIVATE", conversation_id=first, project_id=PROJECT, home_moment="special_evening")
    assert evening != first
    assert "ORDINARY SECRET" not in repr(provider.last_request)
    service.passive_memory_service.observe_safely.assert_not_called()
    returned, _ = service.send("DAY RETURN", conversation_id=evening, project_id=PROJECT, allow_capability_routing=False)
    assert returned != evening
    assert "EVENING PRIVATE" not in repr(provider.last_request)
    assert service.history.get(evening).space == "special_evening"


def test_empty_mail_list_ordinal_never_invokes_ordinary_model(tmp_path, memory_path):
    from backend.connectors.yandex_mail.service import YandexMailConversationService
    from unittest.mock import Mock
    registry = PresentedReadSetRegistry()
    service, _, provider = _service(tmp_path, memory_path, presented_registry=registry)
    conversation = service.history.create()
    registry.present(conversation.id, "yandex_mail", (), entity_kind="письмо", presentation_kind="unread")
    service.yandex_mail_service = YandexMailConversationService(reader=Mock(), presented_read_sets=registry)
    _, response = service.send("первое", conversation_id=conversation.id, project_id=PROJECT)
    assert "нет писем для выбора" in response
    assert provider.requests == []


def test_application_delete_cancels_proposal_without_memory_mutation(tmp_path, memory_path):
    from backend.application.conversation import ConversationApplicationService
    from unittest.mock import Mock
    service, repository, _ = _service(tmp_path, memory_path)
    conversation = service.history.create()
    service.history.append(conversation.id, ConversationRole.USER, "Disposable")
    service.memory_intent_handler.handle("Запомни: я люблю чай", conversation_id=conversation.id, project_id=PROJECT)
    assert service.memory_intent_handler.proposal_store.pending_for_conversation(conversation.id)
    before = repository.read_document()
    app = ConversationApplicationService(conversation=service, models=Mock())
    app.delete_conversation(conversation.id)
    assert app.recent_conversations() == ()
    assert service.memory_intent_handler.proposal_store.pending_for_conversation(conversation.id) == ()
    assert repository.read_document() == before


def test_conversation_shelves_filter_before_pagination(tmp_path, memory_path):
    from backend.application.conversation import ConversationApplicationService
    from unittest.mock import Mock
    service, _, _ = _service(tmp_path, memory_path)
    ordinary = service.history.create()
    service.history.append(ordinary.id, ConversationRole.USER, "Ordinary")
    for _ in range(3):
        evening = service.history.create(space="special_evening")
        service.history.append(evening.id, ConversationRole.USER, "Private evening")
    app = ConversationApplicationService(conversation=service, models=Mock())
    assert app.latest_conversation().conversation_id == ordinary.id
    page = app.conversation_page(space="ordinary", limit=1)
    assert page.total == 1 and page.items[0].conversation_id == ordinary.id
    assert "Private evening" not in page.model_dump_json()
    assert app.conversation_page(space="special_evening", limit=2).has_more


def _service(tmp_path, memory_path, *, presented_registry=None):
    repository = MemorySqliteRepository(tmp_path / "memory.sqlite3")
    repository.import_json(memory_path)
    provider = FakeProvider(
        provider_id="ollama-local",
        response_text="model must not run",
    )
    handler = MemoryIntentHandler(
        proposal_store=MemoryProposalStore(tmp_path / "proposals.json"),
        confirmed_memory=ConfirmedMemoryService(repository),
        memory_management=MemoryManagementService(repository),
        shared_continuity=SharedContinuityService(repository),
        presented_context_registry=presented_registry,
    )
    service = ConversationService(
        identity_kernel=IdentityKernel(IdentityStore(ROOT / "identity" / "masha.identity.json")),
        memory_retriever=MemoryRetriever(repository),
        working_memory=WorkingMemory(),
        router=ModelRouter([provider]),
        history=ConversationStore(tmp_path / "history.json"),
        memory_intent_handler=handler,
    )
    return service, repository, provider


def test_ordinal_never_uses_an_older_home_list_after_another_owner_presented(
    tmp_path,
    memory_path,
):
    registry = PresentedReadSetRegistry()
    service, _, provider = _service(
        tmp_path,
        memory_path,
        presented_registry=registry,
    )
    conversation_id = _save_relationship(service, "Миша любит чай")
    _, _ = _send(service, "что есть в нашей истории?", conversation_id)
    assert registry.current_context(conversation_id).owner == "home_information"

    registry.present(
        conversation_id,
        "yandex_mail",
        (SimpleNamespace(subject="Новое письмо"),),
        entity_kind="письмо",
    )
    _, response = _send(service, "удали первый пункт", conversation_id)

    assert "Сначала попроси показать" in response
    assert service.memory_intent_handler.proposal_store.current_for_conversation(
        conversation_id
    ) is None
    assert provider.last_request is None


def test_personal_pronoun_is_broad_recall_scope_not_literal_search(
    tmp_path,
    memory_path,
):
    service, _, _ = _service(tmp_path, memory_path)
    conversation_id = _save_relationship(service, "Миша любит чай")

    result = service.memory_intent_handler.recall_from_resolved_intent(
        query="обо мне",
        project_id=PROJECT,
        conversation_id=conversation_id,
    )

    broad = service.memory_intent_handler.recall_from_resolved_intent(
        query=None,
        project_id=PROJECT,
        conversation_id=conversation_id,
    )
    assert result.handled is True
    assert result.response == broad.response


def _send(service, message, conversation_id=None):
    return service.send(message, project_id=PROJECT, conversation_id=conversation_id)


def _confirm(service, conversation_id):
    return _send(service, "да", conversation_id)[1]


def _save_relationship(service, text, conversation_id=None):
    conversation_id, _ = _send(
        service,
        f"Сохрани как наш момент: {text}",
        conversation_id,
    )
    _confirm(service, conversation_id)
    return conversation_id


def _open_thread(service, text, conversation_id=None):
    conversation_id, _ = _send(
        service,
        f"Оставь это как открытую нить: {text}",
        conversation_id,
    )
    _confirm(service, conversation_id)
    return conversation_id


def test_exact_production_history_ordinal_resolves_real_continuity_only_after_confirmation(
    tmp_path,
    memory_path,
):
    service, repository, provider = _service(tmp_path, memory_path)
    conversation_id = _save_relationship(service, "пусть кот останется с нами")
    oldest = "обсудить границы длинных разговоров"
    selected = "Позже решить, какие состояния Маши использовать для длинных разговоров"
    newest = "о том какую модель использовать для длинных разговоров"
    for summary in (oldest, selected, newest):
        conversation_id = _open_thread(service, summary, conversation_id)

    _, history = _send(service, "что есть в нашей истории?", conversation_id)
    presented = service.memory_intent_handler.presented_entity_set(conversation_id)

    assert presented is not None
    assert [item.ordinal for item in presented.items] == [1, 2, 3, 4]
    assert [item.human_label for item in presented.items] == [
        "пусть кот останется с нами",
        newest,
        selected,
        oldest,
    ]
    assert [item.entity_kind for item in presented.items] == [
        HumanEntityKind.MEMORY,
        HumanEntityKind.CONTINUITY,
        HumanEntityKind.CONTINUITY,
        HumanEntityKind.CONTINUITY,
    ]
    assert history.splitlines()[1:] == [
        "1. Воспоминание: пусть кот останется с нами",
        f"2. Открытая тема: {newest}",
        f"3. Открытая тема: {selected}",
        f"4. Открытая тема: {oldest}",
    ]

    selected_id = presented.items[2].entity_id
    before = {
        item.id: item.status.value
        for _, item in service.memory_intent_handler.shared_continuity.open_follow_ups()
    }
    _, proposal_text = _send(service, "удали третью по списку", conversation_id)
    proposal = service.memory_intent_handler.proposal_store.current_for_conversation(
        conversation_id
    )

    assert provider.last_request is None
    assert proposal is not None
    assert proposal.record_type == "continuity_state"
    assert proposal.operation == "continuity_update"
    assert "Убрать открытую тему" in proposal_text
    assert selected in proposal_text
    assert {
        item.id: item.status.value
        for _, item in service.memory_intent_handler.shared_continuity.open_follow_ups()
    } == before
    replacement = {
        item["id"]: item["status"]
        for item in proposal.record_payload["intended_follow_ups"]
    }
    assert replacement[selected_id] == "resolved"
    assert all(
        status == "open"
        for item_id, status in replacement.items()
        if item_id != selected_id
    )

    receipt = _confirm(service, conversation_id)
    remaining = {
        item.id: item.summary
        for _, item in service.memory_intent_handler.shared_continuity.open_follow_ups()
    }
    assert receipt == "Готово. Наша история обновлена."
    assert selected_id not in remaining
    assert set(remaining.values()) == {oldest, newest}
    assert any(
        event["action"] == "continuity_update"
        and event["payload"].get("proposal_id") == proposal.id
        for event in repository.list_audit_events()
    )

    _, refreshed = _send(service, "что есть в нашей истории?", conversation_id)
    assert selected not in refreshed
    assert oldest in refreshed and newest in refreshed


def test_direct_forget_language_resolves_continuity_not_memory_storage(tmp_path, memory_path):
    service, _, provider = _service(tmp_path, memory_path)
    text = "какие состояния Маши использовать для длинных разговоров"
    conversation_id = _open_thread(service, text)

    _, answer = _send(service, f"забудь {text}", conversation_id)
    proposal = service.memory_intent_handler.proposal_store.current_for_conversation(
        conversation_id
    )

    assert provider.last_request is None
    assert proposal is not None
    assert proposal.record_type == "continuity_state"
    assert proposal.operation == "continuity_update"
    assert "Убрать открытую тему" in answer
    assert service.memory_intent_handler.shared_continuity.open_follow_ups()[0][1].status.value == "open"


def test_confirmed_memory_list_owns_exact_rendered_order_and_forgets_only_third_line(
    tmp_path,
    memory_path,
):
    service, repository, provider = _service(tmp_path, memory_path)

    conversation_id, rendered = _send(service, "Что ты помнишь?")
    presented = service.memory_intent_handler.presented_entity_set(conversation_id)

    assert presented is not None
    assert presented.source_kind == "confirmed_memory"
    assert len(presented.items) >= 3
    assert all(item.entity_kind is HumanEntityKind.MEMORY for item in presented.items)
    assert rendered.splitlines()[1 : 1 + len(presented.items)] == [
        f"{item.ordinal}. {item.human_label}" for item in presented.items
    ]
    selected = presented.items[2]
    other_ids = {item.entity_id for item in presented.items if item.entity_id != selected.entity_id}

    _, proposal_text = _send(service, "Маша удали третью строчку", conversation_id)
    proposal = service.memory_intent_handler.proposal_store.current_for_conversation(
        conversation_id
    )
    assert provider.last_request is None
    assert proposal is not None
    assert proposal.operation == "forget"
    assert proposal.target_record_id == selected.entity_id
    assert selected.human_label in proposal_text
    assert service.memory_intent_handler.memory_management.get(selected.entity_id).payload["visibility"] == "visible"

    _confirm(service, conversation_id)

    assert service.memory_intent_handler.memory_management.get(selected.entity_id).payload["visibility"] == "hidden"
    assert all(
        service.memory_intent_handler.memory_management.get(record_id).payload["visibility"] == "visible"
        for record_id in other_ids
    )
    _, refreshed = _send(service, "Что ты помнишь?", conversation_id)
    assert selected.human_label not in refreshed
    assert any(
        event["action"] == "memory_forget"
        and event["payload"].get("record_id") == selected.entity_id
        for event in repository.list_audit_events()
    )


@pytest.mark.parametrize(
    ("command", "ordinal"),
    (
        ("удали третью строчку", 3),
        ("убери вторую строку", 2),
        ("забудь первую запись", 1),
        ("удали пункт 3", 3),
        ("убери запись номер 2", 2),
    ),
)
def test_memory_list_accepts_bounded_natural_ordinal_vocabulary(
    tmp_path,
    memory_path,
    command,
    ordinal,
):
    service, _, provider = _service(tmp_path, memory_path)
    conversation_id, _ = _send(service, "Что ты помнишь?")
    presented = service.memory_intent_handler.presented_entity_set(conversation_id)
    assert presented is not None and len(presented.items) >= 3

    _, _ = _send(service, command, conversation_id)
    proposal = service.memory_intent_handler.proposal_store.current_for_conversation(
        conversation_id
    )

    assert provider.last_request is None
    assert proposal is not None and proposal.operation == "forget"
    assert proposal.target_record_id == presented.items[ordinal - 1].entity_id


@pytest.mark.parametrize(
    "alias",
    (
        "что есть в нашей истории?",
        "что у нас есть в истории?",
        "что у нас в истории?",
        "покажи нашу историю",
        "что сохранено в нашей истории?",
        "что есть в общей истории?",
    ),
)
def test_shared_history_aliases_are_application_lists_and_never_reach_qwen(
    tmp_path,
    memory_path,
    alias,
):
    case = tmp_path / str(abs(hash(alias)))
    case.mkdir()
    service, _, provider = _service(case, memory_path)
    conversation_id = _save_relationship(service, "наш вечер с телескопом")
    conversation_id = _open_thread(service, "выбрать окуляр", conversation_id)

    _, answer = _send(service, alias, conversation_id)
    presented = service.memory_intent_handler.presented_entity_set(conversation_id)

    assert provider.last_request is None
    assert answer.splitlines()[1:] == [
        "1. Воспоминание: наш вечер с телескопом",
        "2. Открытая тема: выбрать окуляр",
    ]
    assert presented is not None
    assert [item.human_label for item in presented.items] == [
        "наш вечер с телескопом",
        "выбрать окуляр",
    ]


def test_real_shared_history_alias_selects_second_line_without_mutating_before_confirmation(
    tmp_path,
    memory_path,
):
    service, _, provider = _service(tmp_path, memory_path)
    conversation_id = _save_relationship(service, "наш вечер с телескопом")
    conversation_id = _open_thread(service, "выбрать окуляр", conversation_id)

    _, _ = _send(service, "Маша что у нас есть в истории?", conversation_id)
    presented = service.memory_intent_handler.presented_entity_set(conversation_id)
    selected = presented.items[1]
    _, proposal_text = _send(service, "убери вторую строку", conversation_id)
    proposal = service.memory_intent_handler.proposal_store.current_for_conversation(
        conversation_id
    )

    assert provider.last_request is None
    assert selected.entity_kind is HumanEntityKind.CONTINUITY
    assert proposal is not None and proposal.operation == "continuity_update"
    assert selected.human_label in proposal_text
    assert any(
        follow_up.id == selected.entity_id
        for _, follow_up in service.memory_intent_handler.shared_continuity.open_follow_ups()
    )


def test_general_history_question_remains_model_owned_and_invalidates_selection(
    tmp_path,
    memory_path,
):
    service, _, provider = _service(tmp_path, memory_path)
    conversation_id, _ = _send(service, "Что ты помнишь?")
    assert service.memory_intent_handler.presented_entity_set(conversation_id) is not None
    provider.response_text = "Римская история началась задолго до империи."

    _, answer = _send(service, "Расскажи историю Рима", conversation_id)

    assert answer == provider.response_text
    assert provider.last_request is not None
    assert service.memory_intent_handler.presented_entity_set(conversation_id) is None


def test_new_application_list_replaces_old_selection_and_empty_list_clears_it(
    tmp_path,
    memory_path,
):
    service, _, _ = _service(tmp_path, memory_path)
    conversation_id = _save_relationship(service, "наш вечер с телескопом")
    conversation_id = _open_thread(service, "выбрать окуляр", conversation_id)
    _, _ = _send(service, "Что у нас в истории?", conversation_id)
    history_set = service.memory_intent_handler.presented_entity_set(conversation_id)
    assert history_set is not None and history_set.source_kind == "shared_history"

    _, _ = _send(service, "Что ты помнишь?", conversation_id)
    memory_set = service.memory_intent_handler.presented_entity_set(conversation_id)
    assert memory_set is not None and memory_set.source_kind == "confirmed_memory"
    assert memory_set != history_set

    _, missing = _send(
        service,
        "Что ты знаешь про мою подводную лодку?",
        conversation_id,
    )
    assert "ничего подходящего" in missing
    assert service.memory_intent_handler.presented_entity_set(conversation_id) is None


def test_direct_confirmed_fact_still_uses_memory_forget_proposal(tmp_path, memory_path):
    service, repository, _ = _service(tmp_path, memory_path)
    conversation_id, _ = _send(service, "Запомни, что я люблю блокноты в клетку")
    _confirm(service, conversation_id)

    _, answer = _send(service, "забудь блокноты в клетку", conversation_id)
    proposal = service.memory_intent_handler.proposal_store.current_for_conversation(
        conversation_id
    )

    assert proposal is not None
    assert proposal.record_type == "fact"
    assert proposal.operation == "forget"
    assert "воспоминание" in answer
    target = next(item for item in repository.read_document().facts if item.id == proposal.target_record_id)
    assert target.visibility.value == "visible"


def test_cross_kind_match_clarifies_and_deictic_topic_refinement_is_typed(tmp_path, memory_path):
    service, repository, provider = _service(tmp_path, memory_path)
    relationship = "обсудить модель для длинных разговоров"
    thread = "выбрать модель для длинных разговоров"
    conversation_id = _save_relationship(service, relationship)
    conversation_id = _open_thread(service, thread, conversation_id)

    _, clarification = _send(
        service,
        "убери модель для длинных разговоров",
        conversation_id,
    )

    assert "воспоминание" in clarification
    assert "открытая тема" in clarification
    assert service.memory_intent_handler.proposal_store.current_for_conversation(conversation_id) is None
    assert provider.last_request is None
    assert repository.read_document().relationship_memories[0].visibility.value == "visible"
    assert service.memory_intent_handler.shared_continuity.open_follow_ups()[0][1].status.value == "open"

    _, refined = _send(service, "вот эту про выбрать модель", conversation_id)
    proposal = service.memory_intent_handler.proposal_store.current_for_conversation(
        conversation_id
    )
    assert proposal is not None and proposal.operation == "continuity_update"
    assert thread in refined


def test_ordinal_without_application_list_fails_closed_without_model_call(tmp_path, memory_path):
    service, _, provider = _service(tmp_path, memory_path)

    conversation_id, answer = _send(service, "удали третью строчку")

    assert "Без списка приложения" in answer
    assert service.memory_intent_handler.proposal_store.current_for_conversation(conversation_id) is None
    assert provider.last_request is None


@pytest.mark.parametrize(
    "command",
    (
        "удали третью",
        "третью убери",
        "забудь третью",
        "убери третью по списку",
        "удали третью по списку",
    ),
)
def test_natural_ordinal_word_orders_select_exact_presented_item(
    tmp_path,
    memory_path,
    command,
):
    service, _, provider = _service(tmp_path, memory_path)
    conversation_id = _save_relationship(service, "наш первый общий вечер")
    selected = "выбрать модель для длинных разговоров"
    conversation_id = _open_thread(service, selected, conversation_id)
    conversation_id = _open_thread(service, "обсудить свет в комнате", conversation_id)
    _, _ = _send(service, "что есть в нашей истории?", conversation_id)

    _, answer = _send(service, command, conversation_id)
    proposal = service.memory_intent_handler.proposal_store.current_for_conversation(
        conversation_id
    )

    assert provider.last_request is None
    assert proposal is not None and proposal.operation == "continuity_update"
    assert selected in answer


def test_model_generated_numbered_prose_never_becomes_selection_truth(tmp_path, memory_path):
    service, _, provider = _service(tmp_path, memory_path)
    conversation_id = _save_relationship(service, "наш вечер с телескопом")
    conversation_id = _open_thread(service, "выбрать окуляр", conversation_id)
    conversation_id = _open_thread(service, "обсудить модель", conversation_id)
    _, _ = _send(service, "что есть в нашей истории?", conversation_id)
    assert service.memory_intent_handler.presented_entity_set(conversation_id) is not None

    provider.response_text = "1. Чай\n2. Кот\n3. Модель"
    conversation_id, model_answer = _send(
        service,
        "Придумай три случайных пункта для разговора",
        conversation_id,
    )
    model_request = provider.last_request

    _, answer = _send(service, "удали третью строчку", conversation_id)

    assert model_answer.startswith("1. Чай")
    assert service.memory_intent_handler.presented_entity_set(conversation_id) is None
    assert "Без списка приложения" in answer
    assert provider.last_request is model_request


def test_rejection_cancels_resolve_proposal_and_leaves_thread_open(tmp_path, memory_path):
    service, _, _ = _service(tmp_path, memory_path)
    text = "решить, какие состояния Маши оставить"
    conversation_id = _open_thread(service, text)
    _, _ = _send(service, f"забудь {text}", conversation_id)
    proposal = service.memory_intent_handler.proposal_store.current_for_conversation(
        conversation_id
    )
    assert proposal is not None

    _, cancelled = _send(service, "не сейчас", conversation_id)

    assert cancelled == "Хорошо, открытую тему не убираю."
    assert service.memory_intent_handler.shared_continuity.open_follow_ups()[0][1].summary == text
    assert service.memory_intent_handler.proposal_store.get(proposal.id).status.value == "cancelled"


@pytest.mark.parametrize(
    "claim",
    (
        "Хорошо, я убираю из памяти запись про состояния Маши.",
        "Убираю эту тему.",
        "Я убрала это из памяти.",
        "Уберу эту запись сейчас.",
    ),
)
def test_remove_execution_claim_is_blocked_without_receipt(claim):
    assert render_model_response(claim) == UNRECEIPTED_MUTATION_RESPONSE


def test_ordinary_physical_remove_language_is_allowed():
    ordinary = "Я убираю чашку со стола."

    assert render_model_response(ordinary) == ordinary
