"""Explicit, staged durable-state inventory for Whole-Home backup."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from backend.skills.models import SkillRegistryState
from backend.skills.registry import SkillRegistry, SkillRegistryError

from .errors import BackupError
from .models import BackupComponent


@dataclass(frozen=True)
class StagedComponent:
    manifest: BackupComponent
    staged_path: Path


@dataclass(frozen=True)
class StaticInventoryComponent:
    """One canonical v1 component mapping shared by writer and verifier."""

    component_id: str
    source_relative_path: str
    archive_path: str
    required: bool


V1_STATIC_INVENTORY = (
    StaticInventoryComponent("identity", "identity/masha.identity.json", "payload/identity/masha.identity.json", True),
    StaticInventoryComponent("memory_database", "local-data/memory/masha.sqlite3", "payload/memory/masha.sqlite3", True),
    StaticInventoryComponent("conversation_history", "local-data/conversations/history.json", "payload/conversations/history.json", True),
    StaticInventoryComponent("config_home_timezone", "local-data/config/home-timezone.json", "payload/config/home-timezone.json", False),
    StaticInventoryComponent("config_models", "local-data/config/models.json", "payload/config/models.json", False),
    StaticInventoryComponent("config_proactive_policy", "local-data/config/proactive-policy.json", "payload/config/proactive-policy.json", False),
    StaticInventoryComponent("config_autonomy_safety", "local-data/config/autonomy-safety.json", "payload/config/autonomy-safety.json", False),
    StaticInventoryComponent("config_internet_access", "local-data/config/internet-access.json", "payload/config/internet-access.json", False),
    StaticInventoryComponent("config_action_autonomy", "local-data/config/action-autonomy.json", "payload/config/action-autonomy.json", False),
    StaticInventoryComponent("config_skills", "local-data/config/skills.json", "payload/config/skills.json", False),
    StaticInventoryComponent("config_google_calendar", "local-data/config/google-calendar.json", "payload/config/google-calendar.json", False),
    StaticInventoryComponent("runtime_external_observations", "local-data/runtime/external-observations.json", "payload/runtime/external-observations.json", False),
    StaticInventoryComponent("runtime_document_receipts", "local-data/runtime/document-read-receipts.json", "payload/runtime/document-read-receipts.json", False),
    StaticInventoryComponent("runtime_daily_receipts", "local-data/runtime/daily-runtime-receipts.json", "payload/runtime/daily-runtime-receipts.json", False),
    StaticInventoryComponent("runtime_agent_runs", "local-data/runtime/agent-runs.json", "payload/runtime/agent-runs.json", False),
)
V1_STATIC_COMPONENTS_BY_ID = {item.component_id: item for item in V1_STATIC_INVENTORY}
V1_REQUIRED_COMPONENT_IDS = frozenset(item.component_id for item in V1_STATIC_INVENTORY if item.required)


def static_component_matches_v1(component: BackupComponent) -> bool:
    """Return true only for an exact component-id/path/required v1 binding."""
    expected = V1_STATIC_COMPONENTS_BY_ID.get(component.component_id)
    return bool(
        expected
        and component.archive_path == expected.archive_path
        and component.required is expected.required
    )


class BackupInventory:
    """Copies only allowlisted snapshot artifacts into a private temporary area."""

    def __init__(self, project_root: Path, staging_root: Path):
        self.root = Path(project_root)
        self.staging_root = Path(staging_root)

    def stage(self) -> tuple[StagedComponent, ...]:
        rows: list[StagedComponent] = []
        staged_skill_registry: StagedComponent | None = None
        for contract in V1_STATIC_INVENTORY:
            source = self.root / contract.source_relative_path
            if contract.component_id == "memory_database":
                rows.append(self._stage_sqlite(contract.component_id, source, contract.archive_path))
            elif contract.required:
                rows.append(self._stage_file(
                    contract.component_id, source, contract.archive_path, required=True,
                ))
            elif source.exists():
                staged = self._stage_file(
                    contract.component_id, source, contract.archive_path, required=False,
                )
                rows.append(staged)
                if contract.component_id == "config_skills":
                    staged_skill_registry = staged
        rows.extend(self._stage_installed_skills(staged_skill_registry))
        return tuple(rows)

    def _stage_file(self, component_id: str, source: Path, archive_path: str, *, required: bool) -> StagedComponent:
        if source.is_symlink():
            raise BackupError("backup_source_unsafe")
        if not source.exists():
            if required:
                raise BackupError("required_component_missing")
            raise BackupError("optional_component_disappeared")
        if not source.is_file():
            raise BackupError("backup_source_unsafe")
        target = self.staging_root / archive_path
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as incoming, target.open("xb") as outgoing:
            shutil.copyfileobj(incoming, outgoing, length=1024 * 1024)
        return StagedComponent(self._component(component_id, archive_path, target, required), target)

    def _stage_sqlite(self, component_id: str, source: Path, archive_path: str) -> StagedComponent:
        if source.is_symlink():
            raise BackupError("backup_source_unsafe")
        if not source.exists():
            raise BackupError("required_component_missing")
        if not source.is_file():
            raise BackupError("backup_source_unsafe")
        target = self.staging_root / archive_path
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            incoming = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
            outgoing = sqlite3.connect(target)
            try:
                incoming.backup(outgoing)
                check = outgoing.execute("PRAGMA quick_check").fetchone()
                if check != ("ok",):
                    raise BackupError("sqlite_snapshot_invalid")
            finally:
                outgoing.close()
                incoming.close()
        except BackupError:
            raise
        except sqlite3.Error as error:
            raise BackupError("sqlite_snapshot_failed") from error
        return StagedComponent(self._component(component_id, archive_path, target, True), target)

    def _stage_installed_skills(self, staged_registry: StagedComponent | None) -> tuple[StagedComponent, ...]:
        if staged_registry is None:
            return ()
        try:
            registered = SkillRegistryState.model_validate(
                json.loads(staged_registry.staged_path.read_text(encoding="utf-8"))
            ).skills
        except (OSError, ValueError, ValidationError) as error:
            raise BackupError("skill_registry_invalid") from error
        skill_root = self.root / "local-data/skills"
        if skill_root.is_symlink():
            raise BackupError("backup_source_unsafe")
        rows: list[StagedComponent] = []
        for entry in registered:
            skill_id = entry.skill_id
            expected = entry.package_sha256
            package = skill_root / skill_id
            if package.is_symlink() or not package.is_dir():
                raise BackupError("installed_skill_unavailable")
            for source in sorted(package.rglob("*")):
                if source.is_symlink():
                    raise BackupError("installed_skill_symlink_unsupported")
                if not source.is_file():
                    continue
                relative = source.relative_to(package).as_posix()
                archive_path = f"payload/skills/{skill_id}/{relative}"
                component_id = f"installed_skill:{skill_id}:{hashlib.sha256(relative.encode('utf-8')).hexdigest()}"
                rows.append(self._stage_file(
                    component_id, source, archive_path, required=False,
                ))
            staged_package = self.staging_root / "payload" / "skills" / skill_id
            try:
                _, digest = SkillRegistry.inspect_package_path(staged_package)
            except SkillRegistryError as error:
                raise BackupError("installed_skill_invalid") from error
            if digest != expected:
                raise BackupError("installed_skill_integrity_failed")
        return tuple(rows)

    @staticmethod
    def _component(component_id: str, archive_path: str, path: Path, required: bool) -> BackupComponent:
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                size += len(chunk)
                digest.update(chunk)
        return BackupComponent(
            component_id=component_id,
            archive_path=archive_path,
            required=required,
            byte_size=size,
            sha256=digest.hexdigest(),
            format_version=None,
        )
