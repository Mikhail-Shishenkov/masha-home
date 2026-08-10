import pytest

from backend.memory.memory_retriever import MemoryRetriever
from backend.memory.memory_store import MemoryStore


PROJECT_ID = "project_masha_home"


@pytest.mark.parametrize(
    ("memory_type", "memory_id"),
    [
        ("fact", "fact_001"),
        ("decision", "decision_001"),
        ("commitment", "commitment_001"),
    ],
)
def test_generic_lifecycle_changes_retrieval_visibility(
    memory_path: str,
    memory_type: str,
    memory_id: str,
):
    store = MemoryStore(memory_path)
    retriever = MemoryRetriever(store)

    def visible_ids() -> set[str]:
        return {
            item["data"]["id"]
            for item in retriever.retrieve(project_id=PROJECT_ID, limit=20)
        }

    assert memory_id in visible_ids()
    assert store.forget(memory_type, memory_id) is True
    assert memory_id not in visible_ids()
    assert store.restore(memory_type, memory_id) is True
    assert memory_id in visible_ids()


def test_unknown_memory_type_is_rejected(memory_path: str):
    store = MemoryStore(memory_path)

    assert store.forget("unknown", "item_001") is False
    assert store.restore("unknown", "item_001") is False
