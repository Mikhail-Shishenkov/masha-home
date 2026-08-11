from backend.memory.memory_retriever import MemoryRetriever
from backend.memory.memory_store import MemoryStore


def test_retrieve_returns_ranked_project_memory(memory_path: str):
    results = MemoryRetriever(MemoryStore(memory_path)).retrieve(
        project_id="project_masha_home",
        limit=10,
    )

    assert results
    assert all(set(item) == {"type", "data", "score", "reasons"} for item in results)
    assert all(item["score"] >= 0 for item in results)
    assert [item["score"] for item in results] == sorted(
        (item["score"] for item in results),
        reverse=True,
    )


def test_retrieve_respects_limit(memory_path: str):
    results = MemoryRetriever(MemoryStore(memory_path)).retrieve(limit=2)

    assert len(results) == 2
