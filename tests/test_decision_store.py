from backend.memory.decision_store import DecisionStore


store = DecisionStore("tests/fixtures/test_memory.json")

decision = store.get_decision("decision_001")

print("DECISION:")
print(decision)

print("\nDECISIONS BY PROJECT:")

decisions = store.get_decisions_by_project("project_masha_home")

for item in decisions:
    print("-", item.title)