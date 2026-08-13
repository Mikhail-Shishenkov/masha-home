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
from backend.memory.shared_continuity import SharedContinuityService
from backend.temporal.temporal_engine import FixedClock, TemporalEngine
from backend.temporal.proactive import ProactiveDecisionEngine, ProactivePolicy
from backend.temporal.temporal_models import ProactiveDecision
from backend.temporal.temporal_runtime import TemporalRuntime
from datetime import datetime, timedelta, timezone


ROOT = Path(__file__).resolve().parents[1]
PROJECT = "project_masha_home"


def _service(tmp_path, memory_path):
    store = MemorySqliteRepository(tmp_path / "memory.sqlite3")
    store.import_json(memory_path)
    handler = MemoryIntentHandler(
        proposal_store=MemoryProposalStore(tmp_path / "proposals.json"),
        confirmed_memory=ConfirmedMemoryService(store),
        memory_management=MemoryManagementService(store),
        shared_continuity=SharedContinuityService(store),
    )
    return ConversationService(
        identity_kernel=IdentityKernel(IdentityStore(ROOT / "identity" / "masha.identity.json")),
        memory_retriever=MemoryRetriever(store), working_memory=WorkingMemory(),
        router=ModelRouter([FakeProvider(provider_id="ollama-local", response_text="model must not run")]),
        history=ConversationStore(tmp_path / "history.json"), memory_intent_handler=handler,
    ), store


def _send(service, message, conversation_id=None):
    return service.send(message, project_id=PROJECT, conversation_id=conversation_id)


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


def test_natural_query_routes_use_real_commitments_without_calling_model(tmp_path, memory_path):
    service, _ = _service(tmp_path, memory_path)

    answers = [_send(service, phrase)[1] for phrase in (
        "Маш, что у меня сегодня?",
        "Какие у нас дела?",
        "Что было запланировано?",
        "Что там с разработкой?",
    )]

    assert "Сейчас не вижу" in answers[0]  # fixture has no deadline today
    assert all("Продолжить разработку Masha Home" in answer for answer in answers[1:])


def test_generic_what_about_routes_only_when_a_real_commitment_matches(tmp_path, memory_path):
    service, _ = _service(tmp_path, memory_path)
    conversation_id, _ = _send(service, "Добавь мне задачу купить билеты")
    _send(service, "да", conversation_id)

    _, matched = _send(service, "Что там с билетами?", conversation_id)
    assert "купить билеты" in matched

    for phrase in ("Что с погодой?", "Что с фильмом?", "Как тебе кофе?"):
        _, ordinary = _send(service, phrase, conversation_id)
        assert ordinary == "model must not run"


def test_natural_create_routes_are_proposals_and_never_write_before_confirmation(tmp_path, memory_path):
    phrases = (
        "Добавь мне задачу купить молоко",
        "Запиши в дела позвонить врачу",
        "Надо не забыть купить корм",
    )
    for index, phrase in enumerate(phrases):
        case = tmp_path / f"natural-create-{index}"
        case.mkdir()
        service, store = _service(case, memory_path)
        before = len(store.read_document().commitments)

        conversation_id, answer = _send(service, phrase)

        assert "как обязательство" in answer
        assert len(store.read_document().commitments) == before
        _, confirmed = _send(service, "подтверждаю", conversation_id)
        assert confirmed == "Готово, сохранила."
        assert len(store.read_document().commitments) == before + 1


def test_natural_completion_resolves_real_records_and_still_requires_confirmation(tmp_path, memory_path):
    service, store = _service(tmp_path, memory_path)
    conversation_id, _ = _send(service, "Добавь мне задачу купить билеты")
    _send(service, "да", conversation_id)

    _, proposal = _send(service, "Билеты купил", conversation_id)
    assert "Отметить обязательство выполненным" in proposal
    assert next(item for item in store.read_document().commitments if item.text == "купить билеты").status.value == "open"
    _send(service, "да", conversation_id)
    assert next(item for item in store.read_document().commitments if item.text == "купить билеты").status.value == "completed"

    conversation_id, _ = _send(service, "Добавь мне задачу купить молоко")
    _send(service, "да", conversation_id)
    _, second = _send(service, "С молоком закончили", conversation_id)
    assert "Отметить обязательство выполненным" in second


def test_russian_case_reference_resolves_one_real_commitment(tmp_path, memory_path):
    service, store = _service(tmp_path, memory_path)
    conversation_id, _ = _send(service, "Запиши в дела позвонить врачу")
    _send(service, "да", conversation_id)

    _, proposal = _send(service, "С врачом закончили", conversation_id)

    assert "позвонить врачу" in proposal
    commitment = next(item for item in store.read_document().commitments if item.text == "позвонить врачу")
    assert commitment.status.value == "open"
    _send(service, "подтверждаю", conversation_id)
    commitment = next(item for item in store.read_document().commitments if item.text == "позвонить врачу")
    assert commitment.status.value == "completed"


def test_natural_forget_resolves_fact_semantically_and_requires_confirmation(tmp_path, memory_path):
    service, store = _service(tmp_path, memory_path)
    conversation_id, _ = _send(service, "Запомни, что я люблю чай")
    _send(service, "да", conversation_id)
    fact = next(item for item in store.read_document().facts if item.value == "я люблю чай")

    _, proposal = _send(service, "Забудь, что я люблю чай", conversation_id)
    assert "Скрыть из активной памяти" in proposal
    assert next(item for item in store.read_document().facts if item.id == fact.id).visibility.value == "visible"
    _send(service, "подтверждаю", conversation_id)
    assert next(item for item in store.read_document().facts if item.id == fact.id).visibility.value == "hidden"


def test_natural_continuity_is_explicit_and_legacy_developer_threads_are_filtered(tmp_path, memory_path):
    service, _ = _service(tmp_path, memory_path)
    conversation_id, clarification = _send(service, "Давай к этому вопросу потом вернёмся")
    assert "Какую именно тему" in clarification
    _, clarification_two = _send(service, "Не потеряй эту тему", conversation_id)
    assert "Какую именно тему" in clarification_two

    _, proposal = _send(service, "Не потеряй выбор света для комнаты", conversation_id)
    assert "Оставить это открытой нитью" in proposal
    _send(service, "да", conversation_id)
    _, answer = _send(service, "К чему мы хотели вернуться?", conversation_id)
    assert "выбор света для комнаты" in answer
    assert "memory_schema.json" not in answer
    assert "Python-модели" not in answer


def test_relationship_memory_can_be_queried_and_forgotten_without_physical_delete(tmp_path, memory_path):
    service, store = _service(tmp_path, memory_path)
    text = "сегодня мы наконец соединили память, дела и Дом"
    conversation_id, preview = _send(service, f"Сохрани как наш момент: {text}")
    assert "часть нашей" in preview
    _send(service, "да", conversation_id)

    _, history = _send(service, "Что есть в нашей истории?", conversation_id)
    assert text in history

    _, forget = _send(service, f"Забудь {text}", conversation_id)
    assert text in forget
    relationship = next(item for item in store.read_document().relationship_memories if text in str(item.content))
    assert relationship.visibility.value == "visible"
    _send(service, "да", conversation_id)
    relationship = next(item for item in store.read_document().relationship_memories if item.id == relationship.id)
    assert relationship.visibility.value == "hidden"
    assert any(
        event["action"] == "memory_forget" and event["payload"].get("record_id") == relationship.id
        for event in store.list_audit_events()
    )


def test_natural_minute_reminder_uses_temporal_engine_and_existing_commitment_contract(tmp_path, memory_path):
    service, store = _service(tmp_path, memory_path)
    now = datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc)
    engine = TemporalEngine(FixedClock(now))
    service.temporal_engine = engine
    service.memory_intent_handler.temporal_engine = engine

    conversation_id, preview = _send(service, "Напомни через две минуты сказать «мяу»")
    assert "как обязательство" in preview
    _send(service, "да", conversation_id)
    commitment = next(item for item in store.read_document().commitments if "мяу" in item.text)
    assert commitment.due_at == datetime(2026, 8, 12, 10, 2, tzinfo=timezone.utc)
    recovered = TemporalRuntime(
        store,
        TemporalEngine(FixedClock(datetime(2026, 8, 12, 10, 3, tzinfo=timezone.utc))),
    ).recover()
    assert recovered.events[0].source_commitment_id == commitment.id


def test_terminal_minute_reminder_flows_from_confirmation_to_due_event(tmp_path, memory_path):
    service, store = _service(tmp_path, memory_path)
    now = datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc)
    engine = TemporalEngine(FixedClock(now))
    service.temporal_engine = engine
    service.memory_intent_handler.temporal_engine = engine

    conversation_id, preview = _send(
        service,
        "Маша, напомни, чтобы я поставил чайник через 2 минуты",
    )
    assert "чтобы я поставил чайник" in preview
    assert "через 2 минуты" not in preview
    _send(service, "да", conversation_id)

    commitment = next(
        item for item in store.read_document().commitments
        if "поставил чайник" in item.text
    )
    assert commitment.text == "чтобы я поставил чайник"
    assert commitment.due_at == now + timedelta(minutes=2)
    recovered = TemporalRuntime(
        store,
        TemporalEngine(FixedClock(now + timedelta(minutes=3))),
    ).recover()
    event = next(event for event in recovered.events if event.source_commitment_id == commitment.id)
    decision = ProactiveDecisionEngine().decide(
        event,
        ProactivePolicy(
            enabled=True,
            proactive_level=1,
            allow_commitment_reminders=True,
            maximum_reminders=1,
        ),
        now=now + timedelta(minutes=3),
    )
    assert decision is ProactiveDecision.REMIND
