"""Conversation-safe application owner for read-only Yandex Mail requests."""

from __future__ import annotations

from backend.connectors.presented_read_sets import parse_presented_entity_reference
from backend.memory.text_normalization import meaningful_tokens

from .intent import mail_intent
from .models import MailOutcome


class YandexMailConversationService:
    def __init__(self, *, reader, presented_read_sets=None):
        self.reader = reader
        self._presented = {}
        self.presented_read_sets = presented_read_sets

    def _rows(self, conversation_id):
        if self.presented_read_sets is not None:
            return self.presented_read_sets.items_for(conversation_id, "yandex_mail")
        return self._presented.get(conversation_id, ())

    def _present(self, conversation_id, rows, *, presentation_kind=None):
        self._presented[conversation_id] = rows
        if self.presented_read_sets is not None:
            self.presented_read_sets.present(
                conversation_id,
                "yandex_mail",
                rows,
                entity_kind="письмо",
                presentation_kind=presentation_kind,
            )

    def _contextual_read(self, message, conversation_id):
        if self.presented_read_sets is None:
            return None
        context = self.presented_read_sets.current_context(conversation_id)
        if (
            context is None
            or context.owner != "yandex_mail"
            or context.entity_kind != "письмо"
        ):
            return None
        reference = parse_presented_entity_reference(
            message,
            entity_kind="письмо",
            visible_labels=tuple(item.subject for item in context.items),
        )
        if reference is None:
            return None
        required = "unread" if reference.kind.value == "contextual_class" else None
        resolved = self.presented_read_sets.resolve(
            conversation_id,
            owner="yandex_mail",
            entity_kind="письмо",
            reference=reference,
            label_of=lambda item: item.subject,
            required_presentation_kind=required,
        )
        if resolved.status == "no_context":
            return None
        return (
            MailOutcome("clarification_required")
            if resolved.item is None
            else self.reader.read(resolved.item)
        )

    def observe_resolved(
        self,
        *,
        conversation_id: str,
        original_utterance: str,
        view: str | None = None,
        sender: str | None = None,
        topic: str | None = None,
        target: str | None = None,
    ) -> MailOutcome:
        """Execute validated semantic meaning without re-routing the action."""

        contextual = self._contextual_read(
            " ".join(
                part for part in (original_utterance, target) if part
            ),
            conversation_id,
        )
        if contextual is not None:
            return contextual
        if target is not None:
            return MailOutcome("clarification_required")
        if sender is not None:
            return self._search_and_present(
                "sender", sender, conversation_id=conversation_id,
            )
        if topic is not None:
            return self._search_and_present(
                "topic", topic, conversation_id=conversation_id,
            )
        canonical_view = self._canonical_view(view)
        if canonical_view is None:
            return MailOutcome("clarification_required")
        return self._search_and_present(
            canonical_view,
            None,
            conversation_id=conversation_id,
        )

    def _search_and_present(self, kind, query, *, conversation_id):
        outcome = self.reader.search(kind, query)
        if outcome.status in {"search_completed", "important_completed"}:
            self._present(
                conversation_id,
                outcome.messages,
                presentation_kind=kind,
            )
        return outcome

    @staticmethod
    def _canonical_view(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.casefold().replace("ё", "е").strip()
        if normalized in {"unread", "recent", "today", "important"}:
            return normalized
        tokens = meaningful_tokens(normalized)
        if any(token.startswith("важн") for token in tokens):
            return "important"
        if any(token.startswith("сегодня") for token in tokens):
            return "today"
        if any(
            token.startswith(("последн", "недавн", "свеж"))
            for token in tokens
        ):
            return "recent"
        if any(token.startswith(("нов", "непрочитан")) for token in tokens):
            return "unread"
        return None

    def observe(self, message, *, conversation_id):
        contextual = self._contextual_read(message, conversation_id)
        if contextual is not None:
            return contextual
        intent = mail_intent(message)
        if intent is None:
            return None
        if intent.kind == "read_ordinal":
            rows = self._rows(conversation_id)
            index = (intent.ordinal or 0) - 1
            if rows is None:
                return None
            return (
                MailOutcome("clarification_required")
                if index < 0 or index >= len(rows)
                else self.reader.read(rows[index])
            )
        if intent.kind == "read_name":
            rows = self._rows(conversation_id)
            if rows is None:
                return None
            matches = [
                item for item in rows
                if item.subject.casefold() == intent.query.casefold()
            ]
            return (
                self.reader.read(matches[0])
                if len(matches) == 1
                else MailOutcome("clarification_required")
            )
        return self._search_and_present(
            intent.kind,
            intent.query,
            conversation_id=conversation_id,
        )

    @staticmethod
    def human_result(outcome):
        if outcome.status == "search_completed":
            return "Нашла в Яндекс Почте:\n" + "\n".join(
                f"{index}. {item.subject} — {item.sender}"
                for index, item in enumerate(outcome.messages, 1)
            )
        return {
            "disconnected": "Яндекс Почта не подключена.",
            "needs_reconnect": "Нужно переподключить Яндекс Почту.",
            "unavailable": "Сейчас не удалось обратиться к почте.",
            "no_unread": "Новых непрочитанных писем нет.",
            "no_messages": "Писем по этому запросу не нашла.",
            "message_too_large": "Это письмо слишком большое для безопасного чтения.",
            "clarification_required": "Уточни, какое именно письмо прочитать.",
        }.get(outcome.status, "Не смогла разобрать содержимое этого письма.")
