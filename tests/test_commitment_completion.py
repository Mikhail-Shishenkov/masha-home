from pathlib import Path
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from backend.conversation.memory_intent import MemoryIntentHandler, MemoryProposalStore
from backend.memory.confirmed_memory_service import ConfirmedMemoryService
from backend.memory.memory_management import MemoryManagementService
from backend.memory.sqlite_repository import MemorySqliteRepository
from backend.temporal.temporal_engine import FixedClock, TemporalEngine
from backend.temporal.proactive import ProactiveDecisionEngine
from backend.temporal.proactive_interaction import ProactiveInteractionStore
from backend.temporal.temporal_models import ProactiveDecision
from backend.temporal.temporal_runtime import TemporalRuntime


ROOT = Path(__file__).resolve().parents[1]


def test_completion_is_explicit_persistent_and_idempotent(tmp_path, canonical_memory):
    repository = MemorySqliteRepository(tmp_path / "memory.sqlite3")
    repository.replace_document(canonical_memory)
    management = MemoryManagementService(repository)
    proposals = MemoryProposalStore(tmp_path / "proposals.json")
    handler = MemoryIntentHandler(
        proposal_store=proposals,
        confirmed_memory=ConfirmedMemoryService(repository),
        memory_management=management,
        temporal_engine=TemporalEngine(FixedClock(datetime(2026, 8, 11, tzinfo=timezone.utc))),
    )

    proposal = handler.handle("Маша, отметь Продолжить разработку Masha Home выполненным", conversation_id="c", project_id="project_masha_home")
    pending = proposals.pending_for_conversation("c")[0]
    assert "открыто → выполнено" in proposal.response
    assert repository.read_document().commitments[0].status.value == "open"
    confirmed = handler.handle(f"Да {pending.id}", conversation_id="c", project_id="project_masha_home")
    restarted = MemorySqliteRepository(repository.database_path).read_document().commitments[0]

    assert "отмечено выполненным" in confirmed.response
    assert restarted.status.value == "completed" and restarted.completed_at is not None
    assert any(event["action"] == "memory_edit" for event in repository.list_audit_events())
    assert "уже" in handler.handle(f"Да {pending.id}", conversation_id="c", project_id="project_masha_home").response


def test_completion_and_cancellation_close_only_their_delivered_reminders(tmp_path, canonical_memory):
    now = datetime(2026, 8, 11, tzinfo=timezone.utc)
    data = deepcopy(canonical_memory)
    base = data["commitments"][0]
    data["commitments"] = [
        {**base, "id": "commitment_001", "text": "Закончить", "due_at": (now - timedelta(minutes=1)).isoformat()},
        {**base, "id": "cancel", "text": "Отменить", "due_at": (now - timedelta(minutes=1)).isoformat()},
        {**base, "id": "other", "text": "Оставить", "due_at": (now - timedelta(minutes=1)).isoformat()},
    ]
    repository = MemorySqliteRepository(tmp_path / "memory.sqlite3")
    repository.replace_document(data)
    engine = TemporalEngine(FixedClock(now))
    interactions = ProactiveInteractionStore(repository)
    runtime = TemporalRuntime(repository, engine).recover()
    for event in runtime.events:
        candidate = ProactiveDecisionEngine.candidate(
            event,
            commitment_text=event.source_commitment_id,
            temporal_context=engine.context(None),
            decision=ProactiveDecision.REMIND,
            generated_at=now,
        )
        interactions.ensure_candidate(candidate)
        interactions.mark_delivered(event.event_id, "Напомню.", now)

    proposals = MemoryProposalStore(tmp_path / "proposals.json")
    handler = MemoryIntentHandler(
        proposal_store=proposals,
        confirmed_memory=ConfirmedMemoryService(repository),
        memory_management=MemoryManagementService(repository),
        temporal_engine=engine,
        on_commitment_terminal=lambda commitment_id: interactions.dismiss_delivered_reminders_for_commitment(commitment_id, now),
    )

    handler.propose_completion_by_id("commitment_001", "complete-conversation")
    handler.handle("да", conversation_id="complete-conversation", project_id="project_masha_home")
    handler.propose_cancellation_by_id("cancel", "cancel-conversation")
    handler.handle("да", conversation_id="cancel-conversation", project_id="project_masha_home")

    states = {
        event.source_commitment_id: interactions.get(event.event_id)["state"]
        for event in runtime.events
    }
    assert states == {"commitment_001": "dismissed", "cancel": "dismissed", "other": "delivered"}
