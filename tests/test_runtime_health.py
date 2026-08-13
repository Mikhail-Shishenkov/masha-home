import shutil
from pathlib import Path

from backend.conversation.cli import build_service
from backend.llm.fake_provider import FakeProvider
from backend.llm.model_router import ModelRouter
from backend.memory.sqlite_repository import MemorySqliteRepository
from backend.runtime.health import RuntimeHealthService
from backend.temporal.proactive_daemon import ProactiveDaemon


def test_health_is_read_only_and_reports_core_boundaries(tmp_path):
    root = tmp_path / "project"
    source = Path(__file__).resolve().parents[1]
    shutil.copytree(source / "identity", root / "identity")
    repo = MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    repo.import_json(source / "tests" / "fixtures" / "test_memory.json")
    repo.backup_to(root / "local-data" / "memory-backups" / "verified.sqlite3")
    service = build_service(project_root=root)
    service.router = ModelRouter([FakeProvider(provider_id="ollama-local")])
    audit_before = repo.list_audit_events()

    report = RuntimeHealthService(service=service, project_root=root, daemon=ProactiveDaemon(root)).inspect()

    checks = {item.name: item for item in report.checks}
    assert report.status == "degraded"  # Daemon is intentionally not running.
    assert checks["identity"].status == "ok"
    assert checks["sqlite"].status == "ok"
    assert checks["model"].status == "ok"
    assert checks["backup"].status == "ok"
    assert repo.list_audit_events() == audit_before


def test_missing_backup_is_warning_not_runtime_failure(tmp_path):
    root = tmp_path / "project"
    source = Path(__file__).resolve().parents[1]
    shutil.copytree(source / "identity", root / "identity")
    MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3").import_json(source / "tests" / "fixtures" / "test_memory.json")
    service = build_service(project_root=root)
    service.router = ModelRouter([FakeProvider(provider_id="ollama-local")])

    report = RuntimeHealthService(service=service, project_root=root, daemon=ProactiveDaemon(root)).inspect()

    assert next(item for item in report.checks if item.name == "backup").status == "warning"
    assert report.status == "degraded"


def test_unexpected_daemon_probe_failure_degrades_with_truthful_detail(tmp_path):
    root = tmp_path / "project"
    source = Path(__file__).resolve().parents[1]
    shutil.copytree(source / "identity", root / "identity")
    MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3").import_json(
        source / "tests" / "fixtures" / "test_memory.json"
    )
    service = build_service(project_root=root)
    service.router = ModelRouter([FakeProvider(provider_id="ollama-local")])
    daemon = ProactiveDaemon(
        root,
        process_probe=lambda _pid: (_ for _ in ()).throw(RuntimeError("probe exploded")),
    )
    daemon.lock_path.write_text("987654", encoding="ascii")

    report = RuntimeHealthService(
        service=service,
        project_root=root,
        daemon=daemon,
    ).inspect()

    check = next(item for item in report.checks if item.name == "daemon")
    assert report.status == "degraded"
    assert check.status == "warning"
    assert "состояние неизвестно" in check.detail
    assert "probe exploded" in check.detail
