from backend.memory.commitment_store import CommitmentStore


store = CommitmentStore("tests/fixtures/test_memory.json")

commitment = store.get_commitment("commitment_001")

print("COMMITMENT:")
print(commitment)

print("\nOPEN COMMITMENTS:")

commitments = store.get_open_commitments()

for item in commitments:
    print("-", item.text)
    print("  owner:", item.owner)
    print("  status:", item.status)