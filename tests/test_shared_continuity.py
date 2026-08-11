import json
from datetime import datetime, timezone
from pathlib import Path

from backend.conversation.cli import _run_continuity_command, build_service
from backend.conversation.conversation_service import ConversationService
from backend.conversation.conversation_store import ConversationStore
from backend.conversation.context_compiler import ConversationContextCompiler
from backend.conversation.memory_intent import (
    MemoryIntentHandler,
    MemoryProposalStore,
    ProposalStatus,
)
from backend.identity.identity_kernel import IdentityKernel
from backend.identity.identity_store import IdentityStore
from backend.llm.model_models import ModelMessage
from backend.llm.fake_provider import FakeProvider
from backend.llm.model_router import ModelRouter
from backend.memory.confirmed_memory_service import ConfirmedMemoryService
from backend.memory.memory_models import ContinuityFollowUp, ContinuityState, FollowUpStatus
from backend.memory.memory_retriever import MemoryRetriever
from backend.memory.shared_continuity import SharedContinuityService
from backend.memory.sqlite_repository import MemorySqliteRepository
from backend.memory.working_memory import WorkingMemory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ID = "project_masha_home"
NOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


def _repository(tmp_path) -> MemorySqliteRepository:
    repository = MemorySqliteRepository(tmp_path / "memory.sqlite3")
    repository.import_json(PROJECT_ROOT / "tests" / "fixtures" / "test_memory.json")
    return repository


def _handler(tmp_path, repository):
    proposals = MemoryProposalStore(tmp_path / "memory-proposals.json")
    continuity = SharedContinuityService(repository, clock=lambda: NOW)
    return (
        MemoryIntentHandler(
            proposal_store=proposals,
            confirmed_memory=ConfirmedMemoryService(repository),
            shared_continuity=continuity,
        ),
        proposals,
        continuity,
    )


def test_shared_moment_requires_confirmation_and_survives_restart(tmp_path):
    repository = _repository(tmp_path)
    handler, proposals, _ = _handler(tmp_path, repository)

    preview = handler.handle(
        "Маша, сохрани как наш момент: мы впервые запустили тебя полностью локально",
        conversation_id="conversation-1",
        project_id=PROJECT_ID,
    )

    proposal = proposals.pending_for_conversation("conversation-1")[0]
    assert preview.handled is True
    assert "не как факт о тебе" in preview.response
    assert proposal.record_type == "relationship_memory"
    assert repository.read_document().relationship_memories == []

    confirmed = handler.handle(
        "да",
        conversation_id="conversation-1",
        project_id=PROJECT_ID,
    )
    restarted = MemorySqliteRepository(tmp_path / "memory.sqlite3").read_document()

    assert confirmed.response == "Готово, сохранила."
    assert proposals.get(proposal.id).status == ProposalStatus.CONFIRMED
    assert len(restarted.relationship_memories) == 1
    memory = restarted.relationship_memories[0]
    assert memory.content["declared_by"] == "misha"
    assert memory.content["confirmation"] == "explicit_user_confirmation"
    assert memory.source.value == "explicit_user_input"
    assert any(
        event["action"] == "confirmed_memory"
        and event["payload"].get("what") == "relationship_memory"
        for event in repository.list_audit_events()
    )


def test_ordinary_conversation_never_becomes_shared_memory(tmp_path):
    repository = _repository(tmp_path)
    handler, proposals, _ = _handler(tmp_path, repository)
    before = repository.read_document().model_dump(mode="json")

    result = handler.handle(
        "Сегодня был важный для нас разговор",
        conversation_id="conversation-1",
        project_id=PROJECT_ID,
    )

    assert result.handled is False
    assert proposals.pending_for_conversation("conversation-1") == ()
    assert repository.read_document().model_dump(mode="json") == before


def test_open_thread_confirmation_restart_and_resolution_do_not_change_commitment(tmp_path):
    repository = _repository(tmp_path)
    handler, proposals, continuity = _handler(tmp_path, repository)
    commitments_before = [item.model_dump(mode="json") for item in repository.read_document().commitments]

    preview = handler.handle(
        "Маша, оставь открытой нитью: придумать наш домашний ритуал запуска",
        conversation_id="conversation-1",
        project_id=PROJECT_ID,
    )
    proposal = proposals.pending_for_conversation("conversation-1")[0]

    assert "Оставить это открытой нитью" in preview.response
    assert repository.read_document().continuity_states == []
    handler.handle(
        f"да {proposal.id}",
        conversation_id="conversation-1",
        project_id=PROJECT_ID,
    )

    restarted_repository = MemorySqliteRepository(tmp_path / "memory.sqlite3")
    restarted_continuity = SharedContinuityService(restarted_repository, clock=lambda: NOW)
    assert restarted_continuity.open_follow_ups()[0][1].summary == "придумать наш домашний ритуал запуска"

    resolve = continuity.propose_resolve_thread(
        proposals,
        query="домашний ритуал",
        conversation_id="conversation-1",
    )
    continuity.confirm_proposal(resolve, proposals)

    assert SharedContinuityService(restarted_repository).open_follow_ups() == ()
    assert [
        item.model_dump(mode="json") for item in restarted_repository.read_document().commitments
    ] == commitments_before


def test_rejected_thread_and_repeated_confirmation_are_safe(tmp_path):
    repository = _repository(tmp_path)
    handler, proposals, _ = _handler(tmp_path, repository)
    handler.handle(
        "Маша, оставь открытой нитью: обсудить визуальный образ",
        conversation_id="c",
        project_id=PROJECT_ID,
    )
    proposal = proposals.pending_for_conversation("c")[0]

    rejected = handler.handle("нет", conversation_id="c", project_id=PROJECT_ID)
    repeated = handler.handle(f"да {proposal.id}", conversation_id="c", project_id=PROJECT_ID)

    assert rejected.response == "Хорошо, не сохраняю."
    assert "уже отменено" in repeated.response
    assert repository.read_document().continuity_states == []


def test_retrieval_and_context_keep_shared_semantics_bounded(tmp_path):
    repository = _repository(tmp_path)
    handler, _, continuity = _handler(tmp_path, repository)
    handler.handle(
        "Маша, сохрани как наш момент: первый локальный запуск",
        conversation_id="c",
        project_id=PROJECT_ID,
    )
    handler.handle("да", conversation_id="c", project_id=PROJECT_ID)
    proposal = continuity.propose_open_thread(
        handler.proposal_store,
        text="вернуться к характеру Маши",
        conversation_id="c",
    )
    continuity.confirm_proposal(proposal, handler.proposal_store)

    retrieved = MemoryRetriever(repository).retrieve(project_id=PROJECT_ID, limit=2)
    shared = [item for item in retrieved if item["type"] in {"relationship_memory", "continuity_state"}]
    request = ConversationContextCompiler(clock=lambda: NOW).compile(
        messages=(ModelMessage(role="user", content="Что между нами продолжается?"),),
        identity_context=IdentityKernel(
            IdentityStore(PROJECT_ROOT / "identity" / "masha.identity.json")
        ).build_context(),
        working_memory=shared,
    )
    records = request.private_context["memory_context"]

    assert {item["record_type"] for item in records} == {
        "relationship_memory",
        "continuity_state",
    }
    relationship = next(item for item in records if item["record_type"] == "relationship_memory")
    state = next(item for item in records if item["record_type"] == "continuity_state")
    assert relationship["content"]["text"] == "первый локальный запуск"
    assert state["open_follow_ups"][0]["summary"] == "вернуться к характеру Маши"
    assert "intended_follow_ups" not in state
    assert "affective_record_ids" not in state
    assert "НЕ Commitment" in request.private_context["shared_continuity_contract"]
    assert "Не обобщай" in request.private_context["shared_continuity_contract"]
    assert any(
        "bounded_shared_continuity_coverage" in item["reasons"]
        for item in shared
    )


def test_human_continuity_cli_hides_internal_ids(tmp_path):
    project_root = tmp_path / "project"
    (project_root / "identity").mkdir(parents=True)
    (project_root / "identity" / "masha.identity.json").write_bytes(
        (PROJECT_ROOT / "identity" / "masha.identity.json").read_bytes()
    )
    repository = MemorySqliteRepository(
        project_root / "local-data" / "memory" / "masha.sqlite3"
    )
    repository.import_json(PROJECT_ROOT / "tests" / "fixtures" / "test_memory.json")
    service = build_service(project_root=project_root)
    output: list[str] = []

    _run_continuity_command(
        "open обсудить Машин юмор",
        service=service,
        conversation_id="continuity-cli",
        output_fn=output.append,
    )
    assert "continuity confirm" in output[-1]
    assert "Proposal:" not in output[-1]

    _run_continuity_command(
        "confirm",
        service=service,
        conversation_id="continuity-cli",
        output_fn=output.append,
    )
    _run_continuity_command(
        "status",
        service=service,
        conversation_id="continuity-cli",
        output_fn=output.append,
    )

    assert "Что между нами продолжается" in output[-1]
    assert "обсудить Машин юмор" in output[-1]
    assert "followup_" not in output[-1]
    assert "continuity_" not in output[-1]


def test_raw_continuity_cli_remains_available_for_diagnostics(tmp_path):
    repository = _repository(tmp_path)
    continuity = SharedContinuityService(repository)

    payload = json.loads(continuity.raw())

    assert set(payload) == {"relationship_memories", "continuity_states"}


def test_corrupt_legacy_thread_is_quarantined_without_storage_mutation(tmp_path):
    repository = _repository(tmp_path)
    document = repository.read_document()
    corrupt = ContinuityState(
        id="continuity_masha_misha",
        relationship_key="masha:misha",
        last_interaction_at=None,
        affective_record_ids=[],
        current_focus=["Ïîâðåæä¸ííàÿ ñòðîêà"],
        intended_follow_ups=[
            ContinuityFollowUp(
                id="followup_legacy",
                topic="legacy",
                summary="Ïðîâåðèòü ñòàðóþ ïàìÿòü",
                reason_to_return="Ïðîäîëæèòü ðàáîòó",
                priority=0.8,
                status=FollowUpStatus.OPEN,
                source_memory_ids=[],
                revisit_after=None,
            )
        ],
        based_on_episode_ids=[],
        updated_at=NOW,
    )
    payload = document.model_dump(mode="json")
    payload["continuity_states"] = [corrupt.model_dump(mode="json")]
    repository.replace_document(payload)
    before = repository.read_document().model_dump(mode="json")
    continuity = SharedContinuityService(repository)

    assert continuity.open_follow_ups() == ()
    assert continuity.quarantined_count() == 1
    assert "Скрыты повреждённые legacy-фрагменты: 1" in continuity.render()
    assert all(
        item["type"] != "continuity_state"
        for item in MemoryRetriever(repository).retrieve(project_id=PROJECT_ID, limit=20)
    )
    assert repository.read_document().model_dump(mode="json") == before


def test_shared_continuity_question_activates_bounded_context_lens(tmp_path):
    repository = _repository(tmp_path)
    handler, proposals, continuity = _handler(tmp_path, repository)
    handler.handle(
        "Маша, сохрани как наш момент: первый локальный дом",
        conversation_id="seed",
        project_id=PROJECT_ID,
    )
    handler.handle("да", conversation_id="seed", project_id=PROJECT_ID)
    thread = continuity.propose_open_thread(
        proposals,
        text="придумать ритуал возвращения",
        conversation_id="seed",
    )
    continuity.confirm_proposal(thread, proposals)
    provider = FakeProvider(provider_id="ollama-local")
    service = ConversationService(
        identity_kernel=IdentityKernel(
            IdentityStore(PROJECT_ROOT / "identity" / "masha.identity.json")
        ),
        memory_retriever=MemoryRetriever(repository),
        working_memory=WorkingMemory(max_items=6),
        router=ModelRouter([provider]),
        history=ConversationStore(tmp_path / "history.json"),
    )

    service.send("Что между нами продолжается?", project_id=PROJECT_ID)
    memory_context = provider.last_request.private_context["memory_context"]

    assert provider.last_request.private_context["context_lens"] == "shared_continuity"
    assert {item["record_type"] for item in memory_context} == {
        "relationship_memory",
        "continuity_state",
    }
