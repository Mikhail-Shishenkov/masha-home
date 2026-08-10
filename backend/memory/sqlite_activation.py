"""Safe one-way activation of the existing SQLite memory repository."""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .memory_models import MemoryDocument
from .sqlite_repository import MemorySqliteRepository


@dataclass(frozen=True)
class ActivationResult:
    database_path: Path
    backup_path: Path | None
    migrated: bool


def activate_sqlite_memory(
    *,
    json_source: str | Path,
    database_path: str | Path,
    backup_directory: str | Path,
) -> ActivationResult:
    """Import JSON once; refuse to overwrite a populated divergent database."""
    source = Path(json_source)
    raw = json.loads(source.read_text(encoding="utf-8"))
    document = MemoryDocument.model_validate(raw)
    repository = MemorySqliteRepository(database_path)
    existing = repository.read_document()
    if existing is not None:
        if existing.model_dump(mode="json") != document.model_dump(mode="json"):
            raise ValueError("SQLite memory differs from the JSON source; refusing to overwrite it")
        return ActivationResult(Path(database_path), None, migrated=False)

    backup_dir = Path(backup_directory)
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = backup_dir / f"memory-before-sqlite-{timestamp}.json"
    shutil.copy2(source, backup_path)
    repository.replace_document(document, action="import_json")
    migrated = repository.read_document()
    if migrated is None or migrated.model_dump(mode="json") != document.model_dump(mode="json"):
        raise RuntimeError("SQLite migration verification failed")
    return ActivationResult(Path(database_path), backup_path, migrated=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Activate local SQLite memory from a validated JSON export.")
    parser.add_argument("--source", default="memory/test_memory.json")
    parser.add_argument("--database", default="local-data/memory/masha.sqlite3")
    parser.add_argument("--backup-directory", default="local-data/memory-backups")
    arguments = parser.parse_args()
    result = activate_sqlite_memory(
        json_source=arguments.source,
        database_path=arguments.database,
        backup_directory=arguments.backup_directory,
    )
    if result.migrated:
        print(f"SQLite memory activated: {result.database_path}")
        print(f"JSON backup: {result.backup_path}")
    else:
        print(f"SQLite memory already matches source: {result.database_path}")


if __name__ == "__main__":
    main()
