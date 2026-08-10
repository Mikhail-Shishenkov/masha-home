from copy import deepcopy

import pytest
from pydantic import ValidationError

from backend.memory.memory_models import MemoryDocument


def test_model_rejects_unknown_fields(canonical_memory: dict):
    invalid = deepcopy(canonical_memory)
    invalid["facts"][0]["unexpected"] = True

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        MemoryDocument.model_validate(invalid)


def test_model_rejects_naive_timestamps(canonical_memory: dict):
    invalid = deepcopy(canonical_memory)
    invalid["facts"][0]["created_at"] = "2026-08-10T10:00:00"

    with pytest.raises(ValidationError, match="timezone"):
        MemoryDocument.model_validate(invalid)


def test_model_rejects_unknown_project_reference(canonical_memory: dict):
    invalid = deepcopy(canonical_memory)
    invalid["facts"][0]["project_ids"] = ["unknown_project"]

    with pytest.raises(ValidationError, match="unknown project reference"):
        MemoryDocument.model_validate(invalid)


def test_model_rejects_supersession_cycle(canonical_memory: dict):
    invalid = deepcopy(canonical_memory)
    first = invalid["facts"][0]
    second = invalid["facts"][1]
    first["status"] = "superseded"
    first["superseded_by"] = second["id"]
    second["status"] = "superseded"
    second["superseded_by"] = first["id"]

    with pytest.raises(ValidationError, match="supersession cycle"):
        MemoryDocument.model_validate(invalid)


def test_approved_candidate_requires_matching_result_type(canonical_memory: dict):
    invalid = deepcopy(canonical_memory)
    invalid["memory_candidates"] = [
        {
            "id": "candidate_001",
            "candidate_type": "fact",
            "proposed_payload": {"subject": "misha"},
            "status": "approved",
            "confidence": 0.9,
            "source": "conversation",
            "project_ids": [],
            "evidence_episode_ids": ["episode_001"],
            "created_by": "masha",
            "reviewed_by": "misha",
            "created_at": "2026-08-10T11:00:00+03:00",
            "reviewed_at": "2026-08-10T11:01:00+03:00",
            "result_memory_id": "decision_001",
        }
    ]

    with pytest.raises(ValidationError, match="result type"):
        MemoryDocument.model_validate(invalid)
