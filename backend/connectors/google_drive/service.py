"""Application-owned Drive result presentation and conversation-scoped selection."""

from __future__ import annotations

from .intent import drive_intent
from .reader import DriveFileCandidate, DriveReadOutcome, GoogleDriveReader


class GoogleDriveConversationService:
    def __init__(self, *, reader: GoogleDriveReader):
        self.reader = reader
        self._presented: dict[str, tuple[DriveFileCandidate, ...]] = {}

    def observe(self, message: str, *, conversation_id: str) -> DriveReadOutcome | None:
        intent = drive_intent(message)
        if intent is None:
            return None
        if intent.kind == "clarify":
            return DriveReadOutcome("clarification_required")
        if intent.kind == "read_ordinal":
            candidates = self._presented.get(conversation_id, ())
            index = (intent.ordinal or 0) - 1
            if index < 0 or index >= len(candidates):
                return DriveReadOutcome("clarification_required")
            return self.reader.read_file(candidates[index])
        assert intent.query is not None
        if intent.kind == "read_presented_name":
            exact = tuple(
                item for item in self._presented.get(conversation_id, ())
                if _same_name(item.name, intent.query)
            )
            return self.reader.read_file(exact[0]) if len(exact) == 1 else None
        found = self.reader.search(intent.query)
        if intent.kind == "search" or found.status != "search_completed":
            if found.status == "search_completed":
                self._presented[conversation_id] = found.files
            return found
        if intent.kind == "search_read":
            if len(found.files) != 1:
                if found.files:
                    self._presented[conversation_id] = found.files
                return DriveReadOutcome("clarification_required", files=found.files)
            return self.reader.read_file(found.files[0])
        exact = tuple(item for item in found.files if _same_name(item.name, intent.query))
        if len(exact) != 1:
            if found.files:
                self._presented[conversation_id] = found.files
            return DriveReadOutcome("clarification_required", files=found.files)
        return self.reader.read_file(exact[0])

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
