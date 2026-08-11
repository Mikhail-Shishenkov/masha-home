from datetime import datetime, timezone
from pathlib import Path

from backend.conversation.cli import _run_commitments_command
from backend.conversation.conversation_store import ConversationStore
from backend.memory.sqlite_repository import MemorySqliteRepository
from backend.temporal.temporal_engine import FixedClock, TemporalEngine


def test_commitments_cli_is_human_readable_and_filters_statuses(tmp_path, canonical_memory):
    repository = MemorySqliteRepository(tmp_path / "memory.sqlite3")
    repository.replace_document(canonical_memory)
    service = type("Service", (), {"memory_retriever": type("R", (), {"memory_store": repository})(), "temporal_engine": TemporalEngine(FixedClock(datetime(2026, 8, 11, 7, 42, tzinfo=timezone.utc)))})()
    output = []
    _run_commitments_command("commitments list", service=service, output_fn=output.append)
    assert "Обязательства:" in output[-1]
    assert "Продолжить разработку Masha Home" in output[-1]
    assert "commitment_" not in output[-1]
