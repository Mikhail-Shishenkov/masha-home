from backend.memory.memory_store import MemoryStore
from backend.memory.memory_models import Fact


store = MemoryStore("tests/fixtures/test_memory.json")

fact = store.get_fact("fact_001")

print(fact)
print(fact.key)
print(fact.value)
print(fact.owner)

new_fact = Fact(
    id="",
    subject="misha",
    key="learning_python",
    value="Изучает Python внутри проекта Masha Home",
    status="active",
    importance=0.8,
    confidence=1.0,
    source="conversation",
    owner="misha",
    known_by=["misha", "masha"],
    project_ids=["project_masha_home"],
    created_at="2026-08-10T10:00:00+03:00",
    updated_at="2026-08-10T10:00:00+03:00"
)

store.add_fact(new_fact)
duplicate_result = store.add_fact(new_fact)

print("First add:", True)
print("Duplicate add:", duplicate_result)
store.save()
first_result = store.add_fact(new_fact)
duplicate_result = store.add_fact(new_fact)

print("First add:", first_result)
print("Duplicate add:", duplicate_result)

new_fact.value = "Изучает Python и строит Masha Home"

update_result = store.update_fact(new_fact)

print("Update:", update_result)

store.save()

print(store.get_fact("fact_002"))
print("\nPROJECT:")

project = store.get_project("project_masha_home")
print(project)

print("\nFACTS BY PROJECT:")

facts = store.get_facts_by_project("project_masha_home")
print(facts)