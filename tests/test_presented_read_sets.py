from dataclasses import dataclass
from datetime import datetime, timezone

from backend.connectors.presented_read_sets import PresentedReadSetRegistry


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
