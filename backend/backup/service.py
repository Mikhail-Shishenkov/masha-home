"""Create and verify encrypted, portable Whole-Home backups.  No restore lives here."""

from __future__ import annotations

import hashlib
import io
import json
import os
import sqlite3
import tarfile
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from pydantic import ValidationError

from backend.conversation.conversation_models import Conversation, ConversationMessage
from backend.identity.identity_models import IdentityManifest
from backend.memory.memory_models import MemoryDocument
from backend.memory.sqlite_repository import MemorySqliteRepository, RECORD_COLLECTIONS
from backend.skills.models import SkillRegistryState
from backend.skills.registry import SkillRegistry, SkillRegistryError

from .crypto import decrypt_file, encrypt_file, ensure_bundle_size
from .errors import BackupError
from .inventory import (
    BackupInventory,
    StagedComponent,
    V1_REQUIRED_COMPONENT_IDS,
    V1_STATIC_COMPONENTS_BY_ID,
    static_component_matches_v1,
)
from .models import BackupManifest, BackupVerification


_MAX_COMPONENT_BYTES = 512 * 1024 * 1024
_MAX_ARCHIVE_MEMBERS = 513
_CHUNK_BYTES = 1024 * 1024
_MAX_IDENTITY_BYTES = 512 * 1024
_MAX_SKILL_REGISTRY_BYTES = 512 * 1024
_MAX_CONVERSATION_HISTORY_BYTES = 32 * 1024 * 1024


class WholeHomeBackupService:
    """Bounded backup writer and read-only verifier for a single Home root."""

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)

    def create_backup(self, destination_path: Path, passphrase: str) -> BackupVerification:
        destination = _validate_destination(destination_path)
        partial = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.partial")
        try:
            with tempfile.TemporaryDirectory(prefix="masha-backup-") as temporary:
                temporary_root = Path(temporary)
                staged = BackupInventory(self.project_root, temporary_root / "staged").stage()
                manifest = BackupManifest(
                    backup_id=f"backup-{uuid.uuid4()}",
                    created_at=datetime.now(timezone.utc),
                    components=tuple(item.manifest for item in staged),
                )
                archive_path = temporary_root / "payload.tar"
                _write_tar(archive_path, manifest, staged)
                encrypt_file(archive_path, partial, passphrase)
                verification = verify_backup(partial, passphrase)
                os.replace(partial, destination)
                return verification
        except BackupError:
            _remove_partial(partial)
            raise
        except (OSError, tarfile.TarError, ValueError) as error:
            _remove_partial(partial)
            raise BackupError("backup_creation_failed") from error


def create_backup(project_root: Path, destination_path: Path, passphrase: str) -> BackupVerification:
    """Convenience core API; destination is always explicit and caller-owned."""
    return WholeHomeBackupService(project_root).create_backup(destination_path, passphrase)


def verify_backup(path: Path, passphrase: str) -> BackupVerification:
    """Verify untrusted encrypted input without extracting or mutating a Home."""
    bundle = Path(path)
    if not bundle.is_file() or bundle.is_symlink():
        raise BackupError("invalid_backup")
    try:
        ensure_bundle_size(bundle)
        with tempfile.TemporaryDirectory(prefix="masha-backup-verify-") as temporary:
            archive_path = Path(temporary) / "payload.tar"
            decrypt_file(bundle, archive_path, passphrase)
            return _verify_tar(archive_path, Path(temporary))
    except BackupError:
        raise
    except (OSError, tarfile.TarError, sqlite3.Error, ValidationError, ValueError) as error:
        raise BackupError("invalid_backup") from error


def _validate_destination(value: Path) -> Path:
    destination = Path(value)
    if destination.suffix != ".mashabackup" or destination.name == ".mashabackup":
        raise BackupError("backup_destination_invalid")
    if destination.exists() or destination.is_symlink():
        raise BackupError("backup_destination_exists")
    if not destination.parent.is_dir() or destination.parent.is_symlink():
        raise BackupError("backup_destination_unavailable")
    return destination


def _write_tar(path: Path, manifest: BackupManifest, components: tuple[StagedComponent, ...]) -> None:
    with tarfile.open(path, mode="w") as archive:
        _add_bytes(archive, "manifest.json", manifest.model_dump_json(indent=None).encode("utf-8"))
        for component in components:
            _add_file(archive, component.manifest.archive_path, component.staged_path)


def _add_bytes(archive: tarfile.TarFile, name: str, content: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(content)
    info.mode = 0o600
    info.mtime = 0
    archive.addfile(info, io.BytesIO(content))


def _add_file(archive: tarfile.TarFile, name: str, source: Path) -> None:
    info = tarfile.TarInfo(name)
    info.size = source.stat().st_size
    info.mode = 0o600
    info.mtime = 0
    with source.open("rb") as incoming:
        archive.addfile(info, incoming)


def _verify_tar(path: Path, temporary_root: Path) -> BackupVerification:
    with tarfile.open(path, mode="r:") as archive:
        members = _read_members_bounded(archive)
        seen: set[str] = set()
        for member in members:
            _validate_member(member, seen)
        by_name = {member.name: member for member in members}
        manifest_member = by_name.get("manifest.json")
        if manifest_member is None:
            raise BackupError("invalid_backup")
        manifest = _read_manifest(archive, manifest_member)
        _validate_manifest_inventory(manifest)
        expected = {"manifest.json"} | {component.archive_path for component in manifest.components}
        if set(by_name) != expected:
            raise BackupError("invalid_backup")
        if len(expected) != len(members):
            raise BackupError("invalid_backup")
        for component in manifest.components:
            member = by_name[component.archive_path]
            _verify_component(archive, member, component.byte_size, component.sha256)
        identity = _verify_identity(archive, by_name["payload/identity/masha.identity.json"])
        memory = _verify_memory_snapshot(archive, by_name["payload/memory/masha.sqlite3"], temporary_root)
        if memory.identity_version != identity.identity_version:
            raise BackupError("invalid_backup")
        _verify_conversation_history(archive, by_name["payload/conversations/history.json"])
        _verify_archived_skills(archive, by_name, manifest, temporary_root)
        return BackupVerification(
            backup_id=manifest.backup_id,
            created_at=manifest.created_at,
            components_verified=len(manifest.components),
        )


def _validate_manifest_inventory(manifest: BackupManifest) -> None:
    """Manifest declarations never extend the v1 durable-state allowlist."""
    component_ids = {component.component_id for component in manifest.components}
    archive_paths = {component.archive_path for component in manifest.components}
    if (
        len(component_ids) != len(manifest.components)
        or len(archive_paths) != len(manifest.components)
        or not V1_REQUIRED_COMPONENT_IDS.issubset(component_ids)
    ):
        raise BackupError("invalid_backup")
    for component in manifest.components:
        if component.component_id in V1_STATIC_COMPONENTS_BY_ID:
            if not static_component_matches_v1(component):
                raise BackupError("invalid_backup")
            continue
        if not component.component_id.startswith("installed_skill:"):
            raise BackupError("invalid_backup")
        if component.required or not component.archive_path.startswith("payload/skills/"):
            raise BackupError("invalid_backup")


def _read_members_bounded(archive: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members: list[tarfile.TarInfo] = []
    seen: set[str] = set()
    while (member := archive.next()) is not None:
        if len(members) >= _MAX_ARCHIVE_MEMBERS:
            raise BackupError("invalid_backup")
        _validate_member(member, seen)
        members.append(member)
    if not members:
        raise BackupError("invalid_backup")
    return members


def _validate_member(member: tarfile.TarInfo, seen: set[str]) -> None:
    name = member.name
    posix = PurePosixPath(name)
    if (
        not member.isfile()
        or name in seen
        or not name
        or posix.is_absolute()
        or name != posix.as_posix()
        or ".." in posix.parts
        or "\\" in name
        or len(name) > 512
        or member.size < 0
        or member.size > _MAX_COMPONENT_BYTES
    ):
        raise BackupError("invalid_backup")
    seen.add(name)


def _read_manifest(archive: tarfile.TarFile, member: tarfile.TarInfo) -> BackupManifest:
    if member.size > 512 * 1024:
        raise BackupError("invalid_backup")
    incoming = archive.extractfile(member)
    if incoming is None:
        raise BackupError("invalid_backup")
    with incoming:
        payload = incoming.read(member.size + 1)
    if len(payload) != member.size:
        raise BackupError("invalid_backup")
    try:
        return BackupManifest.model_validate_json(payload)
    except ValidationError as error:
        raise BackupError("invalid_backup") from error


def _verify_component(archive: tarfile.TarFile, member: tarfile.TarInfo, expected_size: int, expected_sha256: str) -> None:
    if member.size != expected_size:
        raise BackupError("invalid_backup")
    incoming = archive.extractfile(member)
    if incoming is None:
        raise BackupError("invalid_backup")
    digest = hashlib.sha256()
    count = 0
    with incoming:
        for chunk in iter(lambda: incoming.read(_CHUNK_BYTES), b""):
            count += len(chunk)
            if count > _MAX_COMPONENT_BYTES:
                raise BackupError("invalid_backup")
            digest.update(chunk)
    if count != expected_size or digest.hexdigest() != expected_sha256:
        raise BackupError("invalid_backup")


def _verify_identity(archive: tarfile.TarFile, member: tarfile.TarInfo) -> IdentityManifest:
    payload = _read_member_bytes(archive, member, maximum=_MAX_IDENTITY_BYTES)
    try:
        return IdentityManifest.model_validate_json(payload)
    except ValidationError as error:
        raise BackupError("invalid_backup") from error


def _verify_memory_snapshot(archive: tarfile.TarFile, member: tarfile.TarInfo, temporary_root: Path) -> MemoryDocument:
    snapshot = temporary_root / "memory.sqlite3"
    incoming = archive.extractfile(member)
    if incoming is None:
        raise BackupError("invalid_backup")
    with incoming, snapshot.open("xb") as outgoing:
        for chunk in iter(lambda: incoming.read(_CHUNK_BYTES), b""):
            outgoing.write(chunk)
    connection = sqlite3.connect(f"file:{snapshot.as_posix()}?mode=ro", uri=True)
    try:
        if connection.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise BackupError("invalid_backup")
    finally:
        connection.close()
    try:
        return _read_memory_document_read_only(snapshot)
    except (KeyError, sqlite3.Error, ValidationError, ValueError) as error:
        raise BackupError("invalid_backup") from error


def _read_memory_document_read_only(snapshot: Path) -> MemoryDocument:
    connection = sqlite3.connect(f"file:{snapshot.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        metadata = dict(connection.execute("SELECT key, value FROM memory_metadata"))
        document: dict[str, object] = {
            "schema_version": metadata["schema_version"],
            "identity_version": metadata["identity_version"],
            "projects": MemorySqliteRepository._read_payloads(connection, "projects"),
        }
        for record_type, collection_name in RECORD_COLLECTIONS.items():
            document[collection_name] = MemorySqliteRepository._read_payloads(
                connection, "memory_records", "record_type = ?", (record_type,),
            )
        return MemoryDocument.model_validate(document)
    finally:
        connection.close()


def _verify_conversation_history(archive: tarfile.TarFile, member: tarfile.TarInfo) -> None:
    payload = _read_member_bytes(archive, member, maximum=_MAX_CONVERSATION_HISTORY_BYTES)
    try:
        raw = json.loads(payload)
        if not isinstance(raw, dict) or set(raw) != {"conversations", "messages"}:
            raise BackupError("invalid_backup")
        conversations_raw = raw["conversations"]
        messages_raw = raw["messages"]
        if not isinstance(conversations_raw, list) or not isinstance(messages_raw, list):
            raise BackupError("invalid_backup")
        conversation_ids = {Conversation.model_validate(item).id for item in conversations_raw}
        for item in messages_raw:
            if ConversationMessage.model_validate(item).conversation_id not in conversation_ids:
                raise BackupError("invalid_backup")
    except BackupError:
        raise
    except (UnicodeDecodeError, ValueError, ValidationError) as error:
        raise BackupError("invalid_backup") from error


def _verify_archived_skills(
    archive: tarfile.TarFile,
    by_name: dict[str, tarfile.TarInfo],
    manifest: BackupManifest,
    temporary_root: Path,
) -> None:
    registry_component = next((item for item in manifest.components if item.component_id == "config_skills"), None)
    skill_components = [item for item in manifest.components if item.archive_path.startswith("payload/skills/")]
    if registry_component is None:
        if skill_components:
            raise BackupError("invalid_backup")
        return
    try:
        registry = SkillRegistryState.model_validate_json(
            _read_member_bytes(
                archive, by_name[registry_component.archive_path], maximum=_MAX_SKILL_REGISTRY_BYTES,
            )
        )
    except (ValidationError, UnicodeDecodeError, ValueError) as error:
        raise BackupError("invalid_backup") from error
    expected_ids = {item.skill_id for item in registry.skills}
    staged_root = temporary_root / "verified-skills"
    observed_ids: set[str] = set()
    for component in skill_components:
        parts = PurePosixPath(component.archive_path).parts
        if len(parts) < 4:
            raise BackupError("invalid_backup")
        skill_id = parts[2]
        if skill_id not in expected_ids:
            raise BackupError("invalid_backup")
        relative_path = "/".join(parts[3:])
        expected_component_id = f"installed_skill:{skill_id}:{hashlib.sha256(relative_path.encode('utf-8')).hexdigest()}"
        if component.component_id != expected_component_id:
            raise BackupError("invalid_backup")
        observed_ids.add(skill_id)
        destination = staged_root.joinpath(*parts[2:])
        destination.parent.mkdir(parents=True, exist_ok=True)
        _copy_member_to_file(archive, by_name[component.archive_path], destination)
    if observed_ids != expected_ids:
        raise BackupError("invalid_backup")
    for registered in registry.skills:
        try:
            _, digest = SkillRegistry.inspect_package_path(staged_root / registered.skill_id)
        except SkillRegistryError as error:
            raise BackupError("invalid_backup") from error
        if digest != registered.package_sha256:
            raise BackupError("invalid_backup")


def _read_member_bytes(archive: tarfile.TarFile, member: tarfile.TarInfo, *, maximum: int) -> bytes:
    if member.size > maximum:
        raise BackupError("invalid_backup")
    incoming = archive.extractfile(member)
    if incoming is None:
        raise BackupError("invalid_backup")
    with incoming:
        payload = incoming.read(member.size + 1)
    if len(payload) != member.size:
        raise BackupError("invalid_backup")
    return payload


def _copy_member_to_file(archive: tarfile.TarFile, member: tarfile.TarInfo, destination: Path) -> None:
    incoming = archive.extractfile(member)
    if incoming is None:
        raise BackupError("invalid_backup")
    count = 0
    with incoming, destination.open("xb") as outgoing:
        for chunk in iter(lambda: incoming.read(_CHUNK_BYTES), b""):
            count += len(chunk)
            if count > member.size:
                raise BackupError("invalid_backup")
            outgoing.write(chunk)
    if count != member.size:
        raise BackupError("invalid_backup")


def _remove_partial(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
