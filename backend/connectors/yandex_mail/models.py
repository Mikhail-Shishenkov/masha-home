from __future__ import annotations
import re
from dataclasses import dataclass
from datetime import datetime


_MESSAGE_ID = re.compile(r"^<[!-~]{1,496}>$")


def safe_message_id(value: str | None) -> str | None:
    """Return one command-safe RFC-style Message-ID or fail closed."""

    candidate = (value or "").strip()
    if not _MESSAGE_ID.fullmatch(candidate) or any(
        character in candidate for character in {'"', "\\"}
    ):
        return None
    return candidate


@dataclass(frozen=True)
class MailMessageSummary:
    provider: str; message_ref: str; subject: str; sender: str; received_at: datetime | None; size: int | None; has_attachments: bool
    uidvalidity: str | None = None
    message_id: str | None = None
    def model_value(self): return {"subject": self.subject, "sender": self.sender, "received_at": None if self.received_at is None else self.received_at.isoformat(), "has_attachments": self.has_attachments}
@dataclass(frozen=True)
class MailMessageContent:
    summary: MailMessageSummary; body: str; attachments: tuple[dict, ...] = ()
    def model_value(self): return {"kind":"mail_message", "message":self.summary.model_value(), "body":self.body, "attachments":list(self.attachments)}
@dataclass(frozen=True)
class ResolvedMailRequest:
    subject: str; sender: str
    def model_message(self): return f'Пользователь выбрал письмо «{self.subject}» от «{self.sender}». Прочитай выбранное письмо и ответь по содержимому. Ссылка на первое, второе, третье или тему уже разрешена приложением как выбор письма; не трактуй её как номер части, абзаца или пункта письма.'
@dataclass(frozen=True)
class MailOutcome:
    status: str; messages: tuple[MailMessageSummary,...]=(); content: MailMessageContent|None=None; resolved_request: ResolvedMailRequest|None=None
