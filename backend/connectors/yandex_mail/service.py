"""Conversation-safe application owner for read-only Yandex Mail requests."""

from __future__ import annotations

from backend.connectors.presented_read_sets import parse_presented_entity_reference
from backend.memory.text_normalization import normalize_search_text
from backend.connectors.provider_language import is_listing_command

from .intent import mail_intent
from .models import MailOutcome


_MAILBOX_WORDS = frozenset({
    "письмо", "письма", "почта", "почту", "почте", "новые", "непрочитанные",
    "последние", "все", "мою", "моя", "у", "меня", "за", "сегодня", "входящие",
})


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
            else self._read(resolved.item, conversation_id)
        )

    def _read(self, item, conversation_id):
        outcome = self.reader.read(item)
        if outcome.status == "read_completed" and self.presented_read_sets is not None:
            self.presented_read_sets.focus_read_item(conversation_id, "yandex_mail", item)
        return outcome

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

        # A resolved mailbox view is a listing, not a reference into a prior
        # list. Do not let stale presented context turn it into a single read.
        # Some local models copy the action into this optional filter. It is
        # not a filter: use the existing generic-check default, only AFTER
        # Home has validated and handed off a mail-read request.
        if view is not None and is_listing_command(view):
            view = None
        canonical_view = self._canonical_view(view)
        generic_target = target is not None and set(normalize_search_text(target).split()) <= _MAILBOX_WORDS
        if generic_target:
            if canonical_view is None and normalize_search_text(target) == "письмо":
                return MailOutcome("clarification_required")
            canonical_view = canonical_view or self._canonical_view(target)
            if canonical_view is None:
                canonical_view = "unread"
            target = None
        if canonical_view is not None and sender is None and topic is None and target is None:
            return self._search_and_present(
                canonical_view, None, conversation_id=conversation_id,
            )
        contextual = self._contextual_read(
            " ".join(
                part for part in (original_utterance, target) if part
            ),
            conversation_id,
        )
        if contextual is not None:
            return contextual
        if target is not None:
            reference = parse_presented_entity_reference(
                target, entity_kind="письмо", require_read_action=False,
            )
            if reference is not None:
                context = self.presented_read_sets
                if context is None:
                    return MailOutcome("clarification_required")
                resolved = context.resolve(
                    conversation_id, owner="yandex_mail", entity_kind="письмо",
                    reference=reference, label_of=lambda item: item.subject,
                )
                return (self._read(resolved.item, conversation_id) if resolved.item is not None
                        else MailOutcome("clarification_required"))
            return self._read_subject(target, conversation_id)
        if sender is not None:
            return self._search_and_present(
                "sender", sender, conversation_id=conversation_id,
            )
        if topic is not None:
            return self._search_and_present(
                "topic", topic, conversation_id=conversation_id,
            )
        if view is not None and canonical_view is None:
            return MailOutcome("clarification_required")
        return self._search_and_present(
            canonical_view or "unread",
            None,
            conversation_id=conversation_id,
        )

    def _search_and_present(self, kind, query, *, conversation_id):
        outcome = self.reader.search(kind, query)
        if outcome.status in {"search_completed", "important_completed", "no_unread", "no_messages"}:
            self._present(
                conversation_id,
                outcome.messages,
                presentation_kind=kind,
            )
        return outcome

    def _read_subject(self, subject, conversation_id):
        """Search real mailbox metadata, never infer an ID from a title."""
        outcome = self._search_and_present("topic", subject[:300], conversation_id=conversation_id)
        if outcome.status == "search_completed" and len(outcome.messages) == 1:
            return self._read(outcome.messages[0], conversation_id)
        return outcome

    @staticmethod
    def _canonical_view(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.casefold().replace("ё", "е").strip()
        if normalized in {"unread", "recent", "today", "important"}:
            return normalized
        # Memory's stop-word filter deliberately drops "сегодня". A mailbox
        # view is a temporal filter, not a memory relevance query.
        tokens = normalize_search_text(normalized).split()
        if any(token.startswith("важн") for token in tokens):
            return "important"
        if "сегодня" in tokens:
            return "today"
        if any(
            token.startswith(("последн", "недавн", "свеж"))
            for token in tokens
        ):
            return "recent"
        if any(token.startswith(("нов", "непрочитан")) for token in tokens):
            return "unread"
        if tokens and set(tokens) <= _MAILBOX_WORDS:
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
                else self._read(rows[index], conversation_id)
            )
        if intent.kind == "read_name":
            return self._read_subject(intent.query, conversation_id)
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
