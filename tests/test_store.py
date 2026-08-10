from backend.memory.memory_models import Fact
from backend.memory.memory_store import MemoryStore


def _new_fact() -> Fact:
    return Fact(
        id="fact_003",
        subject="misha",
        key="learning_python",
        value="Изучает Python внутри проекта Masha Home",
        status="active",
        visibility="visible",
        importance=0.8,
        confidence=1.0,
        source="conversation",
        owner="misha",
        known_by=["misha", "masha"],
        project_ids=["project_masha_home"],
        source_episode_ids=[],
        superseded_by=None,
        created_at="2026-08-10T10:00:00+03:00",
        updated_at="2026-08-10T10:00:00+03:00",
    )


def test_get_project_and_fact(memory_path: str):
    store = MemoryStore(memory_path)

    assert store.get_project("project_masha_home").name == "Masha Home"
    assert store.get_project("unknown") is None
    assert store.get_fact("fact_001").key == "repository"
    assert store.get_fact("unknown") is None


def test_add_update_and_save_fact_in_isolated_file(memory_path: str):
    store = MemoryStore(memory_path)
    fact = _new_fact()

    assert store.add_fact(fact) is True
    assert store.add_fact(fact) is False

    fact.value = "Изучает Python и строит Masha Home"
    assert store.update_fact(fact) is True
    store.save()

    reloaded_fact = MemoryStore(memory_path).get_fact("fact_003")
    assert reloaded_fact is not None
    assert reloaded_fact.value == "Изучает Python и строит Masha Home"
