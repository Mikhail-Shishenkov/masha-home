import json

from backend.memory.commitment_store import CommitmentStore


def test_get_commitment(memory_path: str):
    store = CommitmentStore(memory_path)

    commitment = store.get_commitment("commitment_001")

    assert commitment is not None
    assert commitment.owner == "misha"
    assert commitment.text == "Продолжить разработку Masha Home"


def test_get_open_commitments(memory_path: str):
    with open(memory_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    data["commitments"][0]["status"] = "open"

    with open(memory_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)

    commitments = CommitmentStore(memory_path).get_open_commitments()

    assert [item.id for item in commitments] == ["commitment_001"]
