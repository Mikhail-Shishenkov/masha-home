from copy import deepcopy

from jsonschema import Draft202012Validator

from backend.memory.generate_schema import build_schema


def test_memory_schema_is_valid_draft_2020_12(memory_schema: dict):
    Draft202012Validator.check_schema(memory_schema)


def test_schema_rejects_document_without_required_collections(memory_schema: dict):
    errors = list(Draft202012Validator(memory_schema).iter_errors({}))

    assert errors


def test_canonical_document_matches_generated_schema(
    memory_schema: dict,
    canonical_memory: dict,
):
    errors = list(Draft202012Validator(memory_schema).iter_errors(canonical_memory))

    assert not errors


def test_committed_schema_is_generated_from_models(memory_schema: dict):
    assert memory_schema == build_schema()


def test_schema_rejects_out_of_range_episode_importance(
    memory_schema: dict,
    canonical_memory: dict,
):
    invalid = deepcopy(canonical_memory)
    invalid["episodes"][0]["importance"] = 2.0

    errors = list(Draft202012Validator(memory_schema).iter_errors(invalid))

    assert errors
