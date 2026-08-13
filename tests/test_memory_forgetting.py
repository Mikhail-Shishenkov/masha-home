from backend.memory.memory_retriever import MemoryRetrievalRequest, MemoryRetriever
from backend.memory.memory_store import MemoryStore


FACT_ID = "fact_001"
PROJECT_ID = "project_masha_home"


def _retrieved_ids(retriever: MemoryRetriever) -> set[str]:
    return {
        item["data"]["id"]
        for item in retriever.retrieve(
            MemoryRetrievalRequest(
                query="repository github masha home",
                project_id=PROJECT_ID,
                limit=20,
            )
        )
    }


def test_fact_can_be_hidden_and_restored_in_isolated_store(memory_path: str):
    store = MemoryStore(memory_path)
    retriever = MemoryRetriever(store)

    assert FACT_ID in _retrieved_ids(retriever)
    assert store.forget_fact(FACT_ID) is True
    assert store.forget_fact(FACT_ID) is False
    assert FACT_ID not in _retrieved_ids(retriever)

    store.save()
    reloaded = MemoryStore(memory_path)
    reloaded_retriever = MemoryRetriever(reloaded)

    assert FACT_ID not in _retrieved_ids(reloaded_retriever)
    assert reloaded.restore_fact(FACT_ID) is True
    assert reloaded.restore_fact(FACT_ID) is False
    assert FACT_ID in _retrieved_ids(reloaded_retriever)
