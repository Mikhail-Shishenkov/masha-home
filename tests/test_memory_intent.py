import json

from backend.conversation.memory_intent import (
    MemoryIntentHandler,
    MemoryProposalStore,
    ProposalStatus,
)
from backend.memory.confirmed_memory_service import ConfirmedMemoryService
from backend.memory.memory_retriever import MemoryRetriever
from backend.memory.memory_store import MemoryStore


PROJECT_ID = "project_masha_home"


def _handler(tmp_path, store):
    proposal_store = MemoryProposalStore(tmp_path / "memory-proposals.json")
    return MemoryIntentHandler(
        proposal_store=proposal_store,
        confirmed_memory=ConfirmedMemoryService(store),
    ), proposal_store


def test_explicit_fact_creates_a_pending_proposal_without_memory_mutation(tmp_path, memory_path):
    store = MemoryStore(memory_path)
    handler, proposals = _handler(tmp_path, store)
    original = json.dumps(store.data, sort_keys=True)

    result = handler.handle(
        "Маша, запомни, что я предпочитаю локальные модели",
        conversation_id="conversation-1",
        project_id=PROJECT_ID,
    )

    pending = proposals.pending_for_conversation("conversation-1")
    assert result.handled is True
    assert "как факт" in result.response
    assert len(pending) == 1
    assert pending[0].record_type == "fact"
    assert pending[0].status == ProposalStatus.PENDING
    assert json.dumps(store.data, sort_keys=True) == original


def test_confirmation_persists_fact_and_retriever_finds_it_after_restart(tmp_path, memory_path):
    store = MemoryStore(memory_path)
    handler, proposals = _handler(tmp_path, store)
    original_counts = {
        name: len(store.data[name])
        for name in ("facts", "decisions", "commitments", "episodes")
    }
    handler.handle(
        "Запомни, что я предпочитаю локальные модели",
        conversation_id="conversation-1",
        project_id=PROJECT_ID,
    )
    proposal = proposals.pending_for_conversation("conversation-1")[0]

    result = handler.handle("Да", conversation_id="conversation-1", project_id=PROJECT_ID)
    restarted_store = MemoryStore(memory_path)
    restarted_proposals = MemoryProposalStore(tmp_path / "memory-proposals.json")

    assert result.response == "Готово, сохранила."
    assert restarted_proposals.get(proposal.id).status == ProposalStatus.CONFIRMED
    assert any(
        item["data"]["id"] == proposal.record_payload["id"]
        for item in MemoryRetriever(restarted_store).retrieve(project_id=PROJECT_ID, limit=20)
    )
    assert len(restarted_store.data["facts"]) == original_counts["facts"] + 1
    assert all(
        len(restarted_store.data[name]) == original_counts[name]
        for name in ("decisions", "commitments", "episodes")
    )


def test_reject_and_repeated_confirmation_do_not_mutate_memory(tmp_path, memory_path):
    store = MemoryStore(memory_path)
    handler, proposals = _handler(tmp_path, store)
    original = json.dumps(store.data, sort_keys=True)
    handler.handle("Запомни, что я предпочитаю локальные модели", conversation_id="c", project_id=PROJECT_ID)
    proposal = proposals.pending_for_conversation("c")[0]

    rejected = handler.handle("Нет", conversation_id="c", project_id=PROJECT_ID)
    repeated = handler.handle(f"Да {proposal.id}", conversation_id="c", project_id=PROJECT_ID)

    assert rejected.response == "Хорошо, не сохраняю."
    assert repeated.response == "Это предложение уже отменено; ничего не сохраняла."
    assert proposals.get(proposal.id).status == ProposalStatus.CANCELLED
    assert json.dumps(store.data, sort_keys=True) == original


def test_repeated_confirmation_is_idempotent(tmp_path, memory_path):
    store = MemoryStore(memory_path)
    handler, proposals = _handler(tmp_path, store)
    handler.handle("Запомни, что я предпочитаю локальные модели", conversation_id="c", project_id=PROJECT_ID)
    proposal = proposals.pending_for_conversation("c")[0]

    first = handler.handle(f"Да {proposal.id}", conversation_id="c", project_id=PROJECT_ID)
    second = handler.handle(f"Да {proposal.id}", conversation_id="c", project_id=PROJECT_ID)

    assert first.response == "Готово, сохранила."
    assert second.response == "Эта запись уже сохранена."
    assert sum(item["id"] == proposal.record_payload["id"] for item in store.data["facts"]) == 1


def test_confirmation_is_bound_to_a_specific_proposal_when_two_are_pending(tmp_path, memory_path):
    store = MemoryStore(memory_path)
    handler, proposals = _handler(tmp_path, store)
    handler.handle("Запомни, что я предпочитаю локальные модели", conversation_id="c", project_id=PROJECT_ID)
    handler.handle("Запомни как решение проекта, что primary model — qwen3.5:9b", conversation_id="c", project_id=PROJECT_ID)
    first, second = proposals.pending_for_conversation("c")

    ambiguous = handler.handle("Да", conversation_id="c", project_id=PROJECT_ID)
    confirmed = handler.handle(f"Да {first.id}", conversation_id="c", project_id=PROJECT_ID)

    assert "несколько предложений" in ambiguous.response
    assert confirmed.response == "Готово, сохранила."
    assert proposals.get(first.id).status == ProposalStatus.CONFIRMED
    assert proposals.get(second.id).status == ProposalStatus.PENDING
    assert store.get_fact(first.record_payload["id"]) is not None
    assert all(item["id"] != second.record_payload["id"] for item in store.data["decisions"])


def test_explicit_decision_is_proposed_and_ordinary_statement_is_not_handled(tmp_path, memory_path):
    store = MemoryStore(memory_path)
    handler, proposals = _handler(tmp_path, store)

    ordinary = handler.handle("Я предпочитаю локальные модели", conversation_id="c", project_id=PROJECT_ID)
    proposal = handler.handle(
        "Запомни как решение проекта, что primary model — qwen3.5:9b",
        conversation_id="c",
        project_id=PROJECT_ID,
    )

    assert ordinary.handled is False
    assert proposal.handled is True
    assert proposals.pending_for_conversation("c")[0].record_type == "decision"


def test_explicit_deadline_creates_commitment_proposal_deterministically(tmp_path, memory_path):
    handler, proposals = _handler(tmp_path, MemoryStore(memory_path))
    result = handler.handle("Запомни, что завтра в 18:00 нужно отправить отчёт", conversation_id="c", project_id=PROJECT_ID)
    proposal = proposals.pending_for_conversation("c")[0]

    assert proposal.record_type == "commitment"
    assert proposal.record_payload["due_at"] is not None
    assert "отправить отчёт" in result.response


def test_incomplete_explicit_memory_request_asks_for_type_instead_of_guessing(tmp_path, memory_path):
    handler, proposals = _handler(tmp_path, MemoryStore(memory_path))

    result = handler.handle("Запомни", conversation_id="c", project_id=PROJECT_ID)

    assert result.handled is True
    assert "факт, решение, обязательство или эпизод" in result.response
    assert proposals.pending_for_conversation("c") == ()


def test_pending_proposal_survives_restart_without_becoming_production_memory(tmp_path, memory_path):
    store = MemoryStore(memory_path)
    handler, proposals = _handler(tmp_path, store)
    handler.handle("Запомни, что я предпочитаю локальные модели", conversation_id="c", project_id=PROJECT_ID)
    proposal = proposals.pending_for_conversation("c")[0]

    restarted_proposals = MemoryProposalStore(tmp_path / "memory-proposals.json")
    restarted_store = MemoryStore(memory_path)

    assert restarted_proposals.get(proposal.id).status == ProposalStatus.PENDING
    assert restarted_store.get_fact(proposal.record_payload["id"]) is None


class _FailingConfirmedMemory:
    def confirm(self, _confirmation):
        raise OSError("disk unavailable")


def test_storage_failure_keeps_pending_proposal_and_never_reports_success(tmp_path, memory_path):
    store = MemoryStore(memory_path)
    proposals = MemoryProposalStore(tmp_path / "memory-proposals.json")
    handler = MemoryIntentHandler(proposal_store=proposals, confirmed_memory=_FailingConfirmedMemory())
    handler.handle("Запомни, что я предпочитаю локальные модели", conversation_id="c", project_id=PROJECT_ID)
    proposal = proposals.pending_for_conversation("c")[0]

    result = handler.handle("Да", conversation_id="c", project_id=PROJECT_ID)

    assert "Не смогла сохранить" in result.response
    assert proposals.get(proposal.id).status == ProposalStatus.PENDING
    assert store.get_fact(proposal.record_payload["id"]) is None
