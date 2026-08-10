from backend.memory.base_store import BaseStore


store = BaseStore("tests/fixtures/test_memory.json")

print("PROJECT:")
print(store.data["project"]["name"])

print("\nFACT COUNT:")
print(len(store.data["facts"]))

print("\nDECISION COUNT:")
print(len(store.data["decisions"]))