"""Deterministic competing-memory fixture for query-aware retrieval evaluation."""

from __future__ import annotations


PROJECT_ID = "project_masha_home"
CREATED_AT = "2026-08-10T10:00:00+03:00"


def query_retrieval_document() -> dict:
    """Return records A-H from the v0.2 retrieval acceptance matrix."""
    return {
        "schema_version": "0.4",
        "identity_version": "masha-0.1",
        "projects": [
            {
                "id": PROJECT_ID,
                "name": "Masha Home",
                "description": "Локальный домашний AI-проект",
                "status": "active",
                "created_at": CREATED_AT,
                "updated_at": CREATED_AT,
                "completed_at": None,
            }
        ],
        # C and D
        "facts": [
            {
                "id": "C_dev_memory_schema",
                "subject": "Masha Home",
                "key": "memory schema",
                "value": "Python memory_schema models migration",
                "status": "active",
                "visibility": "visible",
                "importance": 0.9,
                "confidence": 1.0,
                "source": "conversation",
                "owner": "misha",
                "known_by": ["misha", "masha"],
                "project_ids": [PROJECT_ID],
                "source_episode_ids": [],
                "supersedes_id": None,
                "superseded_by": None,
                "created_at": CREATED_AT,
                "updated_at": CREATED_AT,
            },
            {
                "id": "D_coffee_preference",
                "subject": "Миша",
                "key": "любит пить",
                "value": "кофе",
                "status": "active",
                "visibility": "visible",
                "importance": 0.7,
                "confidence": 1.0,
                "source": "explicit_user_input",
                "owner": "misha",
                "known_by": ["misha", "masha"],
                "project_ids": [PROJECT_ID],
                "source_episode_ids": [],
                "supersedes_id": None,
                "superseded_by": None,
                "created_at": CREATED_AT,
                "updated_at": CREATED_AT,
            },
        ],
        # A
        "decisions": [
            {
                "id": "A_primary_local_model",
                "title": "Основная локальная модель Masha Home",
                "decision": "Для основного локального разговора выбрана Qwen 3.5 9B",
                "reason": "Подходит для локальной работы",
                "status": "active",
                "visibility": "visible",
                "project_ids": [PROJECT_ID],
                "source": "conversation",
                "source_episode_ids": [],
                "supersedes_id": None,
                "superseded_by": None,
                "created_at": CREATED_AT,
                "updated_at": CREATED_AT,
            }
        ],
        # E
        "commitments": [
            {
                "id": "E_buy_tickets",
                "text": "Купить билеты на поезд",
                "owner": "misha",
                "status": "open",
                "visibility": "visible",
                "project_ids": [PROJECT_ID],
                "due_at": None,
                "completed_at": None,
                "importance": 0.8,
                "source": "conversation",
                "source_episode_ids": [],
                "replaces_id": None,
                "created_at": CREATED_AT,
                "updated_at": CREATED_AT,
            }
        ],
        # B
        "episodes": [
            {
                "id": "B_model_discussion",
                "title": "Обсуждали выбор модели",
                "summary": "Обсуждали быструю и основную локальные модели для Masha Home",
                "occurred_at": CREATED_AT,
                "source": "conversation",
                "importance": 0.8,
                "visibility": "visible",
                "project_ids": [PROJECT_ID],
                "participants": ["misha", "masha"],
                "topics": ["model-choice"],
                "produced": {
                    "facts": [],
                    "decisions": [],
                    "commitments": [],
                    "reflections": [],
                    "relationship_memories": [],
                    "affective_records": [],
                    "project_changes": [],
                },
                "updated": {
                    "facts": [],
                    "decisions": [],
                    "commitments": [],
                    "continuity_states": [],
                    "projects": [],
                },
                "superseded": {"facts": [], "decisions": [], "commitments": []},
                "related_memory_ids": [],
                "created_at": CREATED_AT,
            }
        ],
        "memory_candidates": [],
        # H
        "reflections": [
            {
                "id": "H_model_perspective",
                "text": "Я думаю о выборе основной локальной модели для Masha Home",
                "meaning": "Сейчас Qwen 3.5 9B кажется мне самым цельным вариантом",
                "importance": 0.8,
                "confidence": 0.75,
                "source": "inference",
                "visibility": "visible",
                "project_ids": [PROJECT_ID],
                "source_episode_ids": [],
                "related_memory_ids": [],
                "reconsiders_reflection_id": None,
                "created_at": CREATED_AT,
            }
        ],
        # F
        "relationship_memories": [
            {
                "id": "F_first_mvp",
                "kind": "shared_milestone",
                "title": "Первый рабочий MVP",
                "content": "Сегодня запустили первый MVP Дома — наш общий момент",
                "status": "current",
                "visibility": "visible",
                "importance": 0.9,
                "confidence": 1.0,
                "source": "conversation",
                "project_ids": [PROJECT_ID],
                "source_episode_ids": [],
                "revises_id": None,
                "created_at": CREATED_AT,
            }
        ],
        "affective_records": [],
        # G
        "continuity_states": [
            {
                "id": "G_model_long_context_thread",
                "relationship_key": "misha-masha",
                "last_interaction_at": CREATED_AT,
                "affective_record_ids": [],
                "current_focus": ["Позже решить, какую модель использовать для длинных разговоров"],
                "intended_follow_ups": [
                    {
                        "id": "followup_model_choice",
                        "topic": "выбор модели",
                        "summary": "Вернуться к выбору локальной модели для длинных разговоров",
                        "reason_to_return": "Нужно проверить качество на длинном контексте",
                        "priority": 0.8,
                        "status": "open",
                        "source_memory_ids": [],
                        "revisit_after": None,
                    }
                ],
                "based_on_episode_ids": [],
                "updated_at": CREATED_AT,
            }
        ],
    }
