"""Application-owned Drive result presentation and conversation-scoped selection."""

from __future__ import annotations

from backend.connectors.presented_read_sets import (
    PresentedEntityReferenceKind,
    parse_presented_entity_reference,
)

from .intent import drive_intent
from .reader import DriveFileCandidate, DriveReadOutcome, GoogleDriveReader


class GoogleDriveConversationService:
    def __init__(self, *, reader: GoogleDriveReader, presented_read_sets=None):
        self.reader = reader
        self._presented: dict[str, tuple[DriveFileCandidate, ...]] = {}
        self.presented_read_sets = presented_read_sets

    def _candidates(self, conversation_id: str) -> tuple[DriveFileCandidate, ...] | None:
        if self.presented_read_sets is not None:
            rows = self.presented_read_sets.items_for(conversation_id, "google_drive")
            return None if rows is None else tuple(rows)
        return self._presented.get(conversation_id, ())

    def _present(self, conversation_id: str, files: tuple[DriveFileCandidate, ...]) -> None:
        self._presented[conversation_id] = files
        if self.presented_read_sets is not None:
            self.presented_read_sets.present(conversation_id, "google_drive", files)

    def observe(self, message: str, *, conversation_id: str) -> DriveReadOutcome | None:
        intent = drive_intent(message)
        if intent is None:
            return None
        if intent.kind == "clarify":
            return DriveReadOutcome("clarification_required")
        if intent.kind == "list":
            found = self.reader.search("")
            if found.status == "search_completed":
                self._present(conversation_id, found.files)
            return found
        if intent.kind == "recent":
            found = self.reader.search("")
            if found.status == "search_completed":
                self._present(conversation_id, found.files)
            return found
        if intent.kind == "read_ordinal":
            candidates = self._candidates(conversation_id)
            if candidates is None:
                return None
            index = (intent.ordinal or 0) - 1
            if index < 0 or index >= len(candidates):
                # A bare ordinal is deliberately shared by human read surfaces.
                # If Drive has not presented a candidate list for this conversation,
                # let the next application-owned resolver (for example Mail) decide.
                return None
            return self.reader.read_file(candidates[index])
        assert intent.query is not None
        if intent.kind == "read_presented_name":
            exact = tuple(
                item for item in (self._candidates(conversation_id) or ())
                if _same_name(item.name, intent.query)
            )
            return self.reader.read_file(exact[0]) if len(exact) == 1 else None
        found = self.reader.search(intent.query)
        if intent.kind == "search" or found.status != "search_completed":
            if found.status == "search_completed":
                self._present(conversation_id, found.files)
            return found
        if intent.kind == "search_read":
            if len(found.files) != 1:
                if found.files:
                    self._present(conversation_id, found.files)
                return DriveReadOutcome("clarification_required", files=found.files)
            return self.reader.read_file(found.files[0])
        exact = tuple(item for item in found.files if _same_name(item.name, intent.query))
        if len(exact) != 1:
            if found.files:
                self._present(conversation_id, found.files)
            return DriveReadOutcome("clarification_required", files=found.files)
        return self.reader.read_file(exact[0])

    def observe_resolved(
        self,
        *,
        conversation_id: str,
        original_utterance: str,
        mode: str,
        query: str | None = None,
        target: str | None = None,
    ) -> DriveReadOutcome:
        """Execute already validated file meaning without re-routing language."""

        if mode in {"list", "recent"}:
            found = self.reader.search("")
            if found.status == "search_completed":
                self._present(conversation_id, found.files)
            return found
        if mode == "search":
            if not query:
                return DriveReadOutcome("clarification_required")
            found = self.reader.search(query)
            if found.status == "search_completed":
                self._present(conversation_id, found.files)
            return found
        if mode != "read":
            return DriveReadOutcome("clarification_required")

        if target is not None:
            selected = self._resolve_presented_target(
                conversation_id,
                original_utterance,
            )
            return (
                self.reader.read_file(selected)
                if selected is not None
                else DriveReadOutcome("clarification_required")
            )
        if not query:
            return DriveReadOutcome("clarification_required")
        found = self.reader.search(query)
        if found.status != "search_completed":
            return found
        exact = tuple(item for item in found.files if _same_name(item.name, query))
        if len(exact) != 1:
            self._present(conversation_id, found.files)
            return DriveReadOutcome("clarification_required", files=found.files)
        return self.reader.read_file(exact[0])

    def _resolve_presented_target(
        self,
        conversation_id: str,
        utterance: str,
    ) -> DriveFileCandidate | None:
        candidates = self._candidates(conversation_id)
        if not candidates:
            return None
        reference = parse_presented_entity_reference(
            utterance,
            entity_kind="файл",
            visible_labels=tuple(item.name for item in candidates),
        )
        if reference is None:
            return None
        if reference.kind is PresentedEntityReferenceKind.ORDINAL:
            index = (reference.ordinal or 0) - 1
            return candidates[index] if 0 <= index < len(candidates) else None
        if reference.kind is PresentedEntityReferenceKind.EXACT_LABEL:
            matches = tuple(
                item for item in candidates
                if _same_name(item.name, reference.label or "")
            )
            return matches[0] if len(matches) == 1 else None
        return candidates[0] if len(candidates) == 1 else None

    def attach_assistant_message(self, outcome: DriveReadOutcome, message_id: str) -> None:
        """Keep the existing bounded Document Read receipt linked to its answer."""
        receipt = outcome.document_receipt
        store = self.reader.document_store
        if receipt is not None and store is not None:
            store.attach_assistant_message(receipt.receipt_id, message_id)

    @staticmethod
    def human_result(outcome: DriveReadOutcome) -> str:
        if outcome.status == "search_completed":
            return "Нашла в Google Drive:\n" + "\n".join(
                f"{index}. {item.name}" + ("" if item.readable else " — этот формат пока не умею читать")
                for index, item in enumerate(outcome.files, start=1)
            )
        return {
            "disconnected": "Google Drive не подключён.",
            "needs_reconnect": "Нужно переподключить Google Drive.",
            "unavailable": "Сейчас не удалось обратиться к Google Drive.",
            "no_files": "Ничего подходящего в Drive не нашла.",
            "unsupported_format": "Этот формат я пока не умею читать.",
            "document_too_large": "Документ слишком большой для безопасного чтения.",
            "document_unreadable": "Этот документ сейчас не получилось безопасно прочитать.",
            "clarification_required": "Уточни, какой именно файл прочитать.",
        }.get(outcome.status, "Сейчас не удалось обратиться к Google Drive.")


def _same_name(name: str, requested: str) -> bool:
    return " ".join(name.casefold().split()) == " ".join(requested.casefold().split())
