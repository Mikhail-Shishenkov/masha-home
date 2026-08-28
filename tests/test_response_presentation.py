from backend.conversation.response_expression import _parse_presentation_cue


def test_presentation_cue_parses_expression_and_one_step_proximity():
    cue = _parse_presentation_cue(
        "playful|closer",
        proximity_allowed=True,
    )

    assert cue.expression == "playful"
    assert cue.proximity == "closer"


def test_presentation_cue_keeps_legacy_one_word_expression_and_holds():
    cue = _parse_presentation_cue(
        "amused",
        proximity_allowed=True,
    )

    assert cue.expression == "amused"
    assert cue.proximity == "hold"


def test_presentation_cue_cannot_move_when_home_disallows_proximity():
    cue = _parse_presentation_cue(
        "playful|closer",
        proximity_allowed=False,
    )

    assert cue.expression == "playful"
    assert cue.proximity == "hold"


def test_presentation_cue_invalid_expression_fails_closed():
    cue = _parse_presentation_cue(
        "romantic|closer",
        proximity_allowed=True,
    )

    assert cue.expression == "warm"
    assert cue.proximity == "hold"
