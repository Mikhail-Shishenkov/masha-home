from pathlib import Path
import ast
import shutil

from backend.conversation.cli import build_service, run_cli
from backend.conversation.conversation_service import ConversationUnavailableError
from backend.memory.sqlite_repository import MemorySqliteRepository


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
