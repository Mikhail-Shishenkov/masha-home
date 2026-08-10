from backend.memory.base_store import BaseStore


def test_base_store_loads_memory_collections(memory_path: str):
    store = BaseStore(memory_path)

    assert store.data["projects"][0]["name"] == "Masha Home"
    assert len(store.data["facts"]) == 2
    assert len(store.data["decisions"]) == 1
