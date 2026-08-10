from backend.persona.masha_persona import MashaPersona


def test_builtin_masha_persona_has_visual_identity():
    assert MashaPersona.id == "masha"
    assert MashaPersona.name == "Маша"
    assert MashaPersona.visual_identity is not None
    assert (
        MashaPersona.visual_identity.reference_image
        == "persona/visual_identity/canonical_reference.jpg"
    )
