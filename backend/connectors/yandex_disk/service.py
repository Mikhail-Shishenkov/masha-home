"""Application-owned Yandex Disk presentation and selection."""

from __future__ import annotations

from backend.connectors.presented_read_sets import (
    PresentedEntityReferenceKind,
    parse_presented_entity_reference,
)

from .intent import disk_intent
from .reader import DiskFileCandidate, DiskReadOutcome, YandexDiskReader


class YandexDiskConversationService:
    def __init__(self, *, reader: YandexDiskReader, presented_read_sets=None):
        self.reader = reader
        self._presented: dict[str, tuple[DiskFileCandidate, ...]] = {}
        self.presented_read_sets = presented_read_sets

    def _files(self, conversation_id: str) -> tuple[DiskFileCandidate, ...] | None:
        if self.presented_read_sets is not None:
            rows = self.presented_read_sets.items_for(conversation_id, "yandex_disk")
            return None if rows is None else tuple(rows)
        return self._presented.get(conversation_id, ())

    def _present(self, conversation_id: str, files: tuple[DiskFileCandidate, ...]) -> None:
        self._presented[conversation_id] = files
        if self.presented_read_sets is not None:
            self.presented_read_sets.present(conversation_id, "yandex_disk", files)

    def observe(self, message: str, *, conversation_id: str) -> DiskReadOutcome | None:
        intent = disk_intent(message)
        if intent is None:
            return None
        if intent.kind == "clarify":
            return DiskReadOutcome("clarification_required")
        if intent.kind == "read_ordinal":
            files = self._files(conversation_id)
            if files is None:
                return None
            index = (intent.ordinal or 0) - 1
            return DiskReadOutcome("clarification_required") if index < 0 or index >= len(files) else self.reader.read_file(files[index])
        if intent.kind == "read_name":
            files = self._files(conversation_id)
            if files is None:
                found = self.reader.search(intent.query or "")
                if found.status != "search_completed":
                    return found
                files = found.files
                self._present(conversation_id, files)
            matches = tuple(file for file in files if _same_name(file.name, intent.query or ""))
            return self.reader.read_file(matches[0]) if len(matches) == 1 else DiskReadOutcome("clarification_required")
        outcome = self.reader.recent() if intent.kind == "recent" else (self.reader.list_files() if intent.kind == "list" else self.reader.search(intent.query or ""))
        if outcome.status == "search_completed":
            self._present(conversation_id, outcome.files)
        return outcome

    def observe_resolved(
        self,
        *,
        conversation_id: str,
        original_utterance: str,
        mode: str,
        query: str | None = None,
        target: str | None = None,
    ) -> DiskReadOutcome:
        """Execute already validated file meaning without re-routing language."""

        if mode == "recent":
            outcome = self.reader.recent()
        elif mode == "list":
            outcome = self.reader.list_files()
        elif mode == "search":
            outcome = (
                DiskReadOutcome("clarification_required")
                if not query
                else self.reader.search(query)
            )
        elif mode == "read" and target is not None:
            selected = self._resolve_presented_target(
                conversation_id,
                original_utterance,
            )
            return (
                self.reader.read_file(selected)
                if selected is not None
                else DiskReadOutcome("clarification_required")
            )
        elif mode == "read" and query:
            found = self.reader.search(query)
            if found.status != "search_completed":
                return found
            matches = tuple(
                file for file in found.files if _same_name(file.name, query)
            )
            if len(matches) != 1:
                self._present(conversation_id, found.files)
                return DiskReadOutcome("clarification_required", files=found.files)
            return self.reader.read_file(matches[0])
        else:
            return DiskReadOutcome("clarification_required")
        if outcome.status == "search_completed":
            self._present(conversation_id, outcome.files)
        return outcome

    def _resolve_presented_target(
        self,
        conversation_id: str,
        utterance: str,
    ) -> DiskFileCandidate | None:
        files = self._files(conversation_id)
        if not files:
            return None
        reference = parse_presented_entity_reference(
            utterance,
            entity_kind="файл",
            visible_labels=tuple(item.name for item in files),
        )
        if reference is None:
            return None
        if reference.kind is PresentedEntityReferenceKind.ORDINAL:
            index = (reference.ordinal or 0) - 1
            return files[index] if 0 <= index < len(files) else None
        if reference.kind is PresentedEntityReferenceKind.EXACT_LABEL:
            matches = tuple(
                item for item in files
                if _same_name(item.name, reference.label or "")
            )
            return matches[0] if len(matches) == 1 else None
        return files[0] if len(files) == 1 else None

    def attach_assistant_message(self, outcome: DiskReadOutcome, message_id: str) -> None:
        receipt = outcome.document_receipt
        if receipt is not None and self.reader.document_store is not None:
            self.reader.document_store.attach_assistant_message(receipt.receipt_id, message_id)

    @staticmethod
    def human_result(outcome: DiskReadOutcome) -> str:
        if outcome.status == "search_completed":
            suffix = "\nПоиск был ограничен, поэтому файл мог не попасть в просмотренную часть Диска." if outcome.scan_limited else ""
            return "Нашла на Яндекс Диске:\n" + "\n".join(
                f"{index}. {item.name}" + ("" if item.readable else " — этот формат пока не умею читать")
                for index, item in enumerate(outcome.files, start=1)
            ) + suffix
        if outcome.status == "no_files" and outcome.scan_limited:
            return "Подходящих файлов не нашла. Поиск был ограничен, поэтому файл мог не попасть в просмотренную часть Диска."
        return {
            "disconnected": "Яндекс Диск не подключён.",
            "needs_reconnect": "Нужно переподключить Яндекс Диск.",
            "unavailable": "Сейчас не удалось обратиться к Яндекс Диску.",
            "no_files": "Подходящих файлов не нашла.",
            "unsupported_format": "Этот формат я пока не умею читать.",
            "document_too_large": "Документ слишком большой для безопасного чтения.",
            "document_unreadable": "Этот документ сейчас не получилось прочитать.",
            "clarification_required": "Уточни, какой именно файл прочитать.",
        }.get(outcome.status, "Сейчас не удалось обратиться к Яндекс Диску.")


def _same_name(name: str, requested: str) -> bool:
    return " ".join(name.casefold().split()) == " ".join(requested.casefold().split())
