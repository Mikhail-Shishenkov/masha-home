from datetime import datetime, timedelta, timezone
from pathlib import Path
import ast
import shutil

from backend.conversation.cli import _run_proactive_command, build_service, run_cli
from backend.temporal.proactive import ProactivePolicyStore
from backend.conversation.conversation_service import ConversationUnavailableError
from backend.memory.sqlite_repository import MemorySqliteRepository
from backend.temporal.proactive_events import ProactiveEvent, ProactiveEventState, ProactiveEventStore, ProactiveEventType, check_in_event_id
from backend.temporal.proactive_interaction import ProactiveInteractionStore
from backend.temporal.temporal_models import CheckInCandidate


class _History:
    def latest(self):
        return None


class _Service:
    def __init__(self, *, unavailable: bool = False):
        self.history = _History()
        self.unavailable = unavailable
        self.calls = []

    def send(self, message, *, project_id, conversation_id):
        self.calls.append((message, project_id, conversation_id))
        if self.unavailable:
            raise ConversationUnavailableError()
        return "conversation-1", "local reply"


def _input(values):
    iterator = iter(values)
    return lambda _prompt: next(iterator)


def test_cli_uses_conversation_service_and_exits():
    service = _Service()
    output = []

    run_cli(service, input_fn=_input(["hello", ":exit"]), output_fn=output.append)

    assert service.calls == [("hello", "project_masha_home", None)]
    assert "Conversation id: conversation-1" in output
    assert "Masha> local reply" in output


def test_cli_presents_controlled_local_model_failure():
    service = _Service(unavailable=True)
    output = []

    run_cli(service, input_fn=_input(["hello", ":exit"]), output_fn=output.append)

    assert any("local Ollama is not responding" in line for line in output)


def test_cli_assembles_local_provider_and_primary_execution_profile(tmp_path):
    source_root = Path(__file__).resolve().parents[1]
    project_root = tmp_path / "project"
    shutil.copytree(source_root / "identity", project_root / "identity")
    MemorySqliteRepository(project_root / "local-data" / "memory" / "masha.sqlite3").import_json(
        source_root / "tests" / "fixtures" / "test_memory.json"
    )
    service = build_service(project_root=project_root)

    provider = service.router._providers["ollama-local"]
    assert provider.is_local is True
    assert provider.model_id == ""
    assert provider.endpoint == "http://127.0.0.1:11434"
    assert service.model_profiles.get_active_profile().model_id == "qwen3.5:9b"
    assert isinstance(service.memory_retriever.memory_store, MemorySqliteRepository)


def test_cli_runtime_does_not_import_legacy_persona_or_context_builder():
    cli_path = Path(__file__).resolve().parents[1] / "backend" / "conversation" / "cli.py"
    imports = {
        node.module
        for node in ast.walk(ast.parse(cli_path.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert "backend.persona.persona_store" not in imports
    assert "backend.context" not in imports


def test_proactive_cli_persists_human_readable_policy_controls(tmp_path):
    source_root = Path(__file__).resolve().parents[1]
    project_root = tmp_path / "project"
    shutil.copytree(source_root / "identity", project_root / "identity")
    MemorySqliteRepository(project_root / "local-data" / "memory" / "masha.sqlite3").import_json(
        source_root / "tests" / "fixtures" / "test_memory.json"
    )
    service = build_service(project_root=project_root)
    output: list[str] = []

    _run_proactive_command("status", service=service, output_fn=output.append)
    assert "Инициативность: выключена" in output[-1]
    assert "Уровень: 0" in output[-1]

    _run_proactive_command("on", service=service, output_fn=output.append)
    _run_proactive_command("level 2", service=service, output_fn=output.append)
    _run_proactive_command("checkins on", service=service, output_fn=output.append)
    _run_proactive_command("settings", service=service, output_fn=output.append)

    persisted = ProactivePolicyStore(project_root / "local-data" / "config" / "proactive-policy.json").load()
    assert persisted.enabled is True
    assert persisted.proactive_level == 2
    assert persisted.allow_commitment_reminders is True
    assert persisted.allow_checkins is True
    assert "Напоминания: включены" in output[-1]
    assert "UUID" not in output[-1]

    _run_proactive_command("off", service=service, output_fn=output.append)
    assert ProactivePolicyStore(project_root / "local-data" / "config" / "proactive-policy.json").load().enabled is False


def test_proactive_pending_and_decision_history_are_human_readable(tmp_path):
    source_root = Path(__file__).resolve().parents[1]
    project_root = tmp_path / "project"
    shutil.copytree(source_root / "identity", project_root / "identity")
    repo = MemorySqliteRepository(project_root / "local-data" / "memory" / "masha.sqlite3")
    repo.import_json(source_root / "tests" / "fixtures" / "test_memory.json")
    service = build_service(project_root=project_root)
    now = datetime(2026, 8, 11, 12, tzinfo=timezone.utc)
    event_id = check_in_event_id("cli-anchor")
    events = ProactiveEventStore(repo)
    events.create(ProactiveEvent(event_id=event_id, event_type=ProactiveEventType.CHECK_IN, source_type="absence", source_id="cli-anchor", created_at=now, detected_at=now, payload={"absence_seconds": 3600, "anchor_created_at": (now - timedelta(hours=1)).isoformat()}))
    events.update_state(event_id, ProactiveEventState.CANDIDATE, now)
    candidate = CheckInCandidate(event_id=event_id, absence_duration_seconds=3600, last_message_at=now - timedelta(hours=1), current_local_time=now, proactive_level=2)
    interactions = ProactiveInteractionStore(repo)
    interactions.ensure_candidate(candidate)
    interactions.mark_delivered(event_id, "Миша, я рядом. Как ты?", now)
    repo.record_event(action="proactive_decision", entity_type="proactive_event", entity_id=event_id, payload={"decision": "check_in", "reason": "authorised", "model_profile": "primary"})
    output: list[str] = []

    _run_proactive_command("pending", service=service, output_fn=output.append)
    assert "1. Check-in" in output[-1]
    assert "Миша, я рядом" in output[-1]
    assert "ждёт реакции" in output[-1]
    assert event_id not in output[-1]

    _run_proactive_command("history", service=service, output_fn=output.append)
    assert "Решение: отправить" in output[-1]
    assert "настройки разрешают" in output[-1]
    assert event_id not in output[-1]
