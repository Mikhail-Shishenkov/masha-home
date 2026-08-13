from __future__ import annotations

import copy
import json
import time
from pathlib import Path

import pytest

from backend.conversation.conversation_service import ConversationService
from backend.conversation.conversation_store import ConversationStore
from backend.conversation.memory_intent import MemoryIntentHandler, MemoryProposalStore
from backend.identity.identity_kernel import IdentityKernel
from backend.identity.identity_store import IdentityStore
from backend.llm.fake_provider import FakeProvider
from backend.llm.model_router import ExternalContextDeniedError, ModelRouter
from backend.memory.confirmed_memory_service import ConfirmedMemoryService
from backend.memory.memory_retriever import (
    ContextLens,
    MemoryRetrievalRequest,
    MemoryRetriever,
)
from backend.memory.memory_store import MemoryStore
from backend.memory.working_memory import WorkingMemory

from tests.query_retrieval_fixture import PROJECT_ID, query_retrieval_document


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def query_retrieval_store(tmp_path: Path) -> MemoryStore:
    path = tmp_path / "query_retrieval_memory.json"
    path.write_text(
        json.dumps(query_retrieval_document(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return MemoryStore(path)


def _retrieve(
    store: MemoryStore,
    query: str,
    *,
    lens: ContextLens = ContextLens.GENERAL,
    limit: int = 6,
):
    return MemoryRetriever(store).retrieve(
        MemoryRetrievalRequest(
            query=query,
            project_id=PROJECT_ID,
            limit=limit,
            lens=lens,
        )
    )


def _ids(records: list[dict]) -> list[str]:
    return [record["data"]["id"] for record in records]


def test_acceptance_query_primary_local_model_prefers_decision_then_episode(
    query_retrieval_store: MemoryStore,
):
    records = _retrieve(
        query_retrieval_store,
        "Что мы решили насчёт основной локальной модели?",
    )

    assert _ids(records)[0] == "A_primary_local_model"
    assert "B_model_discussion" in _ids(records)
    assert not {"C_dev_memory_schema", "D_coffee_preference", "E_buy_tickets"} & set(
        _ids(records)
    )


def test_acceptance_query_drink_preference_returns_only_matching_fact(
    query_retrieval_store: MemoryStore,
):
    records = _retrieve(query_retrieval_store, "Помнишь, что я люблю пить?")

    assert _ids(records) == ["D_coffee_preference"]


def test_acceptance_query_model_discussion_returns_only_model_memories(
    query_retrieval_store: MemoryStore,
):
    records = _retrieve(query_retrieval_store, "Что мы обсуждали про модели?")

    assert _ids(records)[0] == "B_model_discussion"
    assert set(_ids(records)) == {
        "A_primary_local_model",
        "B_model_discussion",
        "G_model_long_context_thread",
    }


def test_acceptance_query_open_model_thread_prefers_continuity(
    query_retrieval_store: MemoryStore,
):
    records = _retrieve(
        query_retrieval_store,
        "Что у нас осталось про выбор модели для длинных разговоров?",
    )

    assert _ids(records)[0] == "G_model_long_context_thread"
    assert set(_ids(records)) <= {
        "A_primary_local_model",
        "B_model_discussion",
        "G_model_long_context_thread",
    }


def test_acceptance_shared_history_uses_only_shared_continuity_lens(
    query_retrieval_store: MemoryStore,
):
    records = _retrieve(
        query_retrieval_store,
        "Что есть в нашей истории?",
        lens=ContextLens.SHARED_CONTINUITY,
    )

    assert set(_ids(records)) == {"F_first_mvp", "G_model_long_context_thread"}
    assert {record["type"] for record in records} == {
        "relationship_memory",
        "continuity_state",
    }


def test_acceptance_current_perspective_uses_only_reflection_lens(
    query_retrieval_store: MemoryStore,
):
    records = _retrieve(
        query_retrieval_store,
        "Что ты сама думаешь о выборе модели?",
        lens=ContextLens.MASHA_PERSPECTIVE,
    )

    assert _ids(records) == ["H_model_perspective"]
    assert records[0]["type"] == "reflection"


@pytest.mark.parametrize(
    "query",
    [
        "Доброе утро)",
        "Как тебе погода сегодня?",
        "Какая у меня любимая книга?",
    ],
)
def test_acceptance_queries_without_memory_evidence_return_empty(
    query_retrieval_store: MemoryStore,
    query: str,
):
    assert _retrieve(query_retrieval_store, query) == []


def test_trace_explains_scores_thresholds_and_budget_without_changing_results(
    query_retrieval_store: MemoryStore,
):
    result = MemoryRetriever(query_retrieval_store).retrieve_with_trace(
        MemoryRetrievalRequest(
            query="Какую основную локальную модель мы выбрали?",
            project_id=PROJECT_ID,
            limit=1,
        )
    )

    assert _ids(list(result.records)) == ["A_primary_local_model"]
    selected = next(item for item in result.trace if item.selected)
    irrelevant = next(item for item in result.trace if item.record_id == "E_buy_tickets")
    assert selected.components.lexical >= selected.lexical_threshold
    assert selected.components.importance <= 0.55
    assert selected.components.recency <= 0.30
    assert "selected_by_score" in selected.reasons
    assert irrelevant.passed_threshold is False
    assert "below_relevance_threshold" in irrelevant.reasons


def test_record_and_total_context_budgets_are_enforced(
    query_retrieval_store: MemoryStore,
):
    query_retrieval_store.data["decisions"][0]["decision"] += " локальная модель" * 500
    retriever = MemoryRetriever(query_retrieval_store)
    oversized = retriever.retrieve_with_trace(
        MemoryRetrievalRequest(
            query="локальная модель",
            project_id=PROJECT_ID,
            limit=6,
            max_record_chars=500,
        )
    )
    bounded = retriever.retrieve_with_trace(
        MemoryRetrievalRequest(
            query="локальная модель",
            project_id=PROJECT_ID,
            limit=6,
            memory_budget_chars=256,
        )
    )

    decision_trace = next(
        item for item in oversized.trace if item.record_id == "A_primary_local_model"
    )
    assert decision_trace.selected is False
    assert "record_budget_exceeded" in decision_trace.reasons
    assert bounded.estimated_chars <= 256
    assert len(bounded.records) <= 6


def test_optional_semantic_failure_falls_back_to_deterministic_lexical(
    query_retrieval_store: MemoryStore,
):
    class UnavailableSemanticScorer:
        def score_many(self, query, candidate_texts):
            raise RuntimeError("local semantic component unavailable")

    request = MemoryRetrievalRequest(
        query="Помнишь, что я люблю пить?",
        project_id=PROJECT_ID,
    )
    lexical = MemoryRetriever(query_retrieval_store).retrieve(request)
    fallback = MemoryRetriever(
        query_retrieval_store,
        semantic_scorer=UnavailableSemanticScorer(),
    ).retrieve(request)

    assert _ids(fallback) == _ids(lexical) == ["D_coffee_preference"]
    assert "semantic_fallback_to_lexical" in fallback[0]["reasons"]
    assert fallback[0]["components"]["semantic"] == 0.0


def test_hidden_and_inactive_records_never_become_candidates(
    query_retrieval_store: MemoryStore,
):
    hidden = copy.deepcopy(query_retrieval_store.data["facts"][1])
    hidden.update({"id": "hidden_coffee", "visibility": "hidden", "importance": 1.0})
    inactive = copy.deepcopy(query_retrieval_store.data["decisions"][0])
    inactive.update(
        {
            "id": "cancelled_model",
            "status": "cancelled",
            "importance": 1.0,
        }
    )
    query_retrieval_store.data["facts"].append(hidden)
    query_retrieval_store.data["decisions"].append(inactive)

    coffee = _retrieve(query_retrieval_store, "люблю пить кофе")
    model = _retrieve(query_retrieval_store, "основная локальная модель")

    assert "hidden_coffee" not in _ids(coffee)
    assert "cancelled_model" not in _ids(model)


def test_conversation_retrieves_different_context_per_turn_and_can_send_empty(
    tmp_path: Path,
    query_retrieval_store: MemoryStore,
):
    provider = FakeProvider(provider_id="ollama-local", response_text="Я здесь.")
    service = ConversationService(
        identity_kernel=IdentityKernel(
            IdentityStore(PROJECT_ROOT / "identity" / "masha.identity.json")
        ),
        memory_retriever=MemoryRetriever(query_retrieval_store),
        working_memory=WorkingMemory(),
        router=ModelRouter([provider]),
        history=ConversationStore(tmp_path / "history.json"),
    )

    conversation_id, _ = service.send(
        "Что мы решили про локальные модели?",
        project_id=PROJECT_ID,
    )
    model_context = list(provider.last_request.private_context["memory_context"])
    service.send(
        "Помнишь, что я люблю пить?",
        project_id=PROJECT_ID,
        conversation_id=conversation_id,
    )
    drink_context = list(provider.last_request.private_context["memory_context"])
    service.send("Доброе утро", project_id=PROJECT_ID, conversation_id=conversation_id)
    greeting_context = list(provider.last_request.private_context["memory_context"])

    assert model_context
    assert {item["id"] for item in model_context} <= {
        "A_primary_local_model",
        "B_model_discussion",
        "G_model_long_context_thread",
    }
    assert "B_model_discussion" in {item["id"] for item in model_context}
    assert [item["id"] for item in drink_context] == ["D_coffee_preference"]
    assert greeting_context == []
    assert all("components" not in item and "total_score" not in item for item in model_context)


@pytest.mark.parametrize(
    "message",
    (
        "Какие у нас дела?",
        "Забудь learning_python",
        "Закрой нить про выбор модели",
        "Напомни через две минуты сказать мяу",
    ),
)
def test_explicit_capability_routes_still_run_before_retrieval(
    tmp_path: Path,
    query_retrieval_store: MemoryStore,
    message: str,
):
    class RetrievalMustNotRun:
        def retrieve(self, request):
            raise AssertionError("broad retrieval ran before explicit capability routing")

    provider = FakeProvider(provider_id="ollama-local", response_text="should not run")
    service = ConversationService(
        identity_kernel=IdentityKernel(
            IdentityStore(PROJECT_ROOT / "identity" / "masha.identity.json")
        ),
        memory_retriever=RetrievalMustNotRun(),
        working_memory=WorkingMemory(),
        router=ModelRouter([provider]),
        history=ConversationStore(tmp_path / "history.json"),
        memory_intent_handler=MemoryIntentHandler(
            proposal_store=MemoryProposalStore(tmp_path / "proposals.json"),
            confirmed_memory=ConfirmedMemoryService(query_retrieval_store),
        ),
    )

    _, response = service.send(message, project_id=PROJECT_ID)

    assert response
    assert provider.last_request is None


def test_query_selected_memory_is_never_sent_to_an_external_provider(
    tmp_path: Path,
    query_retrieval_store: MemoryStore,
):
    external = FakeProvider(provider_id="ollama-local", is_local=False)
    service = ConversationService(
        identity_kernel=IdentityKernel(
            IdentityStore(PROJECT_ROOT / "identity" / "masha.identity.json")
        ),
        memory_retriever=MemoryRetriever(query_retrieval_store),
        working_memory=WorkingMemory(),
        router=ModelRouter([external]),
        history=ConversationStore(tmp_path / "history.json"),
    )

    with pytest.raises(ExternalContextDeniedError):
        service.send(
            "Что мы решили насчёт основной локальной модели?",
            project_id=PROJECT_ID,
        )

    assert external.last_request is None


def test_retrieval_is_interactive_on_one_thousand_local_records(
    query_retrieval_store: MemoryStore,
):
    template = query_retrieval_store.data["facts"][0]
    for index in range(1_000):
        noise = copy.deepcopy(template)
        noise.update(
            {
                "id": f"noise_{index:04d}",
                "subject": "архивная заметка",
                "key": f"случайный ключ {index}",
                "value": f"нерелевантный материал {index}",
                "importance": 0.99,
            }
        )
        query_retrieval_store.data["facts"].append(noise)

    started = time.perf_counter()
    records = _retrieve(
        query_retrieval_store,
        "Что мы решили насчёт основной локальной модели?",
    )
    elapsed = time.perf_counter() - started

    assert _ids(records)[0] == "A_primary_local_model"
    assert elapsed < 2.0
