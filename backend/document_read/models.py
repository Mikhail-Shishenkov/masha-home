"""Small source-neutral input, evidence and receipt models for Document Read."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


class _DocumentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DocumentFormat(str, Enum):
    PDF = "pdf"


class DocumentReadSourceKind(str, Enum):
    WEB = "web"
    LOCAL = "local"
    CONNECTOR = "connector"


class DocumentInput(_DocumentModel):
    """Already-authorized bytes only; this contract carries no access authority."""

    media_type: Literal["application/pdf"] = "application/pdf"
    # The reader maps an over-limit body to its controlled product failure;
    # validation must not turn a normal document turn into a Pydantic error.
    content: bytes = Field(min_length=5)
    source_kind: DocumentReadSourceKind
    display_name: str | None = Field(default=None, max_length=300)
    source_reference: str | None = Field(default=None, max_length=200)


class DocumentPageEvidence(_DocumentModel):
    page_number: int = Field(ge=1, le=100)
    text: str = Field(min_length=1, max_length=3_000)
    truncated: bool = False


class DocumentEvidence(_DocumentModel):
    format: Literal[DocumentFormat.PDF] = DocumentFormat.PDF
    media_type: Literal["application/pdf"] = "application/pdf"
    title: str | None = Field(default=None, max_length=300)
    page_count: int = Field(ge=1, le=100)
    pages_read: int = Field(ge=1, le=100)
    extracted_chars: int = Field(ge=1, le=16_000)
    truncated: bool = False
    content_sha256: str = Field(
        pattern=r"^[a-f0-9]{64}$",
        description="SHA-256 of the exact raw PDF bytes supplied to Document Reader.",
    )
    extractor_id: Literal["pypdf-6"] = "pypdf-6"
    pages: tuple[DocumentPageEvidence, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def evidence_is_coherent(self):
        if self.pages_read > self.page_count:
            raise ValueError("pages_read cannot exceed page_count")
        if self.extracted_chars != sum(len(page.text) for page in self.pages):
            raise ValueError("extracted_chars must equal bounded page evidence")
        return self


class DocumentReadReceipt(_DocumentModel):
    """Persistable provenance without raw document bytes or access credentials."""

    receipt_id: str = Field(min_length=8, max_length=100)
    source_kind: DocumentReadSourceKind
    source_reference: str = Field(min_length=1, max_length=200)
    display_name: str | None = Field(default=None, max_length=300)
    evidence: DocumentEvidence
    completed_at: AwareDatetime
    assistant_message_id: str | None = Field(default=None, max_length=100)

    @field_validator("display_name")
    @classmethod
    def bounded_display_name(cls, value: str | None) -> str | None:
        return None if value is None else value.strip()[:300] or None


class DocumentReadState(_DocumentModel):
    schema_version: Literal["1.0"] = "1.0"
    receipts: tuple[DocumentReadReceipt, ...] = ()
