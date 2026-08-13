from backend.memory.memory_manager import MemoryManager
from backend.memory.memory_retriever import MemoryRetriever
from backend.memory.memory_store import MemoryStore
from backend.memory.working_memory import WorkingMemory


def test_manager_updates_working_memory_on_forget_and_restore(
    memory_path: str,
):
    store = MemoryStore(memory_path)
    working_memory = WorkingMemory(max_items=10)
    manager = MemoryManager(
        store=store,
        retriever=MemoryRetriever(store),
        working_memory=working_memory,
    )

    manager.load_working_memory(
        "project_masha_home",
        query="repository github",
        limit=10,
    )
    assert working_memory.contains("fact_001")

    assert manager.forget("fact", "fact_001") is True
    assert not working_memory.contains("fact_001")

    assert manager.restore(
        memory_type="fact",
        memory_id="fact_001",
        project_id="project_masha_home",
        limit=10,
    ) is True
    assert working_memory.contains("fact_001")
