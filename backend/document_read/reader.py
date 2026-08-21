"""Pure local interpretation of already-authorized PDF bytes."""

from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
from io import BytesIO
from threading import RLock

from pypdf import PdfReader
from pypdf import filters as pypdf_filters
from pypdf.errors import LimitReachedError

from .errors import DocumentReadError
from .models import DocumentEvidence, DocumentInput, DocumentPageEvidence


MAX_RAW_PDF_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 100
MAX_DOCUMENT_TEXT_CHARS = 16_000
MAX_PAGE_TEXT_CHARS = 3_000
MAX_DECODED_CONTENT_STREAM_BYTES = 8 * 1024 * 1024
ROOT_OBJECT_RECOVERY_LIMIT = 1_000

# pypdf documents these as process-level controls. Its public API has no
# per-reader stream-output setting, so serialization plus restoration keeps
# W4's tighter boundary scoped to the synchronous Document Reader invocation.
_PYPDF_LIMIT_LOCK = RLock()
_PYPDF_BYTE_LIMITS = (
    "MAX_DECLARED_STREAM_LENGTH",
    "MAX_ARRAY_BASED_STREAM_OUTPUT_LENGTH",
    "ZLIB_MAX_OUTPUT_LENGTH",
    "LZW_MAX_OUTPUT_LENGTH",
    "RUN_LENGTH_MAX_OUTPUT_LENGTH",
    "JBIG2_MAX_OUTPUT_LENGTH",
    "FLATE_MAX_BUFFER_SIZE",
)
_PYPDF_DISABLED_HELPERS = ("JBIG2DEC_BINARY",)


class DocumentReader:
    """Reads text-layer PDFs only; it never opens a source or executes PDF content."""

    def read(self, document: DocumentInput) -> DocumentEvidence:
        raw = document.content
        if len(raw) > MAX_RAW_PDF_BYTES:
            raise DocumentReadError("pdf_input_too_large")
        if not raw.startswith(b"%PDF-"):
            raise DocumentReadError("pdf_unreadable")
        stream = BytesIO(raw)
        reader = None
        try:
            with self._bounded_pypdf_limits():
                reader = PdfReader(
                    stream,
                    strict=False,
                    root_object_recovery_limit=ROOT_OBJECT_RECOVERY_LIMIT,
                )
                if reader.is_encrypted:
                    raise DocumentReadError("pdf_encrypted_unsupported")
                page_count = len(reader.pages)
                if page_count < 1:
                    raise DocumentReadError("pdf_text_unavailable")
                if page_count > MAX_PDF_PAGES:
                    raise DocumentReadError("pdf_page_limit_exceeded")

                pages: list[DocumentPageEvidence] = []
                extracted_chars = 0
                pages_read = 0
                document_truncated = False
                for page_number, page in enumerate(reader.pages, start=1):
                    pages_read = page_number
                    text = self._normalize_text(page.extract_text() or "")
                    if not text:
                        continue
                    remaining = MAX_DOCUMENT_TEXT_CHARS - extracted_chars
                    if remaining <= 0:
                        document_truncated = True
                        break
                    page_limit = min(MAX_PAGE_TEXT_CHARS, remaining)
                    page_text = text[:page_limit].rstrip()
                    page_truncated = len(text) > len(page_text)
                    document_truncated = document_truncated or page_truncated
                    if page_text:
                        pages.append(DocumentPageEvidence(
                            page_number=page_number,
                            text=page_text,
                            truncated=page_truncated,
                        ))
                        extracted_chars += len(page_text)
                    if extracted_chars >= MAX_DOCUMENT_TEXT_CHARS:
                        document_truncated = document_truncated or page_number < page_count
                        break
                if not pages:
                    raise DocumentReadError("pdf_text_unavailable")
                return DocumentEvidence(
                    title=self._metadata_title(reader),
                    page_count=page_count,
                    pages_read=pages_read,
                    extracted_chars=extracted_chars,
                    truncated=document_truncated,
                    content_sha256=sha256(raw).hexdigest(),
                    pages=tuple(pages),
                )
        except LimitReachedError as error:
            raise DocumentReadError("pdf_resource_limit_exceeded") from error
        except DocumentReadError:
            raise
        except Exception as error:
            raise DocumentReadError("pdf_unreadable") from error
        finally:
            if reader is not None:
                try:
                    reader.close()
                except Exception:
                    pass
            stream.close()

    @staticmethod
    @contextmanager
    def _bounded_pypdf_limits():
        """Temporarily scope pypdf's process-global decoding limits.

        ``contextmanager`` keeps setup failures inside a try/finally boundary:
        no successful lock acquisition can escape without restoration and release.
        """
        _PYPDF_LIMIT_LOCK.acquire()
        previous: dict[str, object] = {}
        try:
            for name in _PYPDF_BYTE_LIMITS:
                previous[name] = getattr(pypdf_filters, name)
                setattr(
                    pypdf_filters,
                    name,
                    min(previous[name], MAX_DECODED_CONTENT_STREAM_BYTES),
                )
            for name in _PYPDF_DISABLED_HELPERS:
                previous[name] = getattr(pypdf_filters, name)
                setattr(pypdf_filters, name, None)
            yield
        finally:
            try:
                for name, value in reversed(tuple(previous.items())):
                    setattr(pypdf_filters, name, value)
            finally:
                _PYPDF_LIMIT_LOCK.release()

    @staticmethod
    def _normalize_text(value: str) -> str:
        # Preserve paragraph/line provenance while removing control noise.
        rows = ["".join(char for char in row if char >= " " or char in "\n\t").strip() for row in value.splitlines()]
        return "\n".join(row for row in rows if row).strip()

    @staticmethod
    def _metadata_title(reader: PdfReader) -> str | None:
        try:
            value = getattr(reader.metadata, "title", None)
        except Exception:
            return None
        if not isinstance(value, str):
            return None
        title = " ".join(value.split())[:300].strip()
        return title or None
