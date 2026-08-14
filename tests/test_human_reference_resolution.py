"""Acceptance coverage for application-owned human reference resolution."""

from pathlib import Path

import pytest

from backend.conversation.conversation_service import ConversationService
from backend.conversation.conversation_store import ConversationStore
from backend.conversation.human_reference import HumanEntityKind
from backend.conversation.memory_intent import MemoryIntentHandler, MemoryProposalStore
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


def _service(tmp_path, memory_path):
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
