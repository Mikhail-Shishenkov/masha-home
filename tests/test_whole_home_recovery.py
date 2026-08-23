import json
import shutil
from pathlib import Path

import pytest

from backend.backup import WholeHomeBackupService
from backend.backup.errors import BackupError
from backend.backup.recovery import WholeHomeRecoveryService
from backend.backup.recovery_journal import RecoveryError, RecoveryJournal
from backend.backup.recovery_models import RecoveryPhase, RestoreMode
from backend.application.composition import build_conversation_service
from backend.conversation.conversation_store import ConversationStore
from backend.memory.memory_models import MemoryDocument
from backend.memory.sqlite_repository import MemorySqliteRepository
from backend.runtime.runtime_lease import RuntimeLease
from backend.runtime.runtime_lease import RuntimeLeaseError
from backend.skills.registry import SkillRegistry
from backend.temporal.proactive_daemon import ProactiveDaemon


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PASSPHRASE = "recovery phrase"


def _home(root: Path, *, with_optional_receipt: bool = True) -> Path:
    shutil.copytree(PROJECT_ROOT / "identity", root / "identity")
    repository = MemorySqliteRepository(root / "local-data/memory/masha.sqlite3")
    payload = json.loads((PROJECT_ROOT / "tests/fixtures/test_memory.json").read_text(encoding="utf-8"))
    repository.replace_document(MemoryDocument.model_validate(payload), action="recovery_fixture")
    history = ConversationStore(root / "local-data/conversations/history.json")
    conversation = history.create()
    history.append(conversation.id, role=__import__("backend.conversation.conversation_models", fromlist=["ConversationRole"]).ConversationRole.USER, content="state A")
    config = root / "local-data/config"
    config.mkdir(parents=True, exist_ok=True)
    (config / "models.json").write_text('{"profiles":[]}', encoding="utf-8")
    _skill(root)
    if with_optional_receipt:
        receipt = root / "local-data/runtime/document-read-receipts.json"
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text('{"state":"A"}', encoding="utf-8")
    return root


def _skill(root: Path) -> None:
    package = root / "local-data/skills/recovery_skill"
    package.mkdir(parents=True)
    (package / "skill.json").write_text(json.dumps({
        "schema_version": "1.0", "skill_id": "recovery_skill", "name": "Recovery Skill",
        "version": "1.0.0", "description": "Inert recovery fixture skill package.",
        "entrypoint": "fixture:run", "instructions_file": "SKILL.md", "capabilities": ["local_read"],
        "requested_scopes": ["fixture:recovery"], "risk_level": "observe", "maximum_autonomy_level": 0,
        "supports_dry_run": True, "supports_rollback": False, "verification": "Read fixture only.",
    }), encoding="utf-8")
    (package / "SKILL.md").write_text("# Recovery fixture\n", encoding="utf-8")
    SkillRegistry(skills_root=root / "local-data/skills", state_path=root / "local-data/config/skills.json").register("recovery_skill")


def _backup(root: Path, tmp_path: Path) -> Path:
    path = tmp_path / "state-a.mashabackup"
    WholeHomeBackupService(root).create_backup(path, PASSPHRASE)
    return path


def test_replace_recovery_drill_restores_state_a_and_enters_hold(tmp_path: Path):
    root = _home(tmp_path / "home")
    backup = _backup(root, tmp_path)
    preview = WholeHomeRecoveryService(root).preview_restore(backup, PASSPHRASE)
    (root / "local-data/config/models.json").write_text('{"state":"B"}', encoding="utf-8")
    (root / "local-data/runtime/document-read-receipts.json").write_text('{"state":"B"}', encoding="utf-8")
    (root / "local-data/skills/extra").mkdir()
    result = WholeHomeRecoveryService(root).restore(
        backup, PASSPHRASE, expected_backup_id=preview.backup_id, restore_mode=RestoreMode.REPLACE,
    )
    assert result.phase is RecoveryPhase.HOLD
    assert (root / "local-data/config/models.json").read_text(encoding="utf-8") == '{"profiles":[]}'
    assert (root / "local-data/runtime/document-read-receipts.json").read_text(encoding="utf-8") == '{"state":"A"}'
    assert not (root / "local-data/skills/extra").exists()
    assert (root / "local-data/recovery/checkpoints" / f"{result.recovery_id}.mashabackup").exists()


def test_absent_optional_component_and_current_skill_do_not_survive_replace(tmp_path: Path):
    root = _home(tmp_path / "home", with_optional_receipt=False)
    backup = _backup(root, tmp_path)
    preview = WholeHomeRecoveryService(root).preview_restore(backup, PASSPHRASE)
    receipt = root / "local-data/runtime/document-read-receipts.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text('{"new":true}', encoding="utf-8")
    (root / "local-data/skills/post_backup").mkdir()
    WholeHomeRecoveryService(root).restore(backup, PASSPHRASE, expected_backup_id=preview.backup_id, restore_mode=RestoreMode.REPLACE)
    assert not receipt.exists()
    assert not (root / "local-data/skills/post_backup").exists()


def test_fresh_restore_and_nonempty_fresh_rejection(tmp_path: Path):
    source = _home(tmp_path / "source")
    backup = _backup(source, tmp_path)
    fresh = tmp_path / "fresh"
    preview = WholeHomeRecoveryService(fresh).preview_restore(backup, PASSPHRASE)
    result = WholeHomeRecoveryService(fresh).restore(backup, PASSPHRASE, expected_backup_id=preview.backup_id, restore_mode=RestoreMode.FRESH)
    assert result.phase is RecoveryPhase.HOLD
    assert (fresh / "local-data/memory/masha.sqlite3").exists()
    (fresh / "local-data/random.json").write_text("unowned", encoding="utf-8")
    with pytest.raises(RecoveryError, match="recovery_in_progress"):
        WholeHomeRecoveryService(fresh).restore(backup, PASSPHRASE, expected_backup_id=preview.backup_id, restore_mode=RestoreMode.FRESH)


def test_wrong_passphrase_stale_id_and_active_runtime_leave_home_unchanged(tmp_path: Path):
    root = _home(tmp_path / "home")
    backup = _backup(root, tmp_path)
    before = (root / "local-data/memory/masha.sqlite3").read_bytes()
    service = WholeHomeRecoveryService(root)
    with pytest.raises(Exception):
        service.preview_restore(backup, "wrong")
    preview = service.preview_restore(backup, PASSPHRASE)
    with pytest.raises(RecoveryError, match="restore_confirmation_stale"):
        service.restore(backup, PASSPHRASE, expected_backup_id="other", restore_mode=RestoreMode.REPLACE)
    lease = RuntimeLease(root)
    lease.acquire()
    try:
        with pytest.raises(RecoveryError, match="home_not_quiescent"):
            service.restore(backup, PASSPHRASE, expected_backup_id=preview.backup_id, restore_mode=RestoreMode.REPLACE)
    finally:
        lease.release()
    assert (root / "local-data/memory/masha.sqlite3").read_bytes() == before


def test_apply_failure_rolls_back_and_interrupted_journal_blocks_startup(tmp_path: Path):
    root = _home(tmp_path / "home")
    backup = _backup(root, tmp_path)
    preview = WholeHomeRecoveryService(root).preview_restore(backup, PASSPHRASE)
    before = (root / "local-data/config/models.json").read_bytes()
    with pytest.raises(RecoveryError, match="restore_failed"):
        WholeHomeRecoveryService(root).restore(
            backup,
            PASSPHRASE,
            expected_backup_id=preview.backup_id,
            restore_mode=RestoreMode.REPLACE,
            fault_injector=lambda component: (_ for _ in ()).throw(RuntimeError("boom")) if component == "config_models" else None,
        )
    assert (root / "local-data/config/models.json").read_bytes() == before
    state = RecoveryJournal(root).load()
    assert state is not None and state.phase is RecoveryPhase.ROLLED_BACK
    applying = state.model_copy(update={"phase": RecoveryPhase.APPLYING})
    RecoveryJournal(root).save(applying)
    with pytest.raises(RecoveryError, match="recovery_in_progress"):
        RecoveryJournal(root).assert_start_allowed()


def test_hold_suppresses_proactive_daemon_and_release_keeps_home_valid(tmp_path: Path):
    root = _home(tmp_path / "home")
    backup = _backup(root, tmp_path)
    preview = WholeHomeRecoveryService(root).preview_restore(backup, PASSPHRASE)
    service = WholeHomeRecoveryService(root)
    service.restore(backup, PASSPHRASE, expected_backup_id=preview.backup_id, restore_mode=RestoreMode.REPLACE)
    daemon = ProactiveDaemon(root, sleep=lambda _: None)
    daemon.run(max_cycles=1)
    assert daemon.status()["last_reason"] == "recovery_hold_active"
    assert service.release_recovery_hold().phase is RecoveryPhase.RELEASED
    assert (root / "local-data/memory/masha.sqlite3").exists()


def test_hold_allows_normal_composition_but_applying_blocks_it(tmp_path: Path):
    root = _home(tmp_path / "home")
    backup = _backup(root, tmp_path)
    service = WholeHomeRecoveryService(root)
    preview = service.preview_restore(backup, PASSPHRASE)
    service.restore(backup, PASSPHRASE, expected_backup_id=preview.backup_id, restore_mode=RestoreMode.REPLACE)
    assert build_conversation_service(project_root=root).history.latest() is not None
    state = RecoveryJournal(root).load()
    RecoveryJournal(root).save(state.model_copy(update={"phase": RecoveryPhase.APPLYING}))
    with pytest.raises(RecoveryError, match="recovery_blocked"):
        build_conversation_service(project_root=root)


def test_unknown_daemon_liveness_fails_closed(tmp_path: Path):
    root = _home(tmp_path / "home")
    backup = _backup(root, tmp_path)
    preview = WholeHomeRecoveryService(root).preview_restore(backup, PASSPHRASE)
    daemon = ProactiveDaemon(root, process_probe=lambda _: (_ for _ in ()).throw(PermissionError("unknown")))
    daemon.lock_path.write_text("987654", encoding="ascii")
    with pytest.raises(RecoveryError, match="home_not_quiescent"):
        WholeHomeRecoveryService(root, daemon=daemon).restore(
            backup, PASSPHRASE, expected_backup_id=preview.backup_id, restore_mode=RestoreMode.REPLACE,
        )


def test_checkpoint_failure_or_unverified_checkpoint_leaves_home_untouched(tmp_path: Path):
    root = _home(tmp_path / "home")
    backup = _backup(root, tmp_path)
    service = WholeHomeRecoveryService(root)
    preview = service.preview_restore(backup, PASSPHRASE)
    before = (root / "local-data/memory/masha.sqlite3").read_bytes()
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "backend.backup.recovery.WholeHomeBackupService.create_backup",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(BackupError("backup_write_failed")),
        )
        with pytest.raises(RecoveryError, match="current_home_incomplete"):
            service.restore(backup, PASSPHRASE, expected_backup_id=preview.backup_id, restore_mode=RestoreMode.REPLACE)
    assert (root / "local-data/memory/masha.sqlite3").read_bytes() == before


def test_rollback_failure_enters_blocked_and_journal_never_contains_passphrase(tmp_path: Path, monkeypatch):
    root = _home(tmp_path / "home")
    backup = _backup(root, tmp_path)
    service = WholeHomeRecoveryService(root)
    preview = service.preview_restore(backup, PASSPHRASE)
    real_materialize = __import__("backend.backup.recovery", fromlist=["materialize_verified_backup"]).materialize_verified_backup
    calls = {"count": 0}

    def fail_rollback_materialization(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 2:
            raise BackupError("invalid_backup")
        return real_materialize(*args, **kwargs)

    monkeypatch.setattr("backend.backup.recovery.materialize_verified_backup", fail_rollback_materialization)
    with pytest.raises(RecoveryError, match="recovery_blocked"):
        service.restore(
            backup,
            PASSPHRASE,
            expected_backup_id=preview.backup_id,
            restore_mode=RestoreMode.REPLACE,
            fault_injector=lambda component: (_ for _ in ()).throw(RuntimeError("fail apply")) if component == "config_models" else None,
        )
    state = RecoveryJournal(root).load()
    assert state is not None and state.phase is RecoveryPhase.BLOCKED
    assert PASSPHRASE not in (root / "local-data/recovery/state.json").read_text(encoding="utf-8")


def test_held_recovery_guards_exclude_desktop_and_daemon(tmp_path: Path):
    root = _home(tmp_path / "home")
    service = WholeHomeRecoveryService(root)
    with service._held_writer_guards():
        with pytest.raises(Exception):
            RuntimeLease(root).acquire()
        with pytest.raises(Exception):
            ProactiveDaemon(root)._lease.acquire()
        assert not (root / "local-data/runtime/home-runtime.lock").is_symlink()
        assert not (root / "local-data/runtime/proactive-daemon.lock").is_symlink()
    assert not (root / "local-data/runtime/home-runtime.lock").exists()
    assert not (root / "local-data/runtime/proactive-daemon.lock").exists()


def test_race_before_either_guard_leaves_home_unmodified(tmp_path: Path, monkeypatch):
    root = _home(tmp_path / "home")
    backup = _backup(root, tmp_path)
    preview = WholeHomeRecoveryService(root).preview_restore(backup, PASSPHRASE)
    before = (root / "local-data/memory/masha.sqlite3").read_bytes()
    service = WholeHomeRecoveryService(root)
    rival = RuntimeLease(root)

    def lose_home_race():
        rival.acquire()
        raise RuntimeLeaseError("lost")

    monkeypatch.setattr(service.home_lease, "acquire", lose_home_race)
    with pytest.raises(RecoveryError, match="home_not_quiescent"):
        service.restore(backup, PASSPHRASE, expected_backup_id=preview.backup_id, restore_mode=RestoreMode.REPLACE)
    rival.release()
    assert (root / "local-data/memory/masha.sqlite3").read_bytes() == before
    assert RecoveryJournal(root).load() is None


def test_daemon_race_before_guard_leaves_home_unmodified(tmp_path: Path, monkeypatch):
    root = _home(tmp_path / "home")
    backup = _backup(root, tmp_path)
    preview = WholeHomeRecoveryService(root).preview_restore(backup, PASSPHRASE)
    before = (root / "local-data/memory/masha.sqlite3").read_bytes()
    service = WholeHomeRecoveryService(root)
    rival = ProactiveDaemon(root)._lease

    def lose_daemon_race():
        rival.acquire()
        raise RuntimeLeaseError("lost")

    monkeypatch.setattr(service.daemon_lease, "acquire", lose_daemon_race)
    with pytest.raises(RecoveryError, match="home_not_quiescent"):
        service.restore(backup, PASSPHRASE, expected_backup_id=preview.backup_id, restore_mode=RestoreMode.REPLACE)
    rival.release()
    assert (root / "local-data/memory/masha.sqlite3").read_bytes() == before
    assert RecoveryJournal(root).load() is None


def test_hold_and_checkpointed_block_new_restore(tmp_path: Path):
    root = _home(tmp_path / "home")
    backup = _backup(root, tmp_path)
    service = WholeHomeRecoveryService(root)
    preview = service.preview_restore(backup, PASSPHRASE)
    service.restore(backup, PASSPHRASE, expected_backup_id=preview.backup_id, restore_mode=RestoreMode.REPLACE)
    with pytest.raises(RecoveryError, match="recovery_in_progress"):
        service.restore(backup, PASSPHRASE, expected_backup_id=preview.backup_id, restore_mode=RestoreMode.REPLACE)
    held = service.journal.load()
    service.journal.save(held.model_copy(update={"phase": RecoveryPhase.CHECKPOINTED}))
    with pytest.raises(RecoveryError, match="recovery_in_progress"):
        service.restore(backup, PASSPHRASE, expected_backup_id=preview.backup_id, restore_mode=RestoreMode.REPLACE)


def test_interrupted_replace_rolls_back_checkpoint_and_wrong_phrase_does_not_mutate(tmp_path: Path):
    root = _home(tmp_path / "home")
    backup = _backup(root, tmp_path)
    service = WholeHomeRecoveryService(root)
    preview = service.preview_restore(backup, PASSPHRASE)
    result = service.restore(backup, PASSPHRASE, expected_backup_id=preview.backup_id, restore_mode=RestoreMode.REPLACE)
    (root / "local-data/config/models.json").write_text('{"state":"interrupted"}', encoding="utf-8")
    held = service.journal.load()
    service.journal.save(held.model_copy(update={"phase": RecoveryPhase.APPLYING}))
    before = (root / "local-data/config/models.json").read_bytes()
    with pytest.raises(RecoveryError):
        service.recover_interrupted("wrong")
    assert (root / "local-data/config/models.json").read_bytes() == before
    assert service.journal.load().phase is RecoveryPhase.BLOCKED
    rolled = service.recover_interrupted(PASSPHRASE)
    assert rolled.phase is RecoveryPhase.ROLLED_BACK
    assert (root / "local-data/config/models.json").read_text(encoding="utf-8") == '{"profiles":[]}'


def test_interrupted_fresh_retries_only_same_backup(tmp_path: Path):
    source = _home(tmp_path / "source")
    backup = _backup(source, tmp_path)
    root = tmp_path / "fresh"
    service = WholeHomeRecoveryService(root)
    preview = service.preview_restore(backup, PASSPHRASE)
    service.restore(backup, PASSPHRASE, expected_backup_id=preview.backup_id, restore_mode=RestoreMode.FRESH)
    state = service.journal.load()
    service.journal.save(state.model_copy(update={"phase": RecoveryPhase.BLOCKED}))
    (root / "local-data/config/models.json").write_text('{"state":"partial"}', encoding="utf-8")
    with pytest.raises(RecoveryError, match="restore_confirmation_stale"):
        service.recover_interrupted(PASSPHRASE, backup_path=backup, expected_backup_id="other")
    retried = service.recover_interrupted(PASSPHRASE, backup_path=backup, expected_backup_id=preview.backup_id)
    assert retried.phase is RecoveryPhase.HOLD
    assert (root / "local-data/config/models.json").read_text(encoding="utf-8") == '{"profiles":[]}'


def test_symlinked_owned_parent_is_rejected_before_mutation(tmp_path: Path):
    root = _home(tmp_path / "home")
    backup = _backup(root, tmp_path)
    preview = WholeHomeRecoveryService(root).preview_restore(backup, PASSPHRASE)
    external = tmp_path / "external"
    external.mkdir()
    config = root / "local-data/config"
    shutil.rmtree(config)
    try:
        config.symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are unavailable on this platform")
    with pytest.raises(RecoveryError, match="recovery_target_unsafe"):
        WholeHomeRecoveryService(root).restore(backup, PASSPHRASE, expected_backup_id=preview.backup_id, restore_mode=RestoreMode.REPLACE)


def test_materialization_copies_the_same_authenticated_archive_it_verified(tmp_path: Path, monkeypatch):
    import backend.backup.service as backup_service

    source_a = _home(tmp_path / "a")
    source_b = _home(tmp_path / "b")
    (source_b / "local-data/config/models.json").write_text('{"profiles":["B"]}', encoding="utf-8")
    bundle_a = _backup(source_a, tmp_path)
    bundle_b = tmp_path / "state-b.mashabackup"
    WholeHomeBackupService(source_b).create_backup(bundle_b, PASSPHRASE)
    original_verify = backup_service._verify_tar

    def replace_source_after_verification(archive, temporary):
        result = original_verify(archive, temporary)
        shutil.copyfile(bundle_b, bundle_a)
        return result

    monkeypatch.setattr(backup_service, "_verify_tar", replace_source_after_verification)
    stage = tmp_path / "stage"
    materialized = backup_service.materialize_verified_backup(bundle_a, PASSPHRASE, stage)
    assert (materialized.payload_root / "config/models.json").read_text(encoding="utf-8") == '{"profiles":[]}'
