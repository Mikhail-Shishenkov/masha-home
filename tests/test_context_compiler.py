from datetime import datetime, timezone
from pathlib import Path

from backend.conversation.context_compiler import ConversationContextCompiler
from backend.identity.identity_kernel import IdentityKernel
from backend.identity.identity_store import IdentityStore
from backend.llm.model_models import ModelMessage


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_compiler_preserves_memory_type_semantics_and_bounded_context():
    working_memory = [
        {"type": "fact", "data": {"id": "fact_1", "subject": "misha", "key": "city", "value": "Moscow"}},
        {"type": "decision", "data": {"id": "decision_1", "title": "Storage", "decision": "Use JSON", "status": "active"}},
        {"type": "commitment", "data": {"id": "commitment_1", "text": "Check tests", "status": "open"}},
        {"type": "episode", "data": {"id": "episode_1", "title": "Started", "summary": "Conversation started", "occurred_at": "2026-08-10T00:00:00+00:00"}},
    ]
    compiler = ConversationContextCompiler(lambda: datetime(2026, 8, 11, 12, 30, tzinfo=timezone.utc))

    request = compiler.compile(
        messages=(ModelMessage(role="user", content="Что мы помним?"),),
        identity_context=IdentityKernel(IdentityStore(PROJECT_ROOT / "identity" / "masha.identity.json")).build_context(),
        working_memory=working_memory,
    )

    records = request.private_context["memory_context"]
    assert len(records) <= 4
    assert {record["record_type"] for record in records} == {"fact", "decision", "commitment", "episode"}
    assert "decision" in next(record for record in records if record["record_type"] == "decision")
    assert "text" in next(record for record in records if record["record_type"] == "commitment")
    assert request.private_context["current_local_time"] == "2026-08-11T12:30:00+00:00"
    assert "не говори «я запомнила»" in request.private_context["behavioral_contract"]
