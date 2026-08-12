"""Deterministic chat bridge tests: language -> existing approved domain contracts."""

from pathlib import Path

from backend.conversation.conversation_service import ConversationService
from backend.conversation.conversation_store import ConversationStore
from backend.conversation.memory_intent import MemoryIntentHandler, MemoryProposalStore
from backend.identity.identity_kernel import IdentityKernel
from backend.identity.identity_store import IdentityStore
from backend.llm.fake_provider import FakeProvider
from backend.llm.model_router import ModelRouter
from backend.memory.confirmed_memory_service import ConfirmedMemoryService
from backend.memory.memory_management import MemoryManagementService
from backend.memory.memory_retriever import MemoryRetriever
from backend.memory.sqlite_repository import MemorySqliteRepository
from backend.memory.working_memory import WorkingMemory


ROOT = Path(__file__).resolve().parents[1]
PROJECT = "project_masha_home"


def _service(tmp_path, memory_path):
    store = MemorySqliteRepository(tmp_path / "memory.sqlite3")
    store.import_json(memory_path)
    handler = MemoryIntentHandler(
        proposal_store=MemoryProposalStore(tmp_path / "proposals.json"),
        confirmed_memory=ConfirmedMemoryService(store),
        memory_management=MemoryManagementService(store),
    )
    return ConversationService(
        identity_kernel=IdentityKernel(IdentityStore(ROOT / "identity" / "masha.identity.json")),
        memory_retriever=MemoryRetriever(store), working_memory=WorkingMemory(),
        router=ModelRouter([FakeProvider(provider_id="local", response_text="model must not run")]),
        history=ConversationStore(tmp_path / "history.json"), memory_intent_handler=handler,
    ), store


def test_remember_is_proposed_then_persisted_with_real_receipt(tmp_path, memory_path):
    service, store = _service(tmp_path, memory_path)
    conversation, proposal = service.send("Маша, запомни, что я предпочитаю чай", project_id=PROJECT)
    _, receipt = service.send("да", project_id=PROJECT, conversation_id=conversation)

    assert "Сохраняем?" in proposal
    assert receipt == "Готово, сохранила."
    assert any(item.value == "чай" for item in store.read_document().facts)


def test_natural_confirmation_variants_all_persist_only_after_receipt(tmp_path, memory_path):
    for index, confirmation in enumerate(("да", "сохраняй", "сохраняем", "подтверждаю")):
        case = tmp_path / str(index)
        case.mkdir()
        service, store = _service(case, memory_path)
        conversation, _ = service.send(f"Запомни, что проверка {index}", project_id=PROJECT)
        _, receipt = service.send(confirmation, project_id=PROJECT, conversation_id=conversation)

        assert receipt == "Готово, сохранила."
        assert any(item.value == f"проверка {index}" for item in store.read_document().facts)


def test_do_not_save_closes_proposal_without_writing(tmp_path, memory_path):
    service, store = _service(tmp_path, memory_path)
    before = len(store.read_document().facts)
    conversation, _ = service.send("Запомни, что это не должно сохраниться", project_id=PROJECT)
    _, receipt = service.send("не сохраняй", project_id=PROJECT, conversation_id=conversation)

    assert receipt == "Хорошо, не сохраняю."
    assert len(store.read_document().facts) == before


def test_natural_commitment_phrases_use_the_same_deterministic_route(tmp_path, memory_path):
    phrases = (
        "Добавь дело купить билеты",
        "Добавь в наши дела купить билеты",
        "Запиши нам дело купить билеты",
        "Напомни через два часа посмотреть Персеиды",
    )
    for index, phrase in enumerate(phrases):
        case = tmp_path / f"commitment-{index}"
        case.mkdir()
        service, _ = _service(case, memory_path)
        _, response = service.send(phrase, project_id=PROJECT)
        proposal = service.memory_intent_handler.proposal_store.pending_for_conversation(
            service.history.latest().id
        )[0]

        assert proposal.record_type == "commitment"
        assert "как обязательство" in response
        if "Персеиды" in phrase:
            assert proposal.record_payload["due_at"] is not None


def test_forget_is_explicit_confirmation_and_hides_actual_record(tmp_path, memory_path):
    service, store = _service(tmp_path, memory_path)
    conversation, proposal = service.send("Забудь learning_python", project_id=PROJECT)
    _, receipt = service.send("да", project_id=PROJECT, conversation_id=conversation)

    assert "Скрыть из активной памяти" in proposal
    assert "больше не используется" in receipt
    assert next(item for item in store.read_document().facts if item.id == "fact_002").visibility.value == "hidden"


def test_ambiguous_forget_requests_clarification_without_mutation(tmp_path, memory_path):
    service, store = _service(tmp_path, memory_path)
    _, answer = service.send("Забудь память", project_id=PROJECT)

    assert "Уточни" in answer
    assert all(item.visibility.value == "visible" for item in store.read_document().facts)


def test_show_memory_and_commitments_are_factual_read_only_views(tmp_path, memory_path):
    service, store = _service(tmp_path, memory_path)
    _, memory = service.send("Что ты обо мне помнишь?", project_id=PROJECT)
    _, commitments = service.send("Какие у меня сейчас дела?", project_id=PROJECT)

    assert "misha: learning_python" in memory
    assert "Продолжить разработку Masha Home" in commitments
    assert store.read_document().commitments[0].status.value == "open"


def test_shared_wording_for_commitment_lookup_uses_the_same_read_only_route(tmp_path, memory_path):
    service, _ = _service(tmp_path, memory_path)

    _, answer = service.send("Что у нас по делам?", project_id=PROJECT)

    assert "Продолжить разработку Masha Home" in answer


def test_create_and_complete_commitment_use_existing_confirmation_path(tmp_path, memory_path):
    service, store = _service(tmp_path, memory_path)
    conversation, proposal = service.send("Добавь дело: купить билеты", project_id=PROJECT)
    _, created = service.send("да", project_id=PROJECT, conversation_id=conversation)
    _, completion = service.send("Маша, отметь купить билеты выполненным", project_id=PROJECT, conversation_id=conversation)
    _, completed = service.send("да", project_id=PROJECT, conversation_id=conversation)

    assert "как обязательство" in proposal
    assert created == "Готово, сохранила."
    assert "Отметить обязательство выполненным" in completion
    assert completed == "Готово, обязательство отмечено выполненным."
    assert next(item for item in store.read_document().commitments if item.text == "купить билеты").status.value == "completed"


def test_unidentified_completion_is_truthful_and_does_not_change_commitment(tmp_path, memory_path):
    service, store = _service(tmp_path, memory_path)
    _, answer = service.send("Я это сделал", project_id=PROJECT)

    assert "Какое именно дело" in answer
    assert store.read_document().commitments[0].status.value == "open"


def test_update_fact_needs_confirmation_and_is_idempotent_after_receipt(tmp_path, memory_path):
    service, store = _service(tmp_path, memory_path)
    conversation, proposal = service.send("Обнови learning_python на уже уверенно пишет Python", project_id=PROJECT)
    _, first = service.send("да", project_id=PROJECT, conversation_id=conversation)
    _, second = service.send("да", project_id=PROJECT, conversation_id=conversation)

    assert "Обновить факт" in proposal
    assert first == "Готово. Подтверждённая память обновлена."
    assert "нет предложения памяти" in second
    assert next(item for item in store.read_document().facts if item.id == "fact_002").value == "уже уверенно пишет Python"
