from __future__ import annotations

import json
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from backend.application.human_information import (
    HumanAvailability,
    HumanInformationService,
    HumanRecallRequest,
    HumanSearchRequest,
    HumanSearchScope,
    HumanTimeFilter,
    HumanTimePreset,
    RecallMode,
)
from backend.conversation.conversation_models import ConversationMessageOrigin, ConversationRole
from backend.conversation.conversation_service import ConversationService
from backend.conversation.memory_intent import MemoryIntentHandler, MemoryProposalStore
from backend.identity.identity_kernel import IdentityKernel
from backend.identity.identity_store import IdentityStore
from backend.llm.fake_provider import FakeProvider
from backend.llm.model_router import ModelRouter
from backend.memory.confirmed_memory_service import ConfirmedMemoryService
from backend.memory.memory_management import MemoryManagementService, MemoryMutationOperation
from backend.memory.memory_models import MemoryDocument
from backend.memory.memory_retriever import MemoryRetriever
from backend.memory.sqlite_repository import MemorySqliteRepository
from backend.memory.working_memory import WorkingMemory
from backend.conversation.conversation_store import ConversationStore

from tests.human_information_fixture import (
    ACTIVE_MAC_ID,
    COMPLETED_MAC_TASK_ID,
    CURRENT_MODEL_DECISION_ID,
    FORGOTTEN_MAC_ID,
    MAC_EPISODE_ID,
    OLD_MODEL_DECISION_ID,
    OPEN_MAC_TASK_ID,
    OPEN_THREAD_ID,
    REJECTED_CANDIDATE_ID,
    RESOLVED_THREAD_ID,
    human_information_document,
)
from tests.query_retrieval_fixture import PROJECT_ID


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime.fromisoformat("2026-08-14T12:00:00+04:00")


@pytest.fixture
def human_repository(tmp_path: Path) -> MemorySqliteRepository:
    repository = MemorySqliteRepository(tmp_path / "human.sqlite3")
    repository.replace_document(
        MemoryDocument.model_validate(human_information_document()),
        action="test_human_information_fixture",
    )
    return repository


@pytest.fixture
def human_service(human_repository: MemorySqliteRepository) -> HumanInformationService:
    return HumanInformationService(human_repository, clock=lambda: NOW)


def _ids(result) -> set[str]:
    return {match.item.ref.entity_id for match in result.matches}


def test_lifecycle_normalization_matrix_and_excluded_candidates(human_service):
    items = {item.ref.entity_id: item for item in human_service.information_items()}

    assert items[ACTIVE_MAC_ID].availability is HumanAvailability.ACTIVE
    assert items[FORGOTTEN_MAC_ID].availability is HumanAvailability.FORGOTTEN
    assert items[OLD_MODEL_DECISION_ID].availability is HumanAvailability.ARCHIVED
    assert items[CURRENT_MODEL_DECISION_ID].availability is HumanAvailability.ACTIVE
    assert items[MAC_EPISODE_ID].availability is HumanAvailability.ACTIVE
    assert items[COMPLETED_MAC_TASK_ID].availability is HumanAvailability.ARCHIVED
    assert items[OPEN_MAC_TASK_ID].availability is HumanAvailability.ACTIVE
    assert items[RESOLVED_THREAD_ID].availability is HumanAvailability.ARCHIVED
    assert items[OPEN_THREAD_ID].availability is HumanAvailability.ACTIVE
    assert items[RESOLVED_THREAD_ID].timestamp is None
    assert REJECTED_CANDIDATE_ID not in items
    assert all(item.record_type not in {"reflection", "affective_record", "memory_candidate"} for item in items.values())


def test_mixed_mac_search_is_relevant_humanized_and_excludes_forgotten(human_service):
    result = human_service.search_information(HumanSearchRequest(query="MacBook"))
    ids = _ids(result)

    assert {ACTIVE_MAC_ID, MAC_EPISODE_ID, COMPLETED_MAC_TASK_ID, RESOLVED_THREAD_ID} <= ids
    assert FORGOTTEN_MAC_ID not in ids
    assert REJECTED_CANDIDATE_ID not in ids
    assert all(match.relevance >= 0.24 for match in result.matches)
    assert all(match.item.ref.entity_id not in match.item.label for match in result.matches)


def test_search_scopes_defaults_no_match_and_time_filters(human_service):
    tasks = human_service.search_information(HumanSearchRequest(
        query="MacBook", scope=HumanSearchScope.TASKS,
    ))
    history = human_service.search_information(HumanSearchRequest(
        query="MacBook", scope=HumanSearchScope.HISTORY,
    ))
    no_match = human_service.search_information(HumanSearchRequest(query="ананасовый телескоп"))
    today = human_service.search_information(HumanSearchRequest(
        query="MacBook",
        time_filter=HumanTimeFilter(preset=HumanTimePreset.TODAY),
    ))
    last_7 = human_service.search_information(HumanSearchRequest(
        query="MacBook",
        time_filter=HumanTimeFilter(preset=HumanTimePreset.LAST_7_DAYS),
    ))
    explicit = human_service.search_information(HumanSearchRequest(
        query="MacBook",
        time_filter=HumanTimeFilter(
            start_date=date(2026, 8, 8), end_date=date(2026, 8, 8),
        ),
    ))

    assert {match.item.kind.value for match in tasks.matches} == {"task"}
    assert all(match.item.kind.value != "task" for match in history.matches)
    assert no_match.matches == ()
    assert today.matches == ()
    assert {ACTIVE_MAC_ID, COMPLETED_MAC_TASK_ID, OPEN_MAC_TASK_ID} <= _ids(last_7)
    assert _ids(explicit) == {MAC_EPISODE_ID}
    assert RESOLVED_THREAD_ID not in _ids(last_7)  # no trustworthy own timestamp


def test_search_humanizes_internal_fact_keys_without_changing_searchable_text(human_repository, human_service):
    document = human_repository.read_document()
    template = document.facts[0]
    internal = template.model_copy(update={
        "id": "10101010-1010-4010-8010-101010101010",
        "subject": "misha",
        "key": "learning_python",
        "value": "Изучает Python внутри проекта Masha Home",
    })
    ordinary = template.model_copy(update={
        "id": "20202020-2020-4020-8020-202020202020",
        "subject": "Миша",
        "key": "любимый напиток",
        "value": "чай без сахара",
    })
    human_repository.replace_document(
        document.model_copy(update={"facts": [*document.facts, internal, ordinary]}),
        action="test_search_human_labels",
    )

    by_internal_key = human_service.search_information(HumanSearchRequest(query="learning_python"))
    by_value = human_service.search_information(HumanSearchRequest(query="Python"))
    ordinary_result = human_service.search_information(HumanSearchRequest(query="чай без сахара"))
    internal_label = next(match.item.label for match in by_value.matches if match.item.ref.entity_id == internal.id)
    ordinary_label = next(match.item.label for match in ordinary_result.matches if match.item.ref.entity_id == ordinary.id)

    assert internal.id in _ids(by_internal_key)  # relevance still sees internal searchable text
    assert internal_label == "Память · актуально — Изучает Python внутри проекта Masha Home"
    assert "misha" not in internal_label.casefold()
    assert "learning_python" not in internal_label
    assert internal.id not in internal_label
    assert ordinary_label == "Миша: любимый напиток — чай без сахара"


def test_current_retrospective_task_thread_and_forgotten_recall(human_service):
    current = human_service.recall_information(HumanRecallRequest(
        query="Нашёл ещё один M2 Pro за 115 тысяч.", mode=RecallMode.CURRENT,
        project_id=PROJECT_ID,
    ))
    current_decision = human_service.recall_information(HumanRecallRequest(
        query="Какая основная модель Mac-проекта?", mode=RecallMode.CURRENT,
        project_id=PROJECT_ID,
    ))
    past = human_service.recall_information(HumanRecallRequest(
        query="Помнишь, мы Mac выбирали?", mode=RecallMode.RETROSPECTIVE,
        project_id=PROJECT_ID,
    ))
    completed = human_service.recall_information(HumanRecallRequest(
        query="Что я уже сделал по MacBook?", project_id=PROJECT_ID,
    ))
    open_tasks = human_service.recall_information(HumanRecallRequest(
        query="Что мне ещё надо сделать по MacBook?", project_id=PROJECT_ID,
    ))
    resolved = human_service.recall_information(HumanRecallRequest(
        query="Мы раньше обсуждали состояния Маши для длинных разговоров?",
        project_id=PROJECT_ID,
    ))
    forgotten = human_service.recall_information(HumanRecallRequest(
        query="Что я просил тебя забыть про MacBook?", project_id=PROJECT_ID,
    ))

    current_text = json.dumps(current.working_context, ensure_ascii=False)
    current_decision_text = json.dumps(current_decision.working_context, ensure_ascii=False)
    past_text = json.dumps(past.working_context, ensure_ascii=False)
    completed_text = json.dumps(completed.working_context, ensure_ascii=False)
    open_text = json.dumps(open_tasks.working_context, ensure_ascii=False)
    resolved_text = json.dumps(resolved.working_context, ensure_ascii=False)
    forgotten_text = json.dumps(forgotten.working_context, ensure_ascii=False)
    assert "M2 Pro" in current_text and "секретная забытая" not in current_text
    assert "Qwen B" in current_decision_text and "Qwen A" not in current_decision_text
    assert "Qwen A" in past_text and "Qwen B" in past_text
    assert "Проверить батарею" in completed_text and "Позвонить продавцу" not in completed_text
    assert "Позвонить продавцу" in open_text and "Проверить батарею" not in open_text
    assert "состояния Маши" in resolved_text
    assert "секретная забытая" in forgotten_text
    assert forgotten.mode is RecallMode.FORGOTTEN_REVIEW


def _conversation(tmp_path, repository):
    provider = FakeProvider(provider_id="ollama-local", response_text="Я здесь.")
    proposals = MemoryProposalStore(tmp_path / "proposals.json")
    management = MemoryManagementService(repository)
    human = HumanInformationService(
        repository,
        memory_management=management,
        clock=lambda: NOW,
        proposal_store=proposals,
    )
    handler = MemoryIntentHandler(
        proposal_store=proposals,
        confirmed_memory=ConfirmedMemoryService(repository),
        memory_management=management,
        human_information=human,
    )
    service = ConversationService(
        identity_kernel=IdentityKernel(IdentityStore(ROOT / "identity" / "masha.identity.json")),
        memory_retriever=MemoryRetriever(repository, clock=lambda: NOW),
        working_memory=WorkingMemory(max_items=6),
        router=ModelRouter([provider]),
        history=ConversationStore(tmp_path / "history.json"),
        memory_intent_handler=handler,
        human_information=human,
    )
    return service, provider, human


def test_forgotten_review_restore_requires_confirmation_and_preserves_state(tmp_path, human_repository):
    service, provider, _ = _conversation(tmp_path, human_repository)
    conversation_id, review = service.send(
        "Что я просил тебя забыть про MacBook?", project_id=PROJECT_ID,
    )
    before = MemoryManagementService(human_repository).get(FORGOTTEN_MAC_ID)
    _, proposal_text = service.send(
        "Верни её", project_id=PROJECT_ID, conversation_id=conversation_id,
    )
    pending = service.memory_intent_handler.proposal_store.current_for_conversation(conversation_id)

    assert "забыто" in review
    assert FORGOTTEN_MAC_ID not in review
    assert "Подтверди" in proposal_text
    assert pending is not None and pending.operation == "restore"
    assert before.payload["visibility"] == "hidden"

    _, confirmation = service.send("да", project_id=PROJECT_ID, conversation_id=conversation_id)
    restored = MemoryManagementService(human_repository).get(FORGOTTEN_MAC_ID)
    assert "снова доступна" in confirmation
    assert restored.payload["visibility"] == "visible"
    assert restored.payload["status"] == before.payload["status"] == "active"
    assert any(event["action"] == "memory_restore" for event in human_repository.list_audit_events())
    assert provider.last_request is None


def test_restored_memory_state_is_authoritative_over_prior_mutation_turns(tmp_path, human_repository):
    service, provider, _ = _conversation(tmp_path, human_repository)
    conversation_id, _ = service.send(
        "Что я просил тебя забыть про MacBook?", project_id=PROJECT_ID,
    )
    service.send("Верни её", project_id=PROJECT_ID, conversation_id=conversation_id)
    service.send("да", project_id=PROJECT_ID, conversation_id=conversation_id)

    provider.response_text = "Ты предпочитаешь MacBook M2 Pro."
    _, answer = service.send(
        "Какой MacBook я предпочитаю?", project_id=PROJECT_ID,
        conversation_id=conversation_id,
    )

    request = provider.last_request
    model_history = "\n".join(message.content for message in request.messages)
    memory_context = json.dumps(request.private_context["memory_context"], ensure_ascii=False)
    assert answer == "Ты предпочитаешь MacBook M2 Pro."
    assert "Верни её" not in model_history
    assert "подтверждаю" not in model_history.casefold()
    assert "секретная забытая цена" in memory_context


def test_restore_of_hidden_superseded_record_returns_to_archived_not_current(tmp_path, human_repository):
    management = MemoryManagementService(human_repository)
    management.apply(
        operation=MemoryMutationOperation.FORGET,
        record_id=OLD_MODEL_DECISION_ID,
        proposal_id="superseded-restore-setup",
    )
    proposals = MemoryProposalStore(tmp_path / "superseded-proposals.json")
    human = HumanInformationService(
        human_repository,
        memory_management=management,
        proposal_store=proposals,
        clock=lambda: NOW,
    )
    human.restore_information(
        record_id=OLD_MODEL_DECISION_ID,
        conversation_id="superseded-restore",
    )
    handler = MemoryIntentHandler(
        proposal_store=proposals,
        confirmed_memory=ConfirmedMemoryService(human_repository),
        memory_management=management,
        human_information=human,
    )

    result = handler.handle(
        "да",
        conversation_id="superseded-restore",
        project_id=PROJECT_ID,
    )
    item = next(
        value for value in human.information_items()
        if value.ref.entity_id == OLD_MODEL_DECISION_ID
    )
    assert result.handled and "снова доступна" in result.response
    assert management.get(OLD_MODEL_DECISION_ID).payload["status"] == "superseded"
    assert item.availability is HumanAvailability.ARCHIVED


def test_conversation_search_reuses_presented_entity_ordinals_for_readback(tmp_path, human_repository):
    service, provider, _ = _conversation(tmp_path, human_repository)
    conversation_id, rendered = service.send(
        "Найди дело про батарею MacBook", project_id=PROJECT_ID,
    )
    presented = service.memory_intent_handler.presented_entity_set(conversation_id)

    assert presented is not None
    completed = next(item for item in presented.items if item.entity_id == COMPLETED_MAC_TASK_ID)
    assert COMPLETED_MAC_TASK_ID not in rendered
    reference = "первой" if completed.ordinal == 1 else str(completed.ordinal)
    _, readback = service.send(
        f"Что было в {reference}?", project_id=PROJECT_ID, conversation_id=conversation_id,
    )
    assert "Проверить батарею MacBook" in readback
    assert provider.last_request is None


def test_actual_model_request_has_useful_context_without_internal_ids_or_trace(tmp_path, human_repository):
    service, provider, _ = _conversation(tmp_path, human_repository)
    service.send("Нашёл ещё один M2 Pro за 115 тысяч.", project_id=PROJECT_ID)

    request = provider.last_request
    serialized = json.dumps(request.model_dump(mode="json"), ensure_ascii=False)
    memory_context = request.private_context["memory_context"]
    assert memory_context and "M2 Pro" in json.dumps(memory_context, ensure_ascii=False)
    assert service.last_recall_result.trace  # internal trace remains inspectable
    assert re.search(r"[0-9a-f]{8}-[0-9a-f-]{27,}", serialized, re.IGNORECASE) is None
    for forbidden in (
        "record_id", "candidate_id", "memory_reference", "retrieval_reasons",
        "total_score", "relevance_score", "sqlite", ACTIVE_MAC_ID,
        "relationshipmemory", "continuitystate", "mashareflection",
    ):
        assert forbidden not in serialized.casefold()


def test_exact_recall_phrases_flow_through_conversation_to_bounded_working_context(tmp_path, human_repository):
    service, provider, _ = _conversation(tmp_path, human_repository)
    conversation_id, _ = service.send(
        "Нашёл ещё один M2 Pro за 115 тысяч.", project_id=PROJECT_ID,
    )
    current = json.dumps(provider.last_request.private_context["memory_context"], ensure_ascii=False)
    service.send(
        "Помнишь, мы Mac выбирали?", project_id=PROJECT_ID,
        conversation_id=conversation_id,
    )
    retrospective = json.dumps(provider.last_request.private_context["memory_context"], ensure_ascii=False)
    service.send(
        "Что я уже сделал по этому поводу?", project_id=PROJECT_ID,
        conversation_id=conversation_id,
    )
    completed = json.dumps(provider.last_request.private_context["memory_context"], ensure_ascii=False)
    service.send(
        "Увидел ещё один MacBook в магазине.", project_id=PROJECT_ID,
        conversation_id=conversation_id,
    )
    ordinary = json.dumps(provider.last_request.private_context["memory_context"], ensure_ascii=False)

    assert "M2 Pro" in current
    assert "Qwen A" in retrospective and "Qwen B" in retrospective
    assert "Проверить батарею MacBook" in completed
    assert "Позвонить продавцу" not in completed
    assert "секретная забытая цена" not in ordinary
    assert len(provider.last_request.private_context["memory_context"]) <= 6


def test_stale_application_list_stays_in_transcript_but_not_model_history(tmp_path, human_repository):
    service, provider, _ = _conversation(tmp_path, human_repository)
    conversation_id, rendered = service.send("Что ты помнишь про MacBook?", project_id=PROJECT_ID)
    presented = service.memory_intent_handler.presented_entity_set(conversation_id)
    selected = next(item for item in presented.items if item.entity_id == ACTIVE_MAC_ID)
    service.send(
        f"убери {selected.ordinal} по списку",
        project_id=PROJECT_ID,
        conversation_id=conversation_id,
    )
    service.send("да", project_id=PROJECT_ID, conversation_id=conversation_id)
    service.send(
        "Нашёл MacBook другого цвета.",
        project_id=PROJECT_ID,
        conversation_id=conversation_id,
    )

    request = provider.last_request
    model_history = "\n".join(message.content for message in request.messages)
    context = json.dumps(request.private_context["memory_context"], ensure_ascii=False)
    transcript = service.history.messages(conversation_id)
    assert rendered in {item.content for item in transcript if item.origin is ConversationMessageOrigin.APPLICATION}
    assert rendered not in model_history
    assert "до 120 тысяч" not in context
    assert MemoryManagementService(human_repository).get(ACTIVE_MAC_ID).payload["visibility"] == "hidden"


def test_human_search_and_recall_stay_interactive_around_one_thousand_records(human_repository):
    document = human_repository.read_document()
    template = document.facts[0]
    facts = list(document.facts)
    for index in range(1_000):
        facts.append(template.model_copy(update={
            "id": f"noise_human_{index:04d}",
            "subject": "нерелевантная заметка",
            "key": f"случайность {index}",
            "value": f"обычный шум {index}",
        }))
    human_repository.replace_document(
        document.model_copy(update={"facts": facts}),
        action="test_human_information_scale",
    )
    service = HumanInformationService(human_repository, clock=lambda: NOW)
    search_samples = []
    recall_samples = []
    for _ in range(12):
        started = time.perf_counter()
        service.search_information(HumanSearchRequest(query="MacBook"))
        search_samples.append(time.perf_counter() - started)
        started = time.perf_counter()
        service.recall_information(HumanRecallRequest(
            query="Помнишь, мы Mac выбирали?", mode=RecallMode.RETROSPECTIVE,
        ))
        recall_samples.append(time.perf_counter() - started)
    search_samples.sort()
    recall_samples.sort()
    assert search_samples[int(len(search_samples) * 0.95) - 1] < 2.0
    assert recall_samples[int(len(recall_samples) * 0.95) - 1] < 2.0
