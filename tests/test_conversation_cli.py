from pathlib import Path

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


def test_cli_assembles_only_the_local_primary_provider():
    project_root = Path(__file__).resolve().parents[1]
    service = build_service(project_root=project_root)

    provider = service.router._providers["ollama-local"]
    assert provider.is_local is True
    assert provider.model_id == "qwen3.5:9b"
    assert provider.endpoint == "http://127.0.0.1:11434"
    assert isinstance(service.memory_retriever.memory_store, MemorySqliteRepository)
