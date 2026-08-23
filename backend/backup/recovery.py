"""Offline, journaled REPLACE/FRESH recovery for verified W5.1 bundles."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import shutil
import tempfile
from contextlib import contextmanager
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
from backend.runtime.runtime_lease import PidLease, RuntimeLease, RuntimeLeaseError
from backend.runtime.process_liveness import default_process_probe
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
    "local-data/runtime/proactive-daemon.stop",
)

_OWNED_TARGETS = (
    "identity",
    "local-data/memory",
    "local-data/conversations",
    "local-data/config",
    "local-data/runtime",
    "local-data/skills",
    "local-data/recovery",
)


class WholeHomeRecoveryService:
    """Runs only from a separate offline process; never from Conversation/UI."""

    def __init__(self, project_root: Path, *, home_lease: RuntimeLease | None = None, daemon: ProactiveDaemon | None = None):
        self.root = Path(project_root)
        self.journal = RecoveryJournal(self.root)
        self.home_lease = home_lease or RuntimeLease(self.root)
        self.daemon = daemon or ProactiveDaemon(self.root)
        self.daemon_lease = PidLease(
            self.daemon.lock_path,
            process_probe=getattr(self.daemon, "_process_probe", None) or default_process_probe,
        )

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
        self._assert_owned_paths_safe()
        with self._held_writer_guards():
            self.journal.assert_start_allowed()
            preview = self.preview_restore(backup_path, passphrase)
            if preview.backup_id != expected_backup_id:
                raise RecoveryError("restore_confirmation_stale")
            if restore_mode is RestoreMode.FRESH:
                self._assert_fresh_target()
            recovery_id = f"recovery-{uuid4()}"
            now = datetime.now(timezone.utc)
            state = RecoveryState(
                recovery_id=recovery_id, backup_id=preview.backup_id, restore_mode=restore_mode,
                phase=RecoveryPhase.PREVIEWED, created_at=now, updated_at=now,
            )
            transaction = self.root / "local-data" / "recovery" / recovery_id
            checkpoint: Path | None = None
            try:
                if restore_mode is RestoreMode.REPLACE:
                    checkpoint = self._create_checkpoint(recovery_id, passphrase)
                    state = self.journal.transition(state.model_copy(update={"checkpoint_filename": checkpoint.name}), RecoveryPhase.CHECKPOINTED)
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
                return RestoreResult(recovery_id=state.recovery_id, backup_id=state.backup_id, phase=state.phase, restore_mode=state.restore_mode)
            except RecoveryError:
                raise
            except BackupError as error:
                raise RecoveryError(error.code) from error

    def release_recovery_hold(self) -> RestoreResult:
        self._assert_owned_paths_safe()
        with self._held_writer_guards():
            state = self.journal.load()
            if state is None or state.phase is not RecoveryPhase.HOLD:
                raise RecoveryError("recovery_hold_not_active")
            self._validate_current_structure()
            released = self.journal.transition(state, RecoveryPhase.RELEASED)
            recovery_root = self.root / "local-data" / "recovery" / state.recovery_id
            checkpoints = self.root / "local-data" / "recovery" / "checkpoints"
            shutil.rmtree(recovery_root, ignore_errors=True)
            if state.checkpoint_filename is not None:
                (checkpoints / state.checkpoint_filename).unlink(missing_ok=True)
            return RestoreResult(recovery_id=released.recovery_id, backup_id=released.backup_id, phase=released.phase, restore_mode=released.restore_mode)

    def recover_interrupted(
        self,
        passphrase: str,
        *,
        backup_path: Path | None = None,
        expected_backup_id: str | None = None,
    ) -> RestoreResult:
        """Offline repair for a retained, incomplete transaction only."""
        self._assert_owned_paths_safe()
        with self._held_writer_guards():
            state = self.journal.load()
            if state is None or state.phase not in {
                RecoveryPhase.CHECKPOINTED, RecoveryPhase.APPLYING, RecoveryPhase.VERIFYING,
                RecoveryPhase.ROLLING_BACK, RecoveryPhase.BLOCKED,
            }:
                raise RecoveryError("recovery_not_interrupted")
            if state.restore_mode is RestoreMode.REPLACE:
                return self._recover_interrupted_replace(state, passphrase)
            if backup_path is None or expected_backup_id != state.backup_id:
                raise RecoveryError("restore_confirmation_stale")
            return self._recover_interrupted_fresh(state, backup_path, passphrase)

    def _recover_interrupted_replace(self, state: RecoveryState, passphrase: str) -> RestoreResult:
        expected_name = f"{state.recovery_id}.mashabackup"
        if state.checkpoint_filename != expected_name:
            raise RecoveryError("recovery_blocked")
        checkpoint = self.root / "local-data" / "recovery" / "checkpoints" / expected_name
        if not checkpoint.is_file() or checkpoint.is_symlink():
            raise RecoveryError("recovery_blocked")
        transaction = self.root / "local-data" / "recovery" / state.recovery_id
        try:
            rolling = self.journal.transition(state, RecoveryPhase.ROLLING_BACK, error_code="interrupted_recovery")
            with tempfile.TemporaryDirectory(prefix="masha-recovery-interrupted-") as temporary:
                previous = materialize_verified_backup(checkpoint, passphrase, Path(temporary))
                self._assert_supported(previous.manifest)
                self._apply_materialized(previous, transaction, label="interrupted-rollback", fault_injector=None)
                self._validate_applied(previous, passphrase, transaction)
            self._restore_transaction_quarantine(transaction)
            rolled = self.journal.transition(rolling, RecoveryPhase.ROLLED_BACK, error_code="interrupted_recovery")
            return RestoreResult(recovery_id=rolled.recovery_id, backup_id=rolled.backup_id, phase=rolled.phase, restore_mode=rolled.restore_mode)
        except Exception as error:
            self.journal.transition(state, RecoveryPhase.BLOCKED, error_code="interrupted_rollback_failed")
            if isinstance(error, RecoveryError):
                raise
            raise RecoveryError("recovery_blocked") from error

    def _recover_interrupted_fresh(self, state: RecoveryState, backup_path: Path, passphrase: str) -> RestoreResult:
        transaction = self.root / "local-data" / "recovery" / state.recovery_id
        try:
            self._reset_partial_fresh_targets()
            with tempfile.TemporaryDirectory(prefix="masha-recovery-fresh-retry-") as temporary:
                materialized = materialize_verified_backup(backup_path, passphrase, Path(temporary))
                self._assert_supported(materialized.manifest)
                if materialized.manifest.backup_id != state.backup_id:
                    raise RecoveryError("restore_confirmation_stale")
                quarantine = self._quarantine_actionable_state(transaction)
                self._apply_materialized(materialized, transaction, label="fresh-retry", fault_injector=None)
                verifying = self.journal.transition(state, RecoveryPhase.VERIFYING)
                self._validate_applied(materialized, passphrase, transaction)
            held = self.journal.transition(verifying, RecoveryPhase.HOLD)
            return RestoreResult(recovery_id=held.recovery_id, backup_id=held.backup_id, phase=held.phase, restore_mode=held.restore_mode)
        except Exception as error:
            self.journal.transition(state, RecoveryPhase.BLOCKED, error_code="fresh_retry_failed")
            if isinstance(error, RecoveryError):
                raise
            raise RecoveryError("recovery_blocked") from error

    def _assert_supported(self, manifest) -> None:
        if (
            manifest.backup_format_version != _SUPPORTED_BACKUP_FORMAT
            or manifest.application_data_version != _SUPPORTED_APPLICATION_DATA_VERSION
            or manifest.secrets_included is not False
        ):
            raise RecoveryError("backup_version_unsupported")

    @contextmanager
    def _held_writer_guards(self):
        """Own both writer leases from the preflight through terminal state."""
        if self.home_lease.liveness().state != "stopped" or self.daemon.liveness().state != "stopped":
            raise RecoveryError("home_not_quiescent")
        home_acquired = daemon_acquired = False
        try:
            try:
                self.home_lease.acquire()
                home_acquired = True
                self.daemon_lease.acquire()
                daemon_acquired = True
            except (FileExistsError, RuntimeLeaseError, OSError) as error:
                raise RecoveryError("home_not_quiescent") from error
            # Successful O_EXCL ownership is the second, race-free quiescence
            # check.  Keep both until journal/error handling is complete.
            yield
        finally:
            if daemon_acquired:
                self.daemon_lease.release()
            if home_acquired:
                self.home_lease.release()

    def _assert_owned_paths_safe(self) -> None:
        root = self.root.resolve()
        if self.root.is_symlink():
            raise RecoveryError("recovery_target_unsafe")
        for relative in _OWNED_TARGETS:
            candidate = self.root / relative
            current = self.root
            for part in Path(relative).parts:
                current = current / part
                if current.exists() and current.is_symlink():
                    raise RecoveryError("recovery_target_unsafe")
                if current.exists():
                    try:
                        current.resolve().relative_to(root)
                    except ValueError as error:
                        raise RecoveryError("recovery_target_unsafe") from error

    def _assert_fresh_target(self) -> None:
        for item in V1_STATIC_INVENTORY:
            if item.component_id != "identity" and (self.root / item.source_relative_path).exists():
                raise RecoveryError("fresh_target_not_empty")
        skills = self.root / "local-data" / "skills"
        if skills.exists() and any(skills.iterdir()):
            raise RecoveryError("fresh_target_not_empty")

    def _reset_partial_fresh_targets(self) -> None:
        # FRESH preflight proved these owned files/skills absent before its
        # first mutation.  Removing precisely this allowlist is therefore a
        # safe retry reset, without recursively touching unknown local data.
        for item in V1_STATIC_INVENTORY:
            if item.component_id != "identity":
                self._remove_owned_file(self.root / item.source_relative_path)
        skills = self.root / "local-data" / "skills"
        if skills.exists():
            if skills.is_symlink() or not skills.is_dir():
                raise RecoveryError("recovery_target_unsafe")
            shutil.rmtree(skills)

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
            target = transaction / "quarantine" / relative
            if target.exists():
                if source.exists():
                    raise RecoveryError("recovery_blocked")
                rows.append((source, target))
                continue
            if not source.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, target)
            rows.append((source, target))
        return rows

    def _restore_transaction_quarantine(self, transaction: Path) -> None:
        rows = [
            (self.root / relative, transaction / "quarantine" / relative)
            for relative in _QUARANTINED_PATHS
        ]
        self._restore_quarantine(rows)

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
