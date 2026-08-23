"""Offline, journaled REPLACE/FRESH recovery for verified W5.1 bundles."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .errors import BackupError
from .inventory import V1_STATIC_INVENTORY
from .recovery_journal import RecoveryError, RecoveryJournal
from .recovery_models import RecoveryPhase, RecoveryState, RestoreMode, RestorePreview, RestoreResult
from .service import (
    VerifiedBackupMaterialization,
    WholeHomeBackupService,
    inspect_verified_backup,
    materialize_verified_backup,
    _read_memory_document_read_only,
)
from backend.conversation.conversation_models import Conversation, ConversationMessage
from backend.identity.identity_models import IdentityManifest
from backend.runtime.runtime_lease import RuntimeLease
from backend.skills.models import SkillRegistryState
from backend.skills.registry import SkillRegistry, SkillRegistryError
from backend.temporal.proactive_daemon import ProactiveDaemon


_SUPPORTED_BACKUP_FORMAT = "1.0"
_SUPPORTED_APPLICATION_DATA_VERSION = "0.1"
_QUARANTINED_PATHS = (
    "local-data/memory-proposals.json",
    "local-data/config/skill-installs.json",
    "local-data/runtime/skill-installs",
    "local-data/runtime/local-document-inputs.json",
    "local-data/runtime/proactive-daemon.lock",
    "local-data/runtime/proactive-daemon.stop",
    "local-data/runtime/home-runtime.lock",
)


class WholeHomeRecoveryService:
    """Runs only from a separate offline process; never from Conversation/UI."""

    def __init__(self, project_root: Path, *, home_lease: RuntimeLease | None = None, daemon: ProactiveDaemon | None = None):
        self.root = Path(project_root)
        self.journal = RecoveryJournal(self.root)
        self.home_lease = home_lease or RuntimeLease(self.root)
        self.daemon = daemon or ProactiveDaemon(self.root)

    def preview_restore(self, backup_path: Path, passphrase: str) -> RestorePreview:
        _, manifest = inspect_verified_backup(backup_path, passphrase)
        self._assert_supported(manifest)
        return RestorePreview(
            backup_id=manifest.backup_id,
            created_at=manifest.created_at,
            application_data_version=manifest.application_data_version,
            component_count=len(manifest.components),
            recovery_hold_required=manifest.recovery_hold_required,
            secrets_included=manifest.secrets_included,
        )

    def restore(
        self,
        backup_path: Path,
        passphrase: str,
        *,
        expected_backup_id: str,
        restore_mode: RestoreMode,
        fault_injector=None,
    ) -> RestoreResult:
        self._assert_quiescent()
        self.journal.assert_start_allowed()
        preview = self.preview_restore(backup_path, passphrase)
        if preview.backup_id != expected_backup_id:
            raise RecoveryError("restore_confirmation_stale")
        if restore_mode is RestoreMode.FRESH:
            self._assert_fresh_target()
        recovery_id = f"recovery-{uuid4()}"
        now = datetime.now(timezone.utc)
        state = RecoveryState(
            recovery_id=recovery_id,
            backup_id=preview.backup_id,
            restore_mode=restore_mode,
            phase=RecoveryPhase.PREVIEWED,
            created_at=now,
            updated_at=now,
        )
        transaction = self.root / "local-data" / "recovery" / recovery_id
        checkpoint: Path | None = None
        try:
            if restore_mode is RestoreMode.REPLACE:
                checkpoint = self._create_checkpoint(recovery_id, passphrase)
                state = self.journal.transition(
                    state.model_copy(update={"checkpoint_filename": checkpoint.name}), RecoveryPhase.CHECKPOINTED,
                )
            with tempfile.TemporaryDirectory(prefix="masha-recovery-stage-") as temporary:
                materialized = materialize_verified_backup(backup_path, passphrase, Path(temporary))
                self._assert_supported(materialized.manifest)
                if materialized.manifest.backup_id != expected_backup_id:
                    raise RecoveryError("restore_confirmation_stale")
                state = self.journal.transition(state, RecoveryPhase.APPLYING)
                quarantine = self._quarantine_actionable_state(transaction)
                try:
                    self._apply_materialized(materialized, transaction, label="apply", fault_injector=fault_injector)
                    state = self.journal.transition(state, RecoveryPhase.VERIFYING)
                    self._validate_applied(materialized, passphrase, transaction)
                except Exception as error:
                    if restore_mode is RestoreMode.FRESH or checkpoint is None:
                        self.journal.transition(state, RecoveryPhase.BLOCKED, error_code="restore_failed")
                        raise RecoveryError("recovery_blocked") from error
                    self._rollback(state, checkpoint, passphrase, transaction, quarantine)
                    raise RecoveryError("restore_failed") from error
            state = self.journal.transition(state, RecoveryPhase.HOLD)
            return RestoreResult(
                recovery_id=state.recovery_id,
                backup_id=state.backup_id,
                phase=state.phase,
                restore_mode=state.restore_mode,
            )
        except RecoveryError:
            raise
        except BackupError as error:
            raise RecoveryError(error.code) from error

    def release_recovery_hold(self) -> RestoreResult:
        state = self.journal.load()
        if state is None or state.phase is not RecoveryPhase.HOLD:
            raise RecoveryError("recovery_hold_not_active")
        self._assert_quiescent()
        self._validate_current_structure()
        released = self.journal.transition(state, RecoveryPhase.RELEASED)
        recovery_root = self.root / "local-data" / "recovery" / state.recovery_id
        checkpoints = self.root / "local-data" / "recovery" / "checkpoints"
        shutil.rmtree(recovery_root, ignore_errors=True)
        if state.checkpoint_filename is not None:
            (checkpoints / state.checkpoint_filename).unlink(missing_ok=True)
        return RestoreResult(
            recovery_id=released.recovery_id,
            backup_id=released.backup_id,
            phase=released.phase,
            restore_mode=released.restore_mode,
        )

    def _assert_supported(self, manifest) -> None:
        if (
            manifest.backup_format_version != _SUPPORTED_BACKUP_FORMAT
            or manifest.application_data_version != _SUPPORTED_APPLICATION_DATA_VERSION
            or manifest.secrets_included is not False
        ):
            raise RecoveryError("backup_version_unsupported")

    def _assert_quiescent(self) -> None:
        if self.home_lease.liveness().state != "stopped" or self.daemon.liveness().state != "stopped":
            raise RecoveryError("home_not_quiescent")

    def _assert_fresh_target(self) -> None:
        for item in V1_STATIC_INVENTORY:
            if item.component_id != "identity" and (self.root / item.source_relative_path).exists():
                raise RecoveryError("fresh_target_not_empty")
        skills = self.root / "local-data" / "skills"
        if skills.exists() and any(skills.iterdir()):
            raise RecoveryError("fresh_target_not_empty")

    def _create_checkpoint(self, recovery_id: str, passphrase: str) -> Path:
        directory = self.root / "local-data" / "recovery" / "checkpoints"
        directory.mkdir(parents=True, exist_ok=True)
        checkpoint = directory / f"{recovery_id}.mashabackup"
        try:
            verification = WholeHomeBackupService(self.root).create_backup(checkpoint, passphrase)
        except BackupError as error:
            raise RecoveryError("current_home_incomplete") from error
        if verification.verified is not True or not checkpoint.is_file():
            raise RecoveryError("current_home_incomplete")
        return checkpoint

    def _apply_materialized(self, materialized: VerifiedBackupMaterialization, transaction: Path, *, label: str, fault_injector) -> None:
        components = {item.component_id: item for item in materialized.manifest.components}
        for item in V1_STATIC_INVENTORY:
            target = self.root / item.source_relative_path
            component = components.get(item.component_id)
            if component is None:
                if not item.required:
                    self._remove_owned_file(target)
                continue
            source = materialized.payload_root / Path(*Path(component.archive_path).parts[1:])
            self._atomic_replace_file(source, target)
            if fault_injector is not None:
                fault_injector(item.component_id)
        self._replace_skills(materialized, transaction, label)
        if fault_injector is not None:
            fault_injector("skills")

    def _replace_skills(self, materialized: VerifiedBackupMaterialization, transaction: Path, label: str) -> None:
        target = self.root / "local-data" / "skills"
        source = materialized.payload_root / "skills"
        previous = transaction / f"skills-before-{label}"
        previous.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            os.replace(target, previous)
        if source.exists():
            os.replace(source, target)
        else:
            target.mkdir(parents=True, exist_ok=True)

    def _validate_applied(self, materialized: VerifiedBackupMaterialization, passphrase: str, transaction: Path) -> None:
        components = {item.component_id: item for item in materialized.manifest.components}
        for item in V1_STATIC_INVENTORY:
            target = self.root / item.source_relative_path
            component = components.get(item.component_id)
            if component is None:
                if target.exists():
                    raise RecoveryError("restore_validation_failed")
            elif not target.is_file() or _sha256(target) != component.sha256:
                raise RecoveryError("restore_validation_failed")
        self._validate_current_structure()
        probe = transaction / "post-apply-validation.mashabackup"
        WholeHomeBackupService(self.root).create_backup(probe, passphrase)
        probe.unlink(missing_ok=True)

    def _validate_current_structure(self) -> None:
        for item in V1_STATIC_INVENTORY:
            if item.required and not (self.root / item.source_relative_path).is_file():
                raise RecoveryError("restore_validation_failed")
        try:
            identity = IdentityManifest.model_validate_json(
                (self.root / "identity/masha.identity.json").read_bytes()
            )
            database = self.root / "local-data/memory/masha.sqlite3"
            connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
            try:
                if connection.execute("PRAGMA quick_check").fetchone() != ("ok",):
                    raise RecoveryError("restore_validation_failed")
            finally:
                connection.close()
            if _read_memory_document_read_only(database).identity_version != identity.identity_version:
                raise RecoveryError("restore_validation_failed")
            history = json.loads((self.root / "local-data/conversations/history.json").read_bytes())
            if not isinstance(history, dict) or set(history) != {"conversations", "messages"}:
                raise RecoveryError("restore_validation_failed")
            conversation_ids = {Conversation.model_validate(item).id for item in history["conversations"]}
            for item in history["messages"]:
                if ConversationMessage.model_validate(item).conversation_id not in conversation_ids:
                    raise RecoveryError("restore_validation_failed")
        except RecoveryError:
            raise
        except Exception as error:
            raise RecoveryError("restore_validation_failed") from error
        registry_file = self.root / "local-data" / "config" / "skills.json"
        if registry_file.exists():
            try:
                registry = SkillRegistryState.model_validate_json(registry_file.read_bytes())
            except Exception as error:
                raise RecoveryError("restore_validation_failed") from error
            for entry in registry.skills:
                try:
                    _, digest = SkillRegistry.inspect_package_path(self.root / "local-data" / "skills" / entry.skill_id)
                except SkillRegistryError as error:
                    raise RecoveryError("restore_validation_failed") from error
                if digest != entry.package_sha256:
                    raise RecoveryError("restore_validation_failed")

    def _rollback(self, state: RecoveryState, checkpoint: Path, passphrase: str, transaction: Path, quarantine: list[tuple[Path, Path]]) -> None:
        try:
            rolling = self.journal.transition(state, RecoveryPhase.ROLLING_BACK, error_code="restore_failed")
            with tempfile.TemporaryDirectory(prefix="masha-recovery-rollback-") as temporary:
                previous = materialize_verified_backup(checkpoint, passphrase, Path(temporary))
                self._apply_materialized(previous, transaction, label="rollback", fault_injector=None)
                self._validate_applied(previous, passphrase, transaction)
            self._restore_quarantine(quarantine)
            self.journal.transition(rolling, RecoveryPhase.ROLLED_BACK, error_code="restore_failed")
        except Exception as error:
            self.journal.transition(state, RecoveryPhase.BLOCKED, error_code="rollback_failed")
            raise RecoveryError("recovery_blocked") from error

    def _quarantine_actionable_state(self, transaction: Path) -> list[tuple[Path, Path]]:
        rows: list[tuple[Path, Path]] = []
        for relative in _QUARANTINED_PATHS:
            source = self.root / relative
            if not source.exists():
                continue
            target = transaction / "quarantine" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, target)
            rows.append((source, target))
        return rows

    @staticmethod
    def _restore_quarantine(rows: list[tuple[Path, Path]]) -> None:
        for destination, quarantined in reversed(rows):
            if quarantined.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(quarantined, destination)

    @staticmethod
    def _atomic_replace_file(source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.restore")
        with source.open("rb") as incoming, temporary.open("xb") as outgoing:
            shutil.copyfileobj(incoming, outgoing, length=1024 * 1024)
            outgoing.flush()
            os.fsync(outgoing.fileno())
        os.replace(temporary, target)

    @staticmethod
    def _remove_owned_file(path: Path) -> None:
        if path.exists():
            if path.is_symlink() or not path.is_file():
                raise RecoveryError("restore_validation_failed")
            path.unlink()


def preview_restore(project_root: Path, backup_path: Path, passphrase: str) -> RestorePreview:
    return WholeHomeRecoveryService(project_root).preview_restore(backup_path, passphrase)


def restore_backup(project_root: Path, backup_path: Path, passphrase: str, *, expected_backup_id: str, restore_mode: RestoreMode) -> RestoreResult:
    return WholeHomeRecoveryService(project_root).restore(
        backup_path, passphrase, expected_backup_id=expected_backup_id, restore_mode=restore_mode,
    )


def release_recovery_hold(project_root: Path) -> RestoreResult:
    return WholeHomeRecoveryService(project_root).release_recovery_hold()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as incoming:
        for chunk in iter(lambda: incoming.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
