"""Source-neutral, bounded document interpretation contracts."""

from .errors import DocumentReadError
from .models import (
    DocumentEvidence,
    DocumentFormat,
    DocumentInput,
    DocumentPageEvidence,
    DocumentReadReceipt,
    DocumentReadSourceKind,
)
from .reader import DocumentReader
from .store import DocumentReadStore

__all__ = [
    "DocumentEvidence",
    "DocumentFormat",
    "DocumentInput",
    "DocumentPageEvidence",
    "DocumentReadError",
    "DocumentReadReceipt",
    "DocumentReadSourceKind",
    "DocumentReader",
    "DocumentReadStore",
]
