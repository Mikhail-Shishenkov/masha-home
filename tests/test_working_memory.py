from backend.memory.working_memory import WorkingMemory


def _memory(memory_id: str, score: float, memory_type: str = "fact") -> dict:
    return {
        "type": memory_type,
        "data": {"id": memory_id},
        "score": score,
    }


def test_load_respects_max_items():
    working_memory = WorkingMemory(max_items=2)

    working_memory.load(
        [
            _memory("fact_001", 0.9),
            _memory("fact_002", 0.8),
            _memory("fact_003", 0.7),
        ]
    )

    assert len(working_memory) == 2
    assert working_memory.contains("fact_001")
    assert not working_memory.contains("fact_003")


def test_add_sorts_and_truncates():
    working_memory = WorkingMemory(max_items=2)
    working_memory.load([_memory("fact_001", 0.5)])

    working_memory.add(_memory("fact_002", 0.9))
    working_memory.add(_memory("fact_003", 0.7))

    assert [item["data"]["id"] for item in working_memory.get_all()] == [
        "fact_002",
        "fact_003",
    ]


def test_remove_and_filter_by_type():
    working_memory = WorkingMemory(max_items=3)
    working_memory.load(
        [
            _memory("fact_001", 0.9),
            _memory("decision_001", 0.8, "decision"),
        ]
    )

    assert [
        item["data"]["id"]
        for item in working_memory.get_by_type("decision")
    ] == ["decision_001"]
    assert working_memory.remove("fact_001") is True
    assert working_memory.remove("unknown") is False
    assert not working_memory.contains("fact_001")
