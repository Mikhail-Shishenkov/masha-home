from backend.memory.memory_models import MemoryDocument


def test_canonical_memory_matches_python_model(canonical_memory: dict):
    document = MemoryDocument.model_validate(canonical_memory)

    assert document.schema_version == "0.4"
    assert document.projects[0].name == "Masha Home"
    assert document.facts[0].project_ids == ["project_masha_home"]
