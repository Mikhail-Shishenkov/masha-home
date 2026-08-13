import os
import subprocess
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.llm.model_profiles import ModelProfileStore
from backend.runtime.daily_runtime import DailyCycleReceipt
from backend.temporal.proactive import ProactivePolicy, ProactivePolicyStore
from backend.temporal.proactive_daemon import ProactiveDaemon
from backend.runtime.safety import AutonomySafetyService


def test_background_and_manual_modes_are_persistent_and_deterministic(tmp_path, monkeypatch):
    profiles = ModelProfileStore(tmp_path / "local-data" / "config" / "models.json")
    policy_store = ProactivePolicyStore(profiles.path.parent / "proactive-policy.json")
    service = SimpleNamespace(model_profiles=profiles, history=None, temporal_engine=None, memory_retriever=SimpleNamespace(memory_store=None), identity_kernel=None, router=None)
    monkeypatch.setattr("backend.conversation.cli.build_service", lambda project_root: service)
    calls = []
    class Runtime:
        def __init__(self, **kwargs): pass
        def run_cycle(self, policy):
            calls.append(policy.runtime_mode)
            now = datetime.now(timezone.utc)
            return DailyCycleReceipt(cycle_id="test", started_at=now, finished_at=now, model_profile="primary")
    monkeypatch.setattr("backend.temporal.proactive_daemon.DailyRuntime", Runtime)

    policy_store.save(ProactivePolicy(runtime_mode="manual"))
    ProactiveDaemon(tmp_path).run(max_cycles=1)
    assert calls == []
    policy_store.save(ProactivePolicy(runtime_mode="background"))
    ProactiveDaemon(tmp_path).run(max_cycles=1)
    assert calls == ["background"]
    assert ProactivePolicyStore(policy_store.path).load().runtime_mode == "background"


def test_daemon_lock_stop_and_status(tmp_path):
    daemon = ProactiveDaemon(tmp_path)
    daemon.lock_path.write_text(str(os.getpid()), encoding="utf-8")
    with pytest.raises(FileExistsError):
        daemon.run(max_cycles=1)
    daemon.lock_path.unlink()
    daemon.request_stop()
    daemon.run(max_cycles=1)
    assert daemon.status()["daemon"] == "stopped"


def test_current_process_lock_is_detected_without_signalling_it(tmp_path, monkeypatch):
    daemon = ProactiveDaemon(tmp_path)
    daemon.lock_path.write_text(str(os.getpid()), encoding="utf-8")
    monkeypatch.setattr(os, "kill", lambda *_: pytest.fail("must not signal current process"))

    assert daemon.is_running() is True


def test_other_live_process_and_dead_pid_are_probed_without_signalling(tmp_path):
    daemon = ProactiveDaemon(tmp_path)
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        daemon.lock_path.write_text(str(child.pid), encoding="ascii")
        assert daemon.is_running() is True
    finally:
        child.terminate()
        child.wait(timeout=10)

    assert daemon.is_running() is False


def test_malformed_lock_and_unexpected_probe_failure_are_safe(tmp_path):
    daemon = ProactiveDaemon(
        tmp_path,
        process_probe=lambda _pid: (_ for _ in ()).throw(RuntimeError("probe broke")),
    )
    daemon.lock_path.write_text("not-a-pid", encoding="ascii")
    assert daemon.is_running() is False
    assert daemon.liveness().state == "stopped"

    daemon.lock_path.write_text(str(os.getpid() + 100_000), encoding="ascii")
    assert daemon.is_running() is False
    assert daemon.liveness().state == "unknown"
    assert "probe broke" in daemon.liveness().detail

    with pytest.raises(FileExistsError):
        daemon.run(max_cycles=1)
    assert daemon.lock_path.exists()


def test_emergency_stop_prevents_daemon_service_build_and_exits(tmp_path, monkeypatch):
    daemon = ProactiveDaemon(tmp_path, sleep=lambda _: None)
    AutonomySafetyService(store=daemon.safety_store).engage()
    builds = []
    monkeypatch.setattr(
        "backend.conversation.cli.build_service",
        lambda project_root: builds.append(project_root),
    )

    daemon.run(max_cycles=1)

    assert builds == []
    assert daemon.status()["daemon"] == "stopped"
    assert daemon.status()["last_reason"] == "emergency_stop_engaged"


def test_stale_lock_is_recovered_and_cycle_failure_is_recorded(tmp_path, monkeypatch):
    profiles = ModelProfileStore(tmp_path / "local-data" / "config" / "models.json")
    ProactivePolicyStore(profiles.path.parent / "proactive-policy.json").save(
        ProactivePolicy(runtime_mode="background")
    )
    service = SimpleNamespace(
        model_profiles=profiles,
        history=None,
        temporal_engine=None,
        memory_retriever=SimpleNamespace(memory_store=None),
        identity_kernel=None,
        router=None,
    )
    monkeypatch.setattr("backend.conversation.cli.build_service", lambda project_root: service)

    class FailingRuntime:
        def __init__(self, **kwargs): pass
        def run_cycle(self, policy): raise RuntimeError("isolated cycle failure")

    monkeypatch.setattr("backend.temporal.proactive_daemon.DailyRuntime", FailingRuntime)
    daemon = ProactiveDaemon(tmp_path)
    daemon.lock_path.write_text("stale", encoding="utf-8")
    daemon.run(max_cycles=1)

    assert not daemon.lock_path.exists()
    assert daemon.status()["daemon"] == "stopped"
    assert daemon.status()["last_result"] == "error"
    assert daemon.status()["last_reason"] == "cycle_error"
    assert "isolated cycle failure" in daemon.status()["last_error"]


def test_cycle_failure_does_not_prevent_next_background_cycle(tmp_path, monkeypatch):
    profiles = ModelProfileStore(tmp_path / "local-data" / "config" / "models.json")
    ProactivePolicyStore(profiles.path.parent / "proactive-policy.json").save(ProactivePolicy(runtime_mode="background", cycle_interval_seconds=10))
    service = SimpleNamespace(model_profiles=profiles, history=None, temporal_engine=None, memory_retriever=SimpleNamespace(memory_store=None), identity_kernel=None, router=None)
    monkeypatch.setattr("backend.conversation.cli.build_service", lambda project_root: service)
    calls = []

    class RecoveringRuntime:
        def __init__(self, **kwargs): pass
        def run_cycle(self, policy):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("first cycle failed")
            now = datetime.now(timezone.utc)
            return DailyCycleReceipt(cycle_id="recovered", started_at=now, finished_at=now, model_profile="primary")

    monkeypatch.setattr("backend.temporal.proactive_daemon.DailyRuntime", RecoveringRuntime)
    daemon = ProactiveDaemon(tmp_path, sleep=lambda _: None)
    daemon.run(max_cycles=2)

    assert len(calls) == 2
    assert daemon.status()["last_result"] == "suppress"
    assert daemon.status()["last_error"] is None


def test_service_build_failure_does_not_prevent_next_cycle(tmp_path, monkeypatch):
    profiles = ModelProfileStore(tmp_path / "local-data" / "config" / "models.json")
    ProactivePolicyStore(profiles.path.parent / "proactive-policy.json").save(ProactivePolicy(runtime_mode="manual", cycle_interval_seconds=10))
    service = SimpleNamespace(model_profiles=profiles, history=None, temporal_engine=None, memory_retriever=SimpleNamespace(memory_store=None), identity_kernel=None, router=None)
    calls = []

    def build_service(project_root):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("temporary startup failure")
        return service

    monkeypatch.setattr("backend.conversation.cli.build_service", build_service)
    daemon = ProactiveDaemon(tmp_path, sleep=lambda _: None)
    daemon.run(max_cycles=2)

    assert len(calls) == 2
    assert daemon.status()["last_result"] == "manual_mode"
    assert daemon.status()["last_error"] is None
