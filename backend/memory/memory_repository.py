"""Small storage boundary for the active validated MemoryDocument."""

from __future__ import annotations

from typing import Protocol

from .memory_models import MemoryDocument


class MemoryDocumentRepository(Protocol):
    """A local store capable of replacing a validated document."""

    def read_document(self) -> MemoryDocument | None:
        ...

    def replace_document(
        self,
        document: MemoryDocument,
        *,
        action: str = "replace_document",
        audit_payload: dict | None = None,
    ) -> None:
        ...
