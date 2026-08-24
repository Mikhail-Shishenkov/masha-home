"""Bounded operational timing trace for reminder delivery, never user content."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class ReminderDeliveryTrace:
    """Append a small inspectable timeline without owning reminder lifecycle."""

    def __init__(self, path: Path, *, limit: int = 100):
        self.path = Path(path)
        self.limit = limit

    def record(self, stage: str, *, interaction_id: str | None = None, at: datetime | None = None) -> None:
        rows = self.list()
        rows.append({"stage": stage, "interaction_id": interaction_id,
                     "at": (at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(rows[-self.limit:], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)

    def list(self) -> list[dict[str, str | None]]:
        if not self.path.exists():
            return []
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return value if isinstance(value, list) else []
