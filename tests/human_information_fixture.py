"""Production-like mixed lifecycle fixture for human information tests."""

from __future__ import annotations

from copy import deepcopy

from tests.query_retrieval_fixture import PROJECT_ID, query_retrieval_document


ACTIVE_MAC_ID = "11111111-1111-4111-8111-111111111111"
FORGOTTEN_MAC_ID = "22222222-2222-4222-8222-222222222222"
MAC_EPISODE_ID = "33333333-3333-4333-8333-333333333333"
COMPLETED_MAC_TASK_ID = "44444444-4444-4444-8444-444444444444"
OPEN_MAC_TASK_ID = "55555555-5555-4555-8555-555555555555"
OLD_MODEL_DECISION_ID = "66666666-6666-4666-8666-666666666666"
CURRENT_MODEL_DECISION_ID = "77777777-7777-4777-8777-777777777777"
REVISED_RELATIONSHIP_ID = "88888888-8888-4888-8888-888888888888"
CURRENT_RELATIONSHIP_ID = "99999999-9999-4999-8999-999999999999"
REJECTED_CANDIDATE_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
RESOLVED_THREAD_ID = "followup_resolved_mac_states"
OPEN_THREAD_ID = "followup_open_mac_shop"


def human_information_document() -> dict:
    data = deepcopy(query_retrieval_document())
    data["facts"].extend((
        {
            "id": ACTIVE_MAC_ID,
            "subject": "Миша",
            "key": "предпочтение при выборе ноутбука",
            "value": "MacBook M2 Pro до 120 тысяч рублей",
            "status": "active",
            "visibility": "visible",
            "importance": 0.9,
            "confidence": 1.0,
            "source": "explicit_user_input",
            "owner": "misha",
            "known_by": ["misha", "masha"],
            "project_ids": [PROJECT_ID],
            "source_episode_ids": [],
            "supersedes_id": None,
            "superseded_by": None,
            "created_at": "2026-08-13T18:00:00+04:00",
            "updated_at": "2026-08-13T18:00:00+04:00",
        },
        {
            "id": FORGOTTEN_MAC_ID,
            "subject": "Миша",
            "key": "старая заметка про MacBook",
            "value": "секретная забытая цена MacBook — 90 тысяч",
            "status": "active",
            "visibility": "hidden",
            "importance": 0.8,
            "confidence": 1.0,
            "source": "explicit_user_input",
            "owner": "misha",
            "known_by": ["misha", "masha"],
            "project_ids": [PROJECT_ID],
            "source_episode_ids": [],
            "supersedes_id": None,
            "superseded_by": None,
            "created_at": "2026-08-09T10:00:00+04:00",
            "updated_at": "2026-08-12T10:00:00+04:00",
        },
    ))
    data["decisions"].extend((
        {
            "id": OLD_MODEL_DECISION_ID,
            "title": "Основная модель Mac-проекта",
            "decision": "Использовать Qwen A",
            "reason": "Это был первый рабочий вариант",
            "status": "superseded",
            "visibility": "visible",
            "project_ids": [PROJECT_ID],
            "source": "conversation",
            "source_episode_ids": [],
            "supersedes_id": None,
            "superseded_by": CURRENT_MODEL_DECISION_ID,
            "created_at": "2026-08-04T09:00:00+04:00",
            "updated_at": "2026-08-11T09:00:00+04:00",
        },
        {
            "id": CURRENT_MODEL_DECISION_ID,
            "title": "Основная модель Mac-проекта",
            "decision": "Использовать Qwen B",
            "reason": "Лучше держит длинный контекст",
            "status": "active",
            "visibility": "visible",
            "project_ids": [PROJECT_ID],
            "source": "conversation",
            "source_episode_ids": [],
            "supersedes_id": OLD_MODEL_DECISION_ID,
            "superseded_by": None,
            "created_at": "2026-08-11T09:00:00+04:00",
            "updated_at": "2026-08-11T09:00:00+04:00",
        },
    ))
    data["episodes"].append({
        "id": MAC_EPISODE_ID,
        "title": "Сравнивали MacBook",
        "summary": "Смотрели M2 Pro и обсуждали батарею MacBook",
        "occurred_at": "2026-08-08T20:00:00+04:00",
        "source": "conversation",
        "importance": 0.8,
        "visibility": "visible",
        "project_ids": [PROJECT_ID],
        "participants": ["misha", "masha"],
        "topics": ["MacBook", "M2 Pro"],
        "produced": {
            "facts": [], "decisions": [], "commitments": [], "reflections": [],
            "relationship_memories": [], "affective_records": [], "project_changes": [],
        },
        "updated": {
            "facts": [], "decisions": [], "commitments": [],
            "continuity_states": [], "projects": [],
        },
        "superseded": {"facts": [], "decisions": [], "commitments": []},
        "related_memory_ids": [],
        "created_at": "2026-08-08T20:00:00+04:00",
    })
    data["commitments"].extend((
        {
            "id": COMPLETED_MAC_TASK_ID,
            "text": "Проверить батарею MacBook",
            "owner": "misha",
            "status": "completed",
            "visibility": "visible",
            "project_ids": [PROJECT_ID],
            "due_at": None,
            "completed_at": "2026-08-12T15:00:00+04:00",
            "importance": 0.8,
            "source": "conversation",
            "source_episode_ids": [],
            "replaces_id": None,
            "created_at": "2026-08-07T10:00:00+04:00",
            "updated_at": "2026-08-12T15:00:00+04:00",
        },
        {
            "id": OPEN_MAC_TASK_ID,
            "text": "Позвонить продавцу MacBook M2 Pro",
            "owner": "misha",
            "status": "open",
            "visibility": "visible",
            "project_ids": [PROJECT_ID],
            "due_at": "2026-08-15T12:00:00+04:00",
            "completed_at": None,
            "importance": 0.8,
            "source": "conversation",
            "source_episode_ids": [],
            "replaces_id": None,
            "created_at": "2026-08-13T12:00:00+04:00",
            "updated_at": "2026-08-13T12:00:00+04:00",
        },
    ))
    data["relationship_memories"].extend((
        {
            "id": REVISED_RELATIONSHIP_ID,
            "kind": "relationship_note",
            "title": "Старый способ сравнивать Mac",
            "content": "Сначала сравнивали только цену MacBook",
            "status": "revised",
            "visibility": "visible",
            "importance": 0.6,
            "confidence": 1.0,
            "source": "conversation",
            "project_ids": [PROJECT_ID],
            "source_episode_ids": [],
            "revises_id": None,
            "created_at": "2026-08-03T12:00:00+04:00",
        },
        {
            "id": CURRENT_RELATIONSHIP_ID,
            "kind": "helpful_pattern",
            "title": "Как сравниваем Mac",
            "content": "Сравниваем MacBook по цене, батарее и памяти",
            "status": "current",
            "visibility": "visible",
            "importance": 0.7,
            "confidence": 1.0,
            "source": "conversation",
            "project_ids": [PROJECT_ID],
            "source_episode_ids": [],
            "revises_id": REVISED_RELATIONSHIP_ID,
            "created_at": "2026-08-10T12:00:00+04:00",
        },
    ))
    data["memory_candidates"].append({
        "id": REJECTED_CANDIDATE_ID,
        "candidate_type": "fact",
        "proposed_payload": {"summary": "Кандидат про MacBook"},
        "status": "rejected",
        "confidence": 0.8,
        "source": "conversation",
        "project_ids": [PROJECT_ID],
        "evidence_episode_ids": [],
        "created_by": "system",
        "reviewed_by": "misha",
        "created_at": "2026-08-13T08:00:00+04:00",
        "reviewed_at": "2026-08-13T09:00:00+04:00",
        "result_memory_id": None,
    })
    state = data["continuity_states"][0]
    state["intended_follow_ups"].extend((
        {
            "id": RESOLVED_THREAD_ID,
            "topic": "состояния Маши для длинных разговоров на MacBook",
            "summary": "Обсудить состояния Маши для длинных разговоров на MacBook",
            "reason_to_return": "Нужно было сверить поведение на длинном контексте",
            "priority": 0.8,
            "status": "resolved",
            "source_memory_ids": [],
            "revisit_after": None,
        },
        {
            "id": OPEN_THREAD_ID,
            "topic": "покупка MacBook",
            "summary": "Вернуться к выбору продавца MacBook M2 Pro",
            "reason_to_return": "Нужно дождаться ответа продавца",
            "priority": 0.8,
            "status": "open",
            "source_memory_ids": [],
            "revisit_after": None,
        },
    ))
    return data
