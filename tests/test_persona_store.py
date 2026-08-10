from backend.persona.persona_store import PersonaStore


def test_persona_store_loads_masha(persona_path: str):
    persona = PersonaStore(persona_path).get_persona("masha")

    assert persona is not None
    assert persona.id == "masha"
    assert persona.name == "Маша"
    assert persona.visual_identity is not None
    assert persona.visual_identity.name == "Masha"
    assert len(persona.visual_identity.generation_notes) == 4


def test_persona_store_returns_none_for_unknown_id(persona_path: str):
    assert PersonaStore(persona_path).get_persona("unknown") is None
