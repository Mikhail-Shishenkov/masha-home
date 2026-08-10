from backend.memory.memory_store import MemoryStore


store = MemoryStore("../memory/test_memory.json")

fact = store.get_fact("fact_001")

print(fact)