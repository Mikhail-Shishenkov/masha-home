from pathlib import Path
from datetime import datetime, timezone

from backend.conversation.memory_intent import MemoryIntentHandler, MemoryProposalStore
from backend.memory.confirmed_memory_service import ConfirmedMemoryService
from backend.memory.memory_management import MemoryManagementService
from backend.memory.sqlite_repository import MemorySqliteRepository
from backend.temporal.temporal_engine import FixedClock, TemporalEngine


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
