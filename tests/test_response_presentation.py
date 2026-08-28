import json

from backend.conversation.response_expression import _parse_presentation_cue


def test_presentation_cue_parses_structured_expression_and_proximity():
    cue = _parse_presentation_cue(
        json.dumps({"expression": "playful", "proximity": "closer"}),
        proximity_allowed=True,
    )

    assert cue.expression == "playful"
    assert cue.proximity == "closer"


def test_presentation_cue_structured_output_cannot_move_when_home_disallows():
    cue = _parse_presentation_cue(
        json.dumps({"expression": "playful", "proximity": "closer"}),
        proximity_allowed=False,
    )

    assert cue.expression == "playful"
    assert cue.proximity == "hold"


def test_presentation_cue_invalid_structured_expression_fails_closed():
    cue = _parse_presentation_cue(
        json.dumps({"expression": "romantic", "proximity": "closer"}),
        proximity_allowed=True,
    )

    assert cue.expression == "warm"
    assert cue.proximity == "hold"


def test_presentation_cue_invalid_structured_proximity_fails_closed():
    cue = _parse_presentation_cue(
        json.dumps({"expression": "warm", "proximity": "nearest"}),
        proximity_allowed=True,
    )

    assert cue.expression == "warm"
    assert cue.proximity == "hold"


def test_presentation_cue_malformed_json_fails_closed():
    cue = _parse_presentation_cue(
        '{"expression":"warm","proximity":',
        proximity_allowed=True,
    )

    assert cue.expression == "warm"
    assert cue.proximity == "hold"


def test_presentation_cue_keeps_legacy_two_token_format_for_compatibility():
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


def test_presentation_cue_legacy_invalid_expression_fails_closed():
    cue = _parse_presentation_cue(
        "romantic|closer",
        proximity_allowed=True,
    )

    assert cue.expression == "warm"
    assert cue.proximity == "hold"
