"""Trusted native-picker adapter for one ephemeral local PDF selection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .errors import DocumentReadError
from .models import DocumentInput, DocumentReadSourceKind
from .reader import MAX_RAW_PDF_BYTES


class LocalDocumentInputError(RuntimeError):
    """Controlled local-input failure; paths are deliberately never included."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class LocalDocumentSelection(BaseModel):
    """The only local-selection projection that may cross the UI boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    token: str = Field(min_length=20, max_length=100)
    display_name: str = Field(min_length=1, max_length=300)
    byte_size: int = Field(ge=0, le=MAX_RAW_PDF_BYTES)


@dataclass(frozen=True)
class _StagedDocument:
    token: str
    display_name: str
    content: bytes
    source_reference: str


class LocalDocumentInputService:
    """Stages one user-selected PDF in memory and never persists path or bytes."""

    def __init__(self, *, max_bytes: int = MAX_RAW_PDF_BYTES):
        self.max_bytes = max_bytes
        self._staged: _StagedDocument | None = None

    def stage_selected_path(self, selected_path: str | Path) -> LocalDocumentSelection:
        """Read at most max+1 bytes from the trusted native picker result."""
        self.clear()
        path = Path(selected_path)
        try:
            if path.is_symlink():
                raise LocalDocumentInputError("local_document_symlink_unsupported")
            if not path.is_file():
                raise LocalDocumentInputError("local_document_not_regular_file")
            if path.stat().st_size > self.max_bytes:
                raise LocalDocumentInputError("local_document_too_large")
            with path.open("rb") as source:
                content = source.read(self.max_bytes + 1)
        except LocalDocumentInputError:
            raise
        except OSError as error:
            raise LocalDocumentInputError("local_document_unavailable") from error

        if len(content) > self.max_bytes:
            raise LocalDocumentInputError("local_document_too_large")
        token = f"local_doc_{uuid4()}"
        display_name = path.name[:300].strip() or "document.pdf"
        self._staged = _StagedDocument(
            token=token,
            display_name=display_name,
            content=content,
            source_reference=f"local_input_{uuid4()}",
        )
        return LocalDocumentSelection(
            token=token,
            display_name=display_name,
            byte_size=len(content),
        )

    def consume(self, token: str) -> DocumentInput:
        staged = self._staged
        if staged is None or token != staged.token:
            raise LocalDocumentInputError("local_document_token_invalid")
        self._staged = None
        try:
            return DocumentInput(
                content=staged.content,
                source_kind=DocumentReadSourceKind.LOCAL,
                display_name=staged.display_name,
                source_reference=staged.source_reference,
            )
        except Exception as error:
            raise DocumentReadError("pdf_unreadable") from error

    def clear(self, token: str | None = None) -> bool:
        staged = self._staged
        if staged is None:
            return False
        if token is not None and token != staged.token:
            return False
        self._staged = None
        return True
