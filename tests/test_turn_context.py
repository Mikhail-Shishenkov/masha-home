from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.conversation.turn_context import (
    TurnCapabilityHint,
    TurnContextEnvelope,
    TurnContextEnvelopeBuilder,
    TurnContinuityHint,
    TurnConversationHint,
    TurnMemoryHint,
    TurnPresentedEntityHint,
    TurnTemporalContext,
)
from backend.application.capability_catalog import CapabilityAvailability
from backend.application.home_capabilities import default_home_capability_catalog
from backend.conversation.conversation_models import (
    ConversationMessage,
    ConversationMessageOrigin,
    ConversationRole,
)
from backend.temporal.temporal_engine import FixedClock, TemporalEngine


def temporal_context():
    engine = TemporalEngine(
        clock=FixedClock(datetime(2026, 8, 29, 9, 30, tzinfo=timezone.utc)),
    )
    return engine.context(
        datetime(2026, 8, 28, 20, 0, tzinfo=timezone.utc),
        user_message="Доброе утро",
    )


def test_turn_context_is_bounded_human_evidence_without_internal_ids():
    envelope = TurnContextEnvelope(
        temporal=TurnTemporalContext.from_temporal_context(temporal_context()),
        recent_turns=(TurnConversationHint(
            reference="T1",
            role="user",
            content="Мы обсуждали занятие по AI.",
        ),),
        active_continuity=TurnContinuityHint(
            topic="обучение AI",
            summary="Продолжить разговор об обучении AI",
            reason_to_return="Выбрать следующий учебный шаг",
        ),
        memory_hints=(TurnMemoryHint(
            reference="M1",
            kind="decision",
            content="Для локальной работы выбрана модель Qwen.",
            time_text="актуально с 2026-08-20",
            confidence=0.9,
        ),),
        presented_entities=(TurnPresentedEntityHint(
            reference="P1", position=1,
            owner_operation_id="google_calendar.read",
            kind="calendar_event",
            human_label="Созвон с мамой, завтра в 14:00",
            time_text="2026-08-30 14:00",
        ),),
        capabilities=(TurnCapabilityHint(
            operation_id="google_calendar.event.update",
            availability="available",
        ),),
    )

    value = envelope.model_safe_value()
    serialized = envelope.model_dump_json()

    assert value["temporal"]["local_date"] == "2026-08-29"
    assert value["active_continuity"]["topic"] == "обучение AI"
    assert value["memory_hints"][0]["state"] == "active"
    assert value["presented_entities"][0]["reference"] == "P1"
    assert "record_id" not in serialized
    assert "provider_id" not in serialized
    assert "conversation_id" not in serialized
    assert "credential" not in serialized


def test_turn_context_rejects_unknown_fields_that_could_smuggle_authority():
    with pytest.raises(ValidationError):
        TurnMemoryHint(
            reference="M1",
            kind="fact",
            content="Миша любит чай.",
            record_id="internal-memory-id",
        )

    with pytest.raises(ValidationError):
        TurnPresentedEntityHint(
            reference="P1",
            position=1,
            owner_operation_id="yandex_mail.read",
            kind="mail",
            human_label="Письмо от Ивана",
            provider_id="opaque-provider-id",
        )


def test_turn_context_requires_unique_ephemeral_references_and_ordinals():
    temporal = TurnTemporalContext.from_temporal_context(temporal_context())
    with pytest.raises(ValidationError):
        TurnContextEnvelope(
            temporal=temporal,
            recent_turns=(TurnConversationHint(
                reference="T1", role="user", content="Покажи письма",
            ),),
            memory_hints=(TurnMemoryHint(
                reference="T1", kind="fact", content="Контекст",
            ),),
        )

    with pytest.raises(ValidationError):
        TurnContextEnvelope(
            temporal=temporal,
            presented_entities=(
                TurnPresentedEntityHint(
                    reference="P1", position=1,
                    owner_operation_id="google_drive.read",
                    kind="file", human_label="Первый файл",
                ),
                TurnPresentedEntityHint(
                    reference="P2", position=1,
                    owner_operation_id="yandex_disk.read",
                    kind="file", human_label="Другой первый файл",
                ),
            ),
        )


def test_turn_context_limits_payload_sizes():
    temporal = TurnTemporalContext.from_temporal_context(temporal_context())
    with pytest.raises(ValidationError):
        TurnContextEnvelope(
            temporal=temporal,
            recent_turns=tuple(
                TurnConversationHint(
                    reference=f"T{index}", role="user", content=str(index),
                )
                for index in range(1, 10)
            ),
        )


def test_builder_projects_real_home_types_without_storage_identity():
    now = datetime(2026, 8, 29, 9, 30, tzinfo=timezone.utc)
    message = ConversationMessage(
        id="internal-message-id",
        conversation_id="internal-conversation-id",
        role=ConversationRole.USER,
        content="Мы обсуждали занятие по AI.",
        created_at=now,
        origin=ConversationMessageOrigin.USER,
    )
    catalog = default_home_capability_catalog()
    snapshot = catalog.snapshot({
        descriptor.operation_id: CapabilityAvailability.AVAILABLE
        for descriptor in catalog.descriptors()
    })

    envelope = TurnContextEnvelopeBuilder().build(
        temporal_context=temporal_context(),
        recent_messages=(message,),
        active_continuity={
            "topic": "обучение",
            "summary": "Продолжить обучение AI",
            "reason_to_return": "Выбрать следующий шаг",
            "internal_thread_id": "must-not-cross-boundary",
        },
        memory_context=({
            "category": "решение",
            "content": "Использовать локальную модель.",
            "state": "актуально",
            "time": "2026-08-20",
            "record_id": "must-not-cross-boundary",
        },),
        capability_snapshot=snapshot,
        presented_context=({
            "position": 1,
            "owner_operation_id": "yandex_mail.read",
            "kind": "письмо",
            "human_label": "Письмо о занятии",
            "time_text": "2026-08-29T09:00:00+00:00",
            "provider_id": "must-not-cross-boundary",
        },),
    )

    serialized = envelope.model_dump_json()
    assert envelope.recent_turns[0].reference == "T1"
    assert envelope.memory_hints[0].reference == "M1"
    assert envelope.active_continuity.topic == "обучение"
    assert envelope.presented_entities[0].reference == "P1"
    assert envelope.presented_entities[0].owner_operation_id == "yandex_mail.read"
    assert len(envelope.capabilities) == len(catalog.descriptors())
    assert "internal-message-id" not in serialized
    assert "internal-conversation-id" not in serialized
    assert "must-not-cross-boundary" not in serialized


def test_previous_application_result_is_bounded_context_not_authority():
    envelope = TurnContextEnvelopeBuilder().build(
        temporal_context=temporal_context(),
        last_application_result=("home.memory.recall", "completed_read"),
    )

    assert envelope.last_application_result is not None
    assert envelope.last_application_result.operation_id == "home.memory.recall"
    assert envelope.last_application_result.projection_state == "completed_read"
    assert "receipt" not in envelope.model_dump_json()
