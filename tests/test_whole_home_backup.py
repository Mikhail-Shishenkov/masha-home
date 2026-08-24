import hashlib
import io
import json
import shutil
import sqlite3
import tarfile
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.backup import BackupError, WholeHomeBackupService, verify_backup
from backend.backup.crypto import MAX_ENCRYPTED_BUNDLE_BYTES, decrypt_file, encrypt_file, read_public_header
from backend.backup.inventory import BackupInventory
from backend.backup.service import _MAX_ARCHIVE_MEMBERS
from backend.memory.memory_models import MemoryDocument
from backend.memory.sqlite_repository import MemorySqliteRepository
from backend.skills.registry import SkillRegistry
from backend.secrets import InMemorySecretStore, SecretRef


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PASSPHRASE = "backup recovery phrase"


def _home(root: Path) -> Path:
    shutil.copytree(PROJECT_ROOT / "identity", root / "identity")
    (root / "local-data/conversations").mkdir(parents=True)
    (root / "local-data/conversations/history.json").write_text(
        json.dumps({
            "conversations": [{"id": "conversation-fixture", "created_at": "2026-08-21T12:00:00+00:00"}],
            "messages": [{
                "id": "message-fixture", "role": "user", "content": "private conversation marker",
                "created_at": "2026-08-21T12:00:01+00:00", "conversation_id": "conversation-fixture",
                "origin": "user",
            }],
        }), encoding="utf-8"
    )
    repository = MemorySqliteRepository(root / "local-data/memory/masha.sqlite3")
    payload = json.loads((PROJECT_ROOT / "tests/fixtures/test_memory.json").read_text(encoding="utf-8"))
    repository.replace_document(MemoryDocument.model_validate(payload), action="backup_fixture")
    for name in (
        "home-timezone.json", "models.json", "proactive-policy.json", "autonomy-safety.json",
        "internet-access.json", "action-autonomy.json",
    ):
        file = root / "local-data/config" / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text('{"version":"fixture"}', encoding="utf-8")
    (root / "local-data/config/google-calendar.json").write_text(
        json.dumps({
            "connector_id": "google-calendar", "client_id": "desktop-client-identifier",
            "secret_ref": {"value": "google-calendar-primary"},
            "requested_scope": "https://www.googleapis.com/auth/calendar.readonly",
        }), encoding="utf-8",
    )
    for name in (
        "external-observations.json", "document-read-receipts.json", "daily-runtime-receipts.json", "agent-runs.json",
    ):
        file = root / "local-data/runtime" / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text('{"receipt":"fixture"}', encoding="utf-8")
    _registered_skill(root)
    # Deliberately present but outside the inventory allowlist.
    (root / ".env").write_text("SECRET=do-not-back-up", encoding="utf-8")
    (root / "local-data/random.json").write_text('{"random":true}', encoding="utf-8")
    (root / "local-data/secrets").mkdir(exist_ok=True)
    (root / "local-data/secrets/token.json").write_text('{"token":"no"}', encoding="utf-8")
    (root / "local-data/skill-install-staging").mkdir(exist_ok=True)
    (root / "local-data/skill-install-staging/payload.bin").write_bytes(b"no")
    (root / "local-data/config/skill-installs.json").write_text('{"proposals":[]}', encoding="utf-8")
    (root / "local-data/runtime/local-document-inputs.json").write_text('{"token":"no"}', encoding="utf-8")
    return root


def _registered_skill(root: Path) -> None:
    package = root / "local-data/skills/backup_skill"
    package.mkdir(parents=True)
    (package / "skill.json").write_text(json.dumps({
        "schema_version": "1.0", "skill_id": "backup_skill", "name": "Backup Skill",
        "version": "1.0.0", "description": "Fixture skill kept inert during backup.",
        "entrypoint": "fixture_skill:run", "instructions_file": "SKILL.md",
        "capabilities": ["local_read"], "requested_scopes": ["fixture:backup"],
        "risk_level": "observe", "maximum_autonomy_level": 0,
        "supports_dry_run": True, "supports_rollback": False,
        "verification": "Inspect only immutable fixture files.",
    }), encoding="utf-8")
    (package / "SKILL.md").write_text("# Inert fixture skill\n", encoding="utf-8")
    (package / "fixture_skill.py").write_text("raise RuntimeError('must not import')\n", encoding="utf-8")
    registry = SkillRegistry(skills_root=root / "local-data/skills", state_path=root / "local-data/config/skills.json")
    registry.register("backup_skill")


@pytest.fixture
def home(tmp_path: Path) -> Path:
    return _home(tmp_path / "home")


def _backup(home: Path, tmp_path: Path, name: str = "masha.mashabackup") -> Path:
    output = tmp_path / name
    result = WholeHomeBackupService(home).create_backup(output, PASSPHRASE)
    assert result.verified is True
    return output


def _archive_paths(bundle: Path, tmp_path: Path) -> tuple[dict, set[str]]:
    tar_path = tmp_path / "inspection.tar"
    decrypt_file(bundle, tar_path, PASSPHRASE)
    with tarfile.open(tar_path) as archive:
        manifest = json.loads(archive.extractfile("manifest.json").read())
        return manifest, {item.name for item in archive.getmembers()}


def _rewrite_component(bundle: Path, tmp_path: Path, archive_path: str, transform) -> Path:
    original = tmp_path / "original.tar"
    rewritten = tmp_path / "rewritten.tar"
    decrypt_file(bundle, original, PASSPHRASE)
    with tarfile.open(original) as source:
        manifest = json.loads(source.extractfile("manifest.json").read())
        content_by_name = {
            item.name: source.extractfile(item).read()
            for item in source.getmembers() if item.isfile() and item.name != "manifest.json"
        }
    content_by_name[archive_path] = transform(content_by_name[archive_path])
    for component in manifest["components"]:
        if component["archive_path"] == archive_path:
            content = content_by_name[archive_path]
            component["byte_size"] = len(content)
            component["sha256"] = hashlib.sha256(content).hexdigest()
    with tarfile.open(rewritten, "w") as target:
        manifest_bytes = json.dumps(manifest, separators=(",", ":")).encode("utf-8")
        manifest_info = tarfile.TarInfo("manifest.json")
        manifest_info.size = len(manifest_bytes)
        target.addfile(manifest_info, io.BytesIO(manifest_bytes))
        for name, content in content_by_name.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            target.addfile(info, io.BytesIO(content))
    output = tmp_path / "rewritten.mashabackup"
    encrypt_file(rewritten, output, PASSPHRASE)
    return output


def _rewrite_manifest(bundle: Path, tmp_path: Path, mutate) -> Path:
    original = tmp_path / "original.tar"
    rewritten = tmp_path / "rewritten.tar"
    decrypt_file(bundle, original, PASSPHRASE)
    with tarfile.open(original) as source:
        manifest = json.loads(source.extractfile("manifest.json").read())
        content_by_name = {
            item.name: source.extractfile(item).read()
            for item in source.getmembers() if item.isfile() and item.name != "manifest.json"
        }
    mutate(manifest, content_by_name)
    with tarfile.open(rewritten, "w") as target:
        manifest_bytes = json.dumps(manifest, separators=(",", ":")).encode("utf-8")
        manifest_info = tarfile.TarInfo("manifest.json")
        manifest_info.size = len(manifest_bytes)
        target.addfile(manifest_info, io.BytesIO(manifest_bytes))
        for name, content in content_by_name.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            target.addfile(info, io.BytesIO(content))
    output = tmp_path / "rewritten.mashabackup"
    encrypt_file(rewritten, output, PASSPHRASE)
    return output


def _component(manifest: dict, component_id: str) -> dict:
    return next(item for item in manifest["components"] if item["component_id"] == component_id)


def test_create_verify_inventory_and_explicit_exclusions(home: Path, tmp_path: Path):
    secret_value = "credential-value-never-in-backup"
    secret_store = InMemorySecretStore()
    secret_store.put(SecretRef(value="google-calendar-primary"), secret_value)
    bundle = _backup(home, tmp_path)
    manifest, paths = _archive_paths(bundle, tmp_path)

    assert {"identity", "memory_database", "conversation_history"}.issubset(
        {item["component_id"] for item in manifest["components"]}
    )
    assert "payload/skills/backup_skill/skill.json" in paths
    assert "payload/skills/backup_skill/fixture_skill.py" in paths
    assert "payload/config/google-calendar.json" in paths
    assert all("secrets" not in path and "random" not in path for path in paths)
    assert all("skill-install" not in path and "local-document" not in path for path in paths)
    assert manifest["recovery_hold_required"] is True
    assert manifest["snapshot_requires_quiescence"] is True
    assert manifest["secrets_included"] is False
    assert secret_value.encode("utf-8") not in bundle.read_bytes()
    inspected_tar = tmp_path / "secret-inspection.tar"
    decrypt_file(bundle, inspected_tar, PASSPHRASE)
    assert secret_value.encode("utf-8") not in inspected_tar.read_bytes()
    assert secret_value not in json.dumps(manifest)
    assert all(item["format_version"] is None for item in manifest["components"])
    checked = verify_backup(bundle, PASSPHRASE)
    assert checked.components_verified == len(manifest["components"])


@pytest.mark.parametrize("relative", [
    "identity/masha.identity.json", "local-data/memory/masha.sqlite3", "local-data/conversations/history.json",
])
def test_missing_required_component_fails(home: Path, tmp_path: Path, relative: str):
    (home / relative).unlink()
    with pytest.raises(BackupError, match="required_component_missing"):
        WholeHomeBackupService(home).create_backup(tmp_path / "failed.mashabackup", PASSPHRASE)
    assert not (tmp_path / "failed.mashabackup").exists()


def test_optional_receipts_may_be_absent_and_sqlite_is_a_single_valid_snapshot(home: Path, tmp_path: Path):
    shutil.rmtree(home / "local-data/runtime")
    original = hashlib.sha256((home / "local-data/memory/masha.sqlite3").read_bytes()).hexdigest()
    bundle = _backup(home, tmp_path)
    _, paths = _archive_paths(bundle, tmp_path)
    assert "payload/runtime/external-observations.json" not in paths
    assert "payload/memory/masha.sqlite3-wal" not in paths
    assert "payload/memory/masha.sqlite3-shm" not in paths
    assert hashlib.sha256((home / "local-data/memory/masha.sqlite3").read_bytes()).hexdigest() == original
    assert verify_backup(bundle, PASSPHRASE).verified


def test_bundle_is_encrypted_and_nondeterministic(home: Path, tmp_path: Path):
    first = _backup(home, tmp_path, "first.mashabackup")
    second = _backup(home, tmp_path, "second.mashabackup")
    marker = b"private conversation marker"
    assert marker not in first.read_bytes()
    assert first.read_bytes() != second.read_bytes()
    first_header = read_public_header(first)
    second_header = read_public_header(second)
    assert first_header["kdf"]["salt"] != second_header["kdf"]["salt"]
    assert first_header["cipher"]["nonce"] != second_header["cipher"]["nonce"]
    assert set(first_header) == {"format_version", "kdf", "cipher"}


def test_decrypted_snapshot_component_hashes_match_manifest(home: Path, tmp_path: Path):
    bundle = _backup(home, tmp_path)
    tar_path = tmp_path / "inspection.tar"
    decrypt_file(bundle, tar_path, PASSPHRASE)
    with tarfile.open(tar_path) as archive:
        manifest = json.loads(archive.extractfile("manifest.json").read())
        for component in manifest["components"]:
            content = archive.extractfile(component["archive_path"]).read()
            assert len(content) == component["byte_size"]
            assert hashlib.sha256(content).hexdigest() == component["sha256"]


def test_wrong_passphrase_ciphertext_tamper_and_header_tamper_fail_closed(home: Path, tmp_path: Path):
    bundle = _backup(home, tmp_path)
    with pytest.raises(BackupError, match="decryption_failed"):
        verify_backup(bundle, "wrong phrase")
    changed = tmp_path / "changed.mashabackup"
    data = bytearray(bundle.read_bytes())
    data[-20] ^= 1
    changed.write_bytes(data)
    with pytest.raises(BackupError, match="decryption_failed"):
        verify_backup(changed, PASSPHRASE)
    data = bytearray(bundle.read_bytes())
    data[20] ^= 1
    changed.write_bytes(data)
    with pytest.raises(BackupError):
        verify_backup(changed, PASSPHRASE)


def test_final_bundle_is_only_published_after_verification(home: Path, tmp_path: Path):
    destination = tmp_path / "masha.mashabackup"
    with patch("backend.backup.service.verify_backup", side_effect=BackupError("invalid_backup")):
        with pytest.raises(BackupError, match="invalid_backup"):
            WholeHomeBackupService(home).create_backup(destination, PASSPHRASE)
    assert not destination.exists()
    assert not list(tmp_path.glob("*.partial"))


@pytest.mark.parametrize("name", ["../escape", "/absolute", "payload/link"])
def test_untrusted_archive_paths_and_links_are_rejected(home: Path, tmp_path: Path, name: str):
    tar_path = tmp_path / "unsafe.tar"
    with tarfile.open(tar_path, "w") as archive:
        info = tarfile.TarInfo(name)
        if name == "payload/link":
            info.type = tarfile.SYMTYPE
            info.linkname = "elsewhere"
            archive.addfile(info)
        else:
            info.size = 1
            archive.addfile(info, __import__("io").BytesIO(b"x"))
    bundle = tmp_path / "unsafe.mashabackup"
    encrypt_file(tar_path, bundle, PASSPHRASE)
    with pytest.raises(BackupError, match="invalid_backup"):
        verify_backup(bundle, PASSPHRASE)


def test_duplicate_and_undeclared_archive_entries_are_rejected(tmp_path: Path):
    tar_path = tmp_path / "unsafe.tar"
    with tarfile.open(tar_path, "w") as archive:
        for _ in range(2):
            info = tarfile.TarInfo("manifest.json")
            info.size = 2
            archive.addfile(info, __import__("io").BytesIO(b"{}"))
        info = tarfile.TarInfo("payload/extra.txt")
        info.size = 1
        archive.addfile(info, __import__("io").BytesIO(b"x"))
    bundle = tmp_path / "unsafe.mashabackup"
    encrypt_file(tar_path, bundle, PASSPHRASE)
    with pytest.raises(BackupError, match="invalid_backup"):
        verify_backup(bundle, PASSPHRASE)


def test_absurd_outer_header_length_is_rejected_before_payload_allocation(tmp_path: Path):
    bundle = tmp_path / "invalid.mashabackup"
    bundle.write_bytes(b"MSHBKUP1" + (999_999).to_bytes(4, "big"))
    with pytest.raises(BackupError, match="invalid_backup"):
        verify_backup(bundle, PASSPHRASE)


def test_member_enumeration_stops_at_the_archive_member_bound(tmp_path: Path):
    tar_path = tmp_path / "many-members.tar"
    with tarfile.open(tar_path, "w") as archive:
        for index in range(_MAX_ARCHIVE_MEMBERS + 1):
            archive.addfile(tarfile.TarInfo(f"payload/member-{index}"))
    bundle = tmp_path / "many-members.mashabackup"
    encrypt_file(tar_path, bundle, PASSPHRASE)
    with pytest.raises(BackupError, match="invalid_backup"):
        verify_backup(bundle, PASSPHRASE)


def test_oversized_envelope_is_rejected_before_plaintext_staging(tmp_path: Path):
    bundle = tmp_path / "oversized.mashabackup"
    bundle.write_bytes(b"small")
    with patch("backend.backup.crypto._bundle_size", return_value=MAX_ENCRYPTED_BUNDLE_BYTES + 1):
        with pytest.raises(BackupError, match="backup_too_large"):
            verify_backup(bundle, PASSPHRASE)


def test_creation_cannot_publish_when_the_v1_envelope_bound_is_exceeded(home: Path, tmp_path: Path):
    destination = tmp_path / "too-large.mashabackup"
    with patch("backend.backup.crypto.MAX_ENCRYPTED_BUNDLE_BYTES", 1):
        with pytest.raises(BackupError, match="backup_too_large"):
            WholeHomeBackupService(home).create_backup(destination, PASSPHRASE)
    assert not destination.exists()


@pytest.mark.parametrize("name", ["payload//double", "payload/./dot", "payload/trailing/"])
def test_noncanonical_tar_paths_are_rejected(tmp_path: Path, name: str):
    tar_path = tmp_path / "noncanonical.tar"
    with tarfile.open(tar_path, "w") as archive:
        info = tarfile.TarInfo(name)
        info.size = 1
        archive.addfile(info, io.BytesIO(b"x"))
    bundle = tmp_path / "noncanonical.mashabackup"
    encrypt_file(tar_path, bundle, PASSPHRASE)
    with pytest.raises(BackupError, match="invalid_backup"):
        verify_backup(bundle, PASSPHRASE)


def test_staged_skill_registry_remains_consistent_when_live_registry_changes(home: Path, tmp_path: Path, monkeypatch):
    original_stage_file = BackupInventory._stage_file

    def mutate_live_registry_after_staging(self, component_id, source, archive_path, *, required):
        staged = original_stage_file(self, component_id, source, archive_path, required=required)
        if component_id == "config_skills":
            live = self.root / "local-data/config/skills.json"
            raw = json.loads(live.read_text(encoding="utf-8"))
            raw["skills"][0]["package_sha256"] = "0" * 64
            live.write_text(json.dumps(raw), encoding="utf-8")
        return staged

    monkeypatch.setattr(BackupInventory, "_stage_file", mutate_live_registry_after_staging)
    bundle = _backup(home, tmp_path)
    manifest, _ = _archive_paths(bundle, tmp_path)
    archived_registry = next(item for item in manifest["components"] if item["component_id"] == "config_skills")
    assert archived_registry["archive_path"] == "payload/config/skills.json"
    assert verify_backup(bundle, PASSPHRASE).verified


def test_identity_memory_version_mismatch_is_not_verified(home: Path, tmp_path: Path):
    bundle = _backup(home, tmp_path)

    def mismatch(value: bytes) -> bytes:
        database = tmp_path / "mismatch.sqlite3"
        database.write_bytes(value)
        connection = sqlite3.connect(database)
        try:
            connection.execute("UPDATE memory_metadata SET value = ? WHERE key = 'identity_version'", ("other-identity",))
            connection.commit()
        finally:
            connection.close()
        return database.read_bytes()

    changed = _rewrite_component(bundle, tmp_path, "payload/memory/masha.sqlite3", mismatch)
    with pytest.raises(BackupError, match="invalid_backup"):
        verify_backup(changed, PASSPHRASE)


def test_malformed_or_orphaned_conversation_history_is_not_verified(home: Path, tmp_path: Path):
    bundle = _backup(home, tmp_path)
    changed = _rewrite_component(
        bundle,
        tmp_path,
        "payload/conversations/history.json",
        lambda _: json.dumps({
            "conversations": [],
            "messages": [{
                "id": "orphan", "role": "user", "content": "orphan",
                "created_at": "2026-08-21T12:00:01+00:00", "conversation_id": "missing", "origin": "user",
            }],
        }).encode("utf-8"),
    )
    with pytest.raises(BackupError, match="invalid_backup"):
        verify_backup(changed, PASSPHRASE)


def test_manifest_missing_required_identity_is_invalid_without_key_error(home: Path, tmp_path: Path):
    bundle = _backup(home, tmp_path)

    def remove_identity(manifest, content):
        identity = _component(manifest, "identity")
        manifest["components"].remove(identity)
        content.pop(identity["archive_path"])

    changed = _rewrite_manifest(bundle, tmp_path, remove_identity)
    with pytest.raises(BackupError, match="invalid_backup"):
        verify_backup(changed, PASSPHRASE)


def test_manifest_required_identity_cannot_be_marked_optional(home: Path, tmp_path: Path):
    bundle = _backup(home, tmp_path)
    changed = _rewrite_manifest(
        bundle, tmp_path, lambda manifest, _: _component(manifest, "identity").update(required=False),
    )
    with pytest.raises(BackupError, match="invalid_backup"):
        verify_backup(changed, PASSPHRASE)


def test_manifest_identity_cannot_be_remapped_to_another_allowed_path(home: Path, tmp_path: Path):
    bundle = _backup(home, tmp_path)

    def remap_identity(manifest, content):
        identity = _component(manifest, "identity")
        models = _component(manifest, "config_models")
        identity_bytes = content.pop(identity["archive_path"])
        content.pop(models["archive_path"])
        content[models["archive_path"]] = identity_bytes
        manifest["components"].remove(models)
        identity["archive_path"] = "payload/config/models.json"
        identity["byte_size"] = len(identity_bytes)
        identity["sha256"] = hashlib.sha256(identity_bytes).hexdigest()

    changed = _rewrite_manifest(bundle, tmp_path, remap_identity)
    with pytest.raises(BackupError, match="invalid_backup"):
        verify_backup(changed, PASSPHRASE)


@pytest.mark.parametrize(("component_id", "archive_path"), [
    ("random_component", "payload/random.json"),
    ("secrets_token", "payload/secrets/token.json"),
])
def test_manifest_cannot_authorize_unknown_or_secret_component(
    home: Path, tmp_path: Path, component_id: str, archive_path: str,
):
    bundle = _backup(home, tmp_path)

    def add_unknown(manifest, content):
        payload = b"untrusted manifest inventory"
        manifest["components"].append({
            "component_id": component_id,
            "archive_path": archive_path,
            "required": False,
            "byte_size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "format_version": None,
        })
        content[archive_path] = payload

    changed = _rewrite_manifest(bundle, tmp_path, add_unknown)
    with pytest.raises(BackupError, match="invalid_backup"):
        verify_backup(changed, PASSPHRASE)


def test_manifest_cannot_map_two_component_ids_to_one_archive_path(home: Path, tmp_path: Path):
    bundle = _backup(home, tmp_path)

    def duplicate_path(manifest, _):
        _component(manifest, "config_home_timezone")["archive_path"] = _component(
            manifest, "config_models",
        )["archive_path"]

    changed = _rewrite_manifest(bundle, tmp_path, duplicate_path)
    with pytest.raises(BackupError, match="invalid_backup"):
        verify_backup(changed, PASSPHRASE)


def test_valid_archived_installed_skill_family_still_verifies(home: Path, tmp_path: Path):
    assert verify_backup(_backup(home, tmp_path), PASSPHRASE).verified


def test_installed_skill_symlink_escape_is_rejected(home: Path, tmp_path: Path, monkeypatch):
    link = home / "local-data/skills/backup_skill/escape.txt"
    try:
        link.symlink_to(home / ".env")
    except OSError:
        link.write_text("simulated symlink", encoding="utf-8")
        manifest, _ = SkillRegistry.inspect_package_path(link.parent)
        digest = json.loads((home / "local-data/config/skills.json").read_text(encoding="utf-8"))["skills"][0]["package_sha256"]
        original_is_symlink = Path.is_symlink

        def simulated_is_symlink(value: Path) -> bool:
            return value == link or original_is_symlink(value)

        monkeypatch.setattr(Path, "is_symlink", simulated_is_symlink)
        monkeypatch.setattr(
            "backend.backup.inventory.SkillRegistry.inspect_package_path",
            lambda _: (manifest, digest),
        )
    with pytest.raises(BackupError, match="installed_skill_symlink_unsupported"):
        WholeHomeBackupService(home).create_backup(tmp_path / "failed.mashabackup", PASSPHRASE)
