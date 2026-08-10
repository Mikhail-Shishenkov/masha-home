from backend.memory.decision_store import DecisionStore


def test_get_decision(memory_path: str):
    decision = DecisionStore(memory_path).get_decision("decision_001")

    assert decision is not None
    assert decision.title == "Memory architecture"


def test_get_decisions_by_project(memory_path: str):
    decisions = DecisionStore(memory_path).get_decisions_by_project(
        "project_masha_home"
    )

    assert [item.id for item in decisions] == ["decision_001"]
