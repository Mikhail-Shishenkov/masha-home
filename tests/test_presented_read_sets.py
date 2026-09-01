from dataclasses import dataclass
from datetime import datetime, timezone

from backend.connectors.presented_read_sets import PresentedReadSetRegistry
from backend.conversation.human_reference import (
    HumanEntityAction,
    HumanEntityKind,
    PresentedEntityRef,
    PresentedEntitySet,
)


@dataclass(frozen=True)
class MailRow:
    provider_message_id: str
    subject: str
    received_at: datetime


def test_presented_set_projects_human_context_without_provider_identity():
    registry = PresentedReadSetRegistry()
    registry.present(
        "conversation-internal-id",
        "yandex_mail",
        (MailRow(
            provider_message_id="provider-internal-id",
            subject="Письмо о занятии",
            received_at=datetime(2026, 8, 29, 9, 0, tzinfo=timezone.utc),
        ),),
        entity_kind="письмо",
        presentation_kind="unread",
    )

    hints = registry.model_safe_hints("conversation-internal-id")

    assert hints == ({
        "position": 1,
        "owner_operation_id": "yandex_mail.read",
        "kind": "письмо",
        "human_label": "Письмо о занятии",
        "time_text": "2026-08-29 09:00:00+00:00",
    },)
    assert "provider-internal-id" not in repr(hints)
    assert "conversation-internal-id" not in repr(hints)


def test_unknown_presented_owner_is_not_projected_into_language_context():
    registry = PresentedReadSetRegistry()
    registry.present(
        "conversation",
        "future_connector",
        (MailRow("id", "Неизвестный объект", datetime.now(timezone.utc)),),
    )

    assert registry.model_safe_hints("conversation") == ()


def test_home_lists_share_latest_reference_ownership_without_entity_ids():
    registry = PresentedReadSetRegistry()
    registry.present_home_entities(PresentedEntitySet(
        conversation_id="conversation",
        source_kind="shared_history",
        created_at=datetime(2026, 8, 29, 9, 0, tzinfo=timezone.utc),
        items=(
            PresentedEntityRef(
                ordinal=1,
                entity_kind=HumanEntityKind.MEMORY,
                entity_id="memory-secret-id",
                human_label="Миша любит чай",
                allowed_actions=(HumanEntityAction.FORGET,),
            ),
            PresentedEntityRef(
                ordinal=2,
                entity_kind=HumanEntityKind.THREAD,
                entity_id="thread-secret-id",
                human_label="Обсудить локальную модель",
                allowed_actions=(HumanEntityAction.RESOLVE_CONTINUITY,),
            ),
        ),
    ))

    hints = registry.model_safe_hints("conversation")

    assert [item["owner_operation_id"] for item in hints] == [
        "home.memory.inspect",
        "home.continuity.read",
    ]
    assert [item["position"] for item in hints] == [1, 2]
    assert "secret-id" not in repr(hints)

    registry.present(
        "conversation",
        "yandex_mail",
        (MailRow("mail-id", "Новое письмо", datetime.now(timezone.utc)),),
        entity_kind="письмо",
    )
    assert registry.model_safe_hints("conversation")[0]["owner_operation_id"] == (
        "yandex_mail.read"
    )
