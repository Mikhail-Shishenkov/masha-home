from pathlib import Path

import pytest

from backend.conversation.conversation_service import ConversationService, ConversationUnavailableError
from backend.conversation.conversation_store import ConversationStore
from backend.conversation.memory_intent import MemoryIntentHandler, MemoryProposalStore
from backend.memory.confirmed_memory_service import ConfirmedMemoryService
from backend.identity.identity_kernel import IdentityKernel
from backend.identity.identity_store import IdentityStore
from backend.llm.fake_provider import FakeProvider
from backend.llm.model_provider import ModelProviderUnavailableError
from backend.llm.model_router import ModelRouter
from backend.memory.memory_retriever import MemoryRetriever
from backend.memory.memory_store import MemoryStore
from backend.memory.working_memory import WorkingMemory


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _service(tmp_path, provider):
    store = MemoryStore(PROJECT_ROOT / "tests" / "fixtures" / "test_memory.json")
    return ConversationService(
        identity_kernel=IdentityKernel(IdentityStore(PROJECT_ROOT / "identity" / "masha.identity.json")),
        memory_retriever=MemoryRetriever(store),
        working_memory=WorkingMemory(),
        router=ModelRouter([provider]),
        history=ConversationStore(tmp_path / "history.json"),
    )


def test_service_routes_identity_bounded_memory_time_and_history(tmp_path):
    provider = FakeProvider(provider_id="ollama-local", response_text="Я здесь.")
    service = _service(tmp_path, provider)

    conversation_id, text = service.send("Привет, Маша.", project_id="project_masha_home")

    assert text == "Я здесь."
    assert provider.last_request is not None
    assert provider.last_request.identity_context.name == "Маша"
    assert "current_local_time" in provider.last_request.private_context
    assert len(provider.last_request.private_context["memory_context"]) <= 6
    assert [message.role.value for message in service.history.messages(conversation_id)] == ["user", "assistant"]


def test_service_returns_controlled_error_for_unavailable_local_model(tmp_path):
    service = _service(tmp_path, FakeProvider(provider_id="ollama-local", available=False))

    with pytest.raises(ConversationUnavailableError, match="Локальная модель"):
        service.send("Привет", project_id="project_masha_home")

    assert len(service.history.messages(next(iter(service.history._data["conversations"]))["id"])) == 1


def test_service_reloads_history_and_uses_it_for_continuation_without_memory_mutation(tmp_path):
    provider = FakeProvider(provider_id="ollama-local", response_text="first")
    first_service = _service(tmp_path, provider)
    original_memory = (PROJECT_ROOT / "tests" / "fixtures" / "test_memory.json").read_bytes()

    conversation_id, _ = first_service.send("first user turn", project_id="project_masha_home")

    reloaded_provider = FakeProvider(provider_id="ollama-local", response_text="second")
    reloaded_service = _service(tmp_path, reloaded_provider)
    continued_id, text = reloaded_service.send(
        "second user turn",
        project_id="project_masha_home",
        conversation_id=conversation_id,
    )

    assert continued_id == conversation_id
    assert text == "second"
    assert [message.content for message in reloaded_provider.last_request.messages] == [
        "first user turn",
        "first",
        "second user turn",
    ]
    assert [message.role.value for message in reloaded_service.history.messages(conversation_id)] == [
        "user", "assistant", "user", "assistant"
    ]
    assert (PROJECT_ROOT / "tests" / "fixtures" / "test_memory.json").read_bytes() == original_memory


def test_service_handles_explicit_memory_without_calling_the_model(tmp_path, memory_path):
    provider = FakeProvider(provider_id="ollama-local", response_text="should not be used")
    memory_store = MemoryStore(memory_path)
    service = ConversationService(
        identity_kernel=IdentityKernel(IdentityStore(PROJECT_ROOT / "identity" / "masha.identity.json")),
        memory_retriever=MemoryRetriever(memory_store),
        working_memory=WorkingMemory(),
        router=ModelRouter([provider]),
        history=ConversationStore(tmp_path / "history.json"),
        memory_intent_handler=MemoryIntentHandler(
            proposal_store=MemoryProposalStore(tmp_path / "proposals.json"),
            confirmed_memory=ConfirmedMemoryService(memory_store),
        ),
    )
    original_memory = Path(memory_path).read_bytes()

    conversation_id, proposal = service.send("Запомни, что я предпочитаю локальные модели", project_id="project_masha_home")
    _, confirmation = service.send("Да", project_id="project_masha_home", conversation_id=conversation_id)

    assert "Сохраняем?" in proposal
    assert confirmation == "Готово, сохранила."
    assert provider.last_request is None
    assert Path(memory_path).read_bytes() != original_memory


def test_service_does_not_create_memory_from_an_ordinary_message(tmp_path, memory_path):
    provider = FakeProvider(provider_id="ollama-local", response_text="ordinary reply")
    memory_store = MemoryStore(memory_path)
    service = ConversationService(
        identity_kernel=IdentityKernel(IdentityStore(PROJECT_ROOT / "identity" / "masha.identity.json")),
        memory_retriever=MemoryRetriever(memory_store),
        working_memory=WorkingMemory(),
        router=ModelRouter([provider]),
        history=ConversationStore(tmp_path / "history.json"),
        memory_intent_handler=MemoryIntentHandler(
            proposal_store=MemoryProposalStore(tmp_path / "proposals.json"),
            confirmed_memory=ConfirmedMemoryService(memory_store),
        ),
    )
    original_memory = Path(memory_path).read_bytes()

    _, response = service.send("Я сегодня ездил на мотоцикле", project_id="project_masha_home")

    assert response == "ordinary reply"
    assert Path(memory_path).read_bytes() == original_memory
