"""Application-owned one-turn local document execution."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from backend.document_read import (
    DocumentReadReceipt,
    DocumentReadSourceKind,
    DocumentReadStore,
    DocumentReader,
    LocalDocumentInputError,
    LocalDocumentInputService,
    LocalDocumentSelection,
)
from backend.skills.models import SkillCapability
from backend.skills.registry import SkillRegistry, SkillRegistryError


class LocalDocumentTurnService:
    """Consumes a staged token once, then uses the source-neutral reader."""

    def __init__(
        self,
        *,
        inputs: LocalDocumentInputService,
        reader: DocumentReader,
        store: DocumentReadStore,
        registry: SkillRegistry | None = None,
        clock=None,
    ):
        self.inputs = inputs
        self.reader = reader
        self.store = store
        self.registry = registry
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def stage_selected_path(self, selected_path: str) -> LocalDocumentSelection:
        return self.inputs.stage_selected_path(selected_path)

    def clear(self, token: str | None = None) -> bool:
        return self.inputs.clear(token)

    def consume_for_turn(self, token: str) -> DocumentReadReceipt:
        self._verify_capability()
        document = self.inputs.consume(token)
        evidence = self.reader.read(document)
        return self.store.save(DocumentReadReceipt(
            receipt_id=f"doc_{uuid4()}",
            source_kind=DocumentReadSourceKind.LOCAL,
            source_reference=document.source_reference or f"local_input_{uuid4()}",
            source_domain=None,
            display_name=document.display_name,
            evidence=evidence,
            completed_at=self._clock(),
        ))

    def _verify_capability(self) -> None:
        if self.registry is None:
            return
        try:
            descriptor = self.registry.verify("local_document_read")
        except SkillRegistryError as error:
            raise LocalDocumentInputError("local_document_unavailable") from error
        manifest = descriptor.manifest
        if manifest is None or SkillCapability.LOCAL_READ not in manifest.capabilities:
            raise LocalDocumentInputError("local_document_unavailable")
