from backend.memory.memory_retriever import MemoryRetrievalRequest, MemoryRetriever
from backend.memory.memory_store import MemoryStore


def test_retrieve_returns_ranked_project_memory(memory_path: str):
    results = MemoryRetriever(MemoryStore(memory_path)).retrieve(
        MemoryRetrievalRequest(
            query="Какие основные сущности и правила памяти мы определили?",
            project_id="project_masha_home",
            limit=10,
        )
    )

    assert results
    assert all(set(item) == {"type", "data", "score", "components", "reasons"} for item in results)
    assert all(item["score"] >= 0 for item in results)
    assert [item["score"] for item in results] == sorted(
        (item["score"] for item in results),
        reverse=True,
    )


def test_retrieve_respects_limit(memory_path: str):
    results = MemoryRetriever(MemoryStore(memory_path)).retrieve(
        MemoryRetrievalRequest(query="Masha Home", limit=2)
    )

    assert len(results) == 2


def test_retrieve_can_return_empty_instead_of_filling_limit(memory_path: str):
    results = MemoryRetriever(MemoryStore(memory_path)).retrieve(
        MemoryRetrievalRequest(
            query="Доброе утро)",
            project_id="project_masha_home",
            limit=6,
        )
    )

    assert results == []
