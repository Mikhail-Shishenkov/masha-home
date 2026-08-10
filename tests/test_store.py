from backend.memory.memory_store import MemoryStore
from backend.memory.memory_models import Fact


store = MemoryStore("memory/test_memory.json")

fact = store.get_fact("fact_001")

print(fact)
print(fact.key)
print(fact.value)
print(fact.owner)

new_fact = Fact(
    id="fact_002",
    subject="misha",
    key="learning_python",
    value="Изучает Python внутри проекта Masha Home",
    status="active",
    importance=0.8,
    confidence=1.0,
    source="conversation",
    owner="misha",
    known_by=["misha", "masha"],
    created_at="2026-08-10T10:00:00+03:00",
    updated_at="2026-08-10T10:00:00+03:00"
)

store.add_fact(new_fact)

print(store.get_fact("fact_002"))