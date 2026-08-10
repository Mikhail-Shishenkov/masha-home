from copy import deepcopy

from backend.memory.memory_models import MemoryDocument
from backend.memory.migrations.v03_to_v04 import migrate_v03_to_v04


def _v03_document() -> dict:
    timestamp = "2026-08-10T10:00:00+03:00"
    return {
        "project": {
            "id": "project_001",
            "name": "Test",
            "description": None,
            "status": "active",
            "working_memory": {
                "current_blockers": [],
                "open_questions": ["Что дальше?"],
                "architecture_notes": ["Память локальная"],
                "next_actions": ["Продолжить"],
            },
            "created_at": timestamp,
            "updated_at": timestamp,
            "archived_at": None,
        },
        "facts": [
            {
                "id": "fact_001",
                "subject": "project",
                "key": "mode",
                "value": "local",
                "status": "active",
                "importance": 0.8,
                "confidence": 1.0,
                "source": "test",
                "owner": "misha",
                "known_by": ["misha", "masha"],
                "superseded_by": None,
                "created_at": timestamp,
                "updated_at": timestamp,
            }
        ],
        "decisions": [],
        "commitments": [],
        "episodes": [
            {
                "id": "episode_001",
                "title": "Начало",
                "summary": "Создана память",
                "occurred_at": timestamp,
                "source": "conversation",
                "importance": 2.0,
                "context": {
                    "projects": ["project_001"],
                    "participants": ["misha", "masha"],
                    "topics": ["memory"],
                },
                "produced": {
                    "facts": ["fact_001"],
                    "decisions": [],
                    "commitments": [],
                    "project_changes": ["project_001"],
                },
                "updated": {"facts": [], "projects": [], "commitments": []},
                "superseded": {"facts": [], "decisions": [], "commitments": []},
                "created_at": timestamp,
            }
        ],
    }


def test_migration_preserves_entities_and_working_memory():
    source = _v03_document()
    untouched = deepcopy(source)

    migrated = migrate_v03_to_v04(source)
    document = MemoryDocument.model_validate(migrated)

    assert source == untouched
    assert [item.id for item in document.projects] == ["project_001"]
    assert [item.id for item in document.facts] == ["fact_001"]
    assert [item.id for item in document.episodes] == ["episode_001"]
    assert document.episodes[0].importance == 1.0
    assert document.facts[0].source_episode_ids == ["episode_001"]
    assert document.continuity_states[0].current_focus == ["Память локальная"]
    assert len(document.continuity_states[0].intended_follow_ups) == 2


def test_migration_is_idempotent_for_v04():
    migrated = migrate_v03_to_v04(_v03_document())

    assert migrate_v03_to_v04(migrated) == migrated
