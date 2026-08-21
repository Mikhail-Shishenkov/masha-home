"""Persistence for bounded document receipts only; raw bytes never reach disk."""

from __future__ import annotations

import json
from pathlib import Path

from .models import DocumentReadReceipt, DocumentReadState


class DocumentReadStore:
    def __init__(self, path: Path, *, limit: int = 200):
        self.path = Path(path)
        self.limit = limit

    def save(self, receipt: DocumentReadReceipt) -> DocumentReadReceipt:
        state = self._load()
        rows = [item for item in state.receipts if item.receipt_id != receipt.receipt_id]
        rows.append(receipt)
        self._write(DocumentReadState(receipts=tuple(rows[-self.limit:])))
        return receipt

    def get(self, receipt_id: str) -> DocumentReadReceipt | None:
        return next((item for item in self._load().receipts if item.receipt_id == receipt_id), None)

    def attach_assistant_message(self, receipt_id: str, message_id: str) -> DocumentReadReceipt:
        receipt = self.get(receipt_id)
        if receipt is None:
            raise KeyError(receipt_id)
        return self.save(receipt.model_copy(update={"assistant_message_id": message_id}))

    def for_assistant_message(self, message_id: str) -> tuple[DocumentReadReceipt, ...]:
        return tuple(
            item for item in self._load().receipts if item.assistant_message_id == message_id
        )

    def _load(self) -> DocumentReadState:
        if not self.path.exists():
            return DocumentReadState()
        return DocumentReadState.model_validate(json.loads(self.path.read_text(encoding="utf-8")))

    def _write(self, state: DocumentReadState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(state.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)
