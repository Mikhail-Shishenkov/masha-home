from backend.memory.memory_store import MemoryStore
from backend.memory.memory_retriever import MemoryRetriever


store = MemoryStore("tests/fixtures/test_memory.json")
retriever = MemoryRetriever(store)


results = retriever.retrieve(
    project_id="project_masha_home",
    limit=10,
)


print("RETRIEVED MEMORY:")

for item in results:
    print()
    print("TYPE:", item["type"])
    print("SCORE:", round(item["score"], 3))

    data = item["data"]

    if item["type"] == "fact":
        print("KEY:", data["key"])
        print("VALUE:", data["value"])

    elif item["type"] == "decision":
        print("TITLE:", data["title"])
        print("DECISION:", data["decision"])

    elif item["type"] == "commitment":
        print("TEXT:", data["text"])
        print("OWNER:", data["owner"])

    elif item["type"] == "episode":
        print("TITLE:", data["title"])
        print("SUMMARY:", data["summary"])


assert results
assert all(
    "type" in item
    and "data" in item
    and "score" in item
    for item in results
)

assert all(
    item["score"] >= 0
    for item in results
)

print()
print("TEST: GREEN")