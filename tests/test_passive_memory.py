from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.application import build_masha_application
from backend.conversation.conversation_models import (
    ConversationMessage,
    ConversationMessageOrigin,
    ConversationRole,
)
from backend.llm.fake_provider import FakeProvider
from backend.llm.model_router import ModelRouter
from backend.memory.candidate_lifecycle import (
    CandidateConflictRequiresExplicitSupersession,
    PassiveMemoryService,
)
from backend.memory.memory_models import (
    CandidateStatus,
    CandidateType,
    Fact,
    FactStatus,
    IdentityCode,
    MemoryDocument,
    SourceType,
    Visibility,
)
from backend.memory.memory_retriever import MemoryRetrievalRequest, MemoryRetriever
from backend.memory.passive_detection import (
    COMMITMENT_THRESHOLD,
    DECISION_THRESHOLD,
    ExistingMemoryRelation,
    FACT_THRESHOLD,
    MemoryCandidateDetectionRequest,
    PassiveCandidatePayload,
    PassiveMemoryCandidateDetector,
    RELATIONSHIP_THRESHOLD,
)
from backend.memory.sqlite_repository import MemorySqliteRepository
from backend.temporal.temporal_engine import FixedClock, TemporalEngine
from backend.temporal.timezone_provider import HomeTimeZoneConfig, HomeTimeZoneProvider


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ID = "project_masha_home"
NOW = datetime(2026, 8, 13, 8, 0, tzinfo=timezone.utc)


def _engine(value: datetime = NOW) -> TemporalEngine:
    return TemporalEngine(
        FixedClock(value),
        HomeTimeZoneProvider(
            HomeTimeZoneConfig(
                timezone="Europe/Saratov",
                fallback_utc_offset_minutes=240,
            ),
            zone_loader=lambda _name: timezone(timedelta(hours=4)),
        ),
    )


def _minimal_document(*, facts=()) -> MemoryDocument:
    raw = json.loads((PROJECT_ROOT / "memory" / "test_memory.json").read_text(encoding="utf-8"))
    for collection in (
        "facts",
        "decisions",
        "commitments",
        "episodes",
        "memory_candidates",
        "reflections",
        "relationship_memories",
        "affective_records",
        "continuity_states",
    ):
        raw[collection] = []
    raw["facts"] = [item.model_dump(mode="json") for item in facts]
    return MemoryDocument.model_validate(raw)


def _repository(tmp_path, *, facts=()) -> MemorySqliteRepository:
    repository = MemorySqliteRepository(tmp_path / "memory.sqlite3")
    repository.replace_document(_minimal_document(facts=facts), action="test_setup")
    return repository


def _message(text: str, *, message_id: str = "message-current", created_at: datetime = NOW):
    return ConversationMessage(
        id=message_id,
        role=ConversationRole.USER,
        content=text,
        created_at=created_at,
        conversation_id="conversation-1",
        origin=ConversationMessageOrigin.USER,
    )


def _request(text: str, *, message_id: str = "message-current", engine=None):
    engine = engine or _engine()
    message = _message(text, message_id=message_id, created_at=engine.clock.now_utc())
    return MemoryCandidateDetectionRequest(
        conversation_id=message.conversation_id,
        project_id=PROJECT_ID,
        current_user_message=message,
        recent_messages=(message,),
        temporal_context=engine.context(None, user_message=text),
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        ("Я мужчина и зовут меня Миша.", (CandidateType.FACT, CandidateType.FACT)),
        ("Чай я обычно пью без сахара.", (CandidateType.FACT,)),
        ("Я предпочитаю машины на автомате.", (CandidateType.FACT,)),
        ("Я живу в Саратове.", (CandidateType.FACT,)),
        ("Мне удобнее работать ночью.", (CandidateType.FACT,)),
        ("Всё, оставляем Qwen 3.5 9B основной локальной моделью.", (CandidateType.DECISION,)),
        ("Решили: сначала интернет, потом Telegram.", (CandidateType.DECISION,)),
        ("Будем использовать PostgreSQL для этого проекта.", (CandidateType.DECISION,)),
        ("Завтра обязательно заеду забрать документы.", (CandidateType.COMMITMENT,)),
        (
            "Мне очень нравится, как мы вместе строим этот Дом; для меня это важный наш проект.",
            (CandidateType.RELATIONSHIP_MEMORY,),
        ),
        ("Я обычно ложусь около полуночи.", (CandidateType.FACT,)),
    ),
)
def test_positive_detection_fixture_is_typed_and_user_grounded(text, expected):
    detector = PassiveMemoryCandidateDetector(_engine())

    result = detector.detect(_request(text))

    assert tuple(item.candidate_type for item in result.proposals) == expected
    assert result.semantic_extractor_invoked is False
    assert result.gate_latency_ms >= 0
    assert result.extraction_latency_ms >= 0
    for proposal in result.proposals:
        assert proposal.record["source"] == SourceType.CONVERSATION.value


@pytest.mark.parametrize(
    "text",
    (
        "Сегодня устал.",
        "Я сейчас устал.",
        "Сегодня холодно.",
        "Хочу чай.",
        "Сейчас хочу чаю.",
        "Может, куплю телескоп.",
        "Какой телескоп купить?",
        "Бетельгейзе — красный сверхгигант.",
        "Доброе утро)))",
        "понятно",
        "Мой пароль qwerty123",
        "Мне кажется, я, наверное, больше люблю кофе.",
        "Может быть, мне нравится Linux.",
        "Сегодня хочу лечь пораньше.",
        "Надо бы когда-нибудь купить телескоп.",
        "Он сказал: я предпочитаю Linux.",
    ),
)
def test_negative_detection_fixture_fails_closed(text):
    result = PassiveMemoryCandidateDetector(_engine()).detect(_request(text))

    assert result.proposals == ()
    assert result.skip_reason is not None


def test_confidence_thresholds_are_explicit_and_stricter_for_high_risk_types():
    assert FACT_THRESHOLD == 0.82
    assert DECISION_THRESHOLD == 0.82
    assert COMMITMENT_THRESHOLD == 0.90
    assert RELATIONSHIP_THRESHOLD == 0.90


@pytest.mark.parametrize(
    "text",
    (
        "Мой API key abcdef123456",
        "Номер моей карты 4111111111111111",
        "Мой паспорт 6300 123456",
        "У меня медицинский диагноз диабет",
        "Я всегда голосую за одну партию",
        "Я православный и всегда соблюдаю пост",
        "Моя зарплата всегда составляет сто тысяч",
    ),
)
def test_sensitive_policy_rejects_before_extraction(text):
    result = PassiveMemoryCandidateDetector(_engine()).detect(_request(text))

    assert result.proposals == ()
    assert result.skip_reason in {
        "secret_rejected",
        "sensitive_personal_data_rejected",
    }


def test_assistant_claim_is_never_authoritative_evidence():
    current = _message("угу")
    assistant = ConversationMessage(
        id="assistant-claim",
        role=ConversationRole.ASSISTANT,
        content="Ты любишь кофе.",
        created_at=NOW - timedelta(seconds=2),
        conversation_id=current.conversation_id,
        origin=ConversationMessageOrigin.MODEL,
    )
    request = MemoryCandidateDetectionRequest(
        conversation_id=current.conversation_id,
        project_id=PROJECT_ID,
        current_user_message=current,
        recent_messages=(assistant, current),
        temporal_context=_engine().context(None, user_message=current.content),
    )

    result = PassiveMemoryCandidateDetector(_engine()).detect(request)

    assert result.proposals == ()


def test_commitment_uses_the_same_home_timezone_as_temporal_engine():
    engine = _engine(datetime(2026, 8, 13, 19, 0, tzinfo=timezone.utc))

    result = PassiveMemoryCandidateDetector(engine).detect(
        _request("Завтра обязательно заеду забрать документы.", engine=engine)
    )

    record = result.proposals[0].record
    due = datetime.fromisoformat(record["due_at"].replace("Z", "+00:00"))
    assert due.astimezone(engine.home_timezone.tzinfo).date().isoformat() == "2026-08-14"
    assert due.astimezone(engine.home_timezone.tzinfo).hour == 18


def test_pending_approval_is_atomic_idempotent_retrieval_isolated_and_audited(tmp_path):
    repository = _repository(tmp_path)
    service = PassiveMemoryService(
        repository=repository,
        detector=PassiveMemoryCandidateDetector(_engine()),
        clock=lambda: NOW,
    )

    observed = service.observe(_request("Чай я обычно пью без сахара."))
    candidate = observed.persisted_candidates[0]

    assert candidate.status is CandidateStatus.PENDING
    assert MemoryRetriever(repository).retrieve(
        MemoryRetrievalRequest(query="чай без сахара", project_id=PROJECT_ID)
    ) == []
    pending_document = repository.read_document()
    assert pending_document is not None
    assert pending_document.facts == []

    record = service.approve(candidate.id)
    retrievable = MemoryRetriever(repository).retrieve(
        MemoryRetrievalRequest(query="чай без сахара", project_id=PROJECT_ID)
    )
    second = service.approve(candidate.id)

    assert record == second
    assert record.source is SourceType.CONVERSATION
    assert [item["data"]["id"] for item in retrievable] == [record.id]
    document = repository.read_document()
    assert document is not None
    assert len([item for item in document.facts if item.id == record.id]) == 1
    approved = next(item for item in document.memory_candidates if item.id == candidate.id)
    assert approved.status is CandidateStatus.APPROVED
    assert approved.result_memory_id == record.id
    actions = [event["action"] for event in repository.list_audit_events()]
    assert actions.count("candidate_detected") == 1
    assert actions.count("candidate_approved") == 1
    assert actions.count("memory_created_from_candidate") == 1
    provenance = service.provenance(record.id)
    assert provenance.source is SourceType.CONVERSATION
    assert provenance.project_id == PROJECT_ID
    assert provenance.evidence_message_ids == ("message-current",)
    assert provenance.reviewed_by is IdentityCode.MISHA
    assert "Чай я обычно" not in json.dumps(repository.list_audit_events(), ensure_ascii=False)


def test_reject_and_expire_never_create_confirmed_memory(tmp_path):
    repository = _repository(tmp_path)
    mutable_now = {"value": NOW}
    service = PassiveMemoryService(
        repository=repository,
        detector=PassiveMemoryCandidateDetector(_engine()),
        clock=lambda: mutable_now["value"],
    )
    rejected_candidate = service.observe(
        _request("Я предпочитаю машины на автомате.", message_id="reject-me")
    ).persisted_candidates[0]

    rejected = service.reject(rejected_candidate.id)
    assert rejected.status is CandidateStatus.REJECTED
    assert service.reject(rejected_candidate.id) == rejected

    expiring = service.observe(
        _request("Я обычно ложусь около полуночи.", message_id="expire-me")
    ).persisted_candidates[0]
    mutable_now["value"] = NOW + timedelta(days=8)

    assert service.list_pending() == ()
    document = repository.read_document()
    assert document is not None
    expired = next(item for item in document.memory_candidates if item.id == expiring.id)
    assert expired.status is CandidateStatus.EXPIRED
    assert document.facts == []
    actions = [event["action"] for event in repository.list_audit_events()]
    assert "candidate_rejected" in actions
    assert "candidate_expired" in actions


def test_duplicate_active_memory_and_repeated_pending_candidate_are_suppressed(tmp_path):
    existing = Fact(
        id="fact-tea",
        subject="misha",
        key="tea_preference",
        value="чай без сахара",
        status=FactStatus.ACTIVE,
        visibility=Visibility.VISIBLE,
        importance=0.7,
        confidence=1.0,
        source=SourceType.CONVERSATION,
        owner=IdentityCode.MISHA,
        known_by=[IdentityCode.MISHA, IdentityCode.MASHA],
        project_ids=[PROJECT_ID],
        source_episode_ids=[],
        supersedes_id=None,
        superseded_by=None,
        created_at=NOW - timedelta(days=10),
        updated_at=NOW - timedelta(days=10),
    )
    repository = _repository(tmp_path, facts=(existing,))
    service = PassiveMemoryService(
        repository=repository,
        detector=PassiveMemoryCandidateDetector(_engine()),
        clock=lambda: NOW,
    )

    duplicate = service.observe(_request("Да, чай по-прежнему пью без сахара."))
    first = service.observe(
        _request("Я обычно ложусь около полуночи.", message_id="pending-1")
    )
    second = service.observe(
        _request("Я обычно ложусь около полуночи.", message_id="pending-2")
    )

    assert duplicate.persisted_candidates == ()
    assert duplicate.duplicate_record_ids == (existing.id,)
    assert len(first.persisted_candidates) == 1
    assert second.persisted_candidates == ()
    assert second.duplicate_candidate_ids == (first.persisted_candidates[0].id,)


def test_conflict_stays_pending_until_explicit_supersession(tmp_path):
    old = Fact(
        id="fact-transmission",
        subject="misha",
        key="transmission_preference",
        value="машины с механической коробкой",
        status=FactStatus.ACTIVE,
        visibility=Visibility.VISIBLE,
        importance=0.7,
        confidence=1.0,
        source=SourceType.CONVERSATION,
        owner=IdentityCode.MISHA,
        known_by=[IdentityCode.MISHA, IdentityCode.MASHA],
        project_ids=[PROJECT_ID],
        source_episode_ids=[],
        supersedes_id=None,
        superseded_by=None,
        created_at=NOW - timedelta(days=10),
        updated_at=NOW - timedelta(days=10),
    )
    repository = _repository(tmp_path, facts=(old,))
    service = PassiveMemoryService(
        repository=repository,
        detector=PassiveMemoryCandidateDetector(_engine()),
        clock=lambda: NOW,
    )
    candidate = service.observe(
        _request("Я предпочитаю машины на автомате.")
    ).persisted_candidates[0]
    payload = PassiveCandidatePayload.model_validate(candidate.proposed_payload)

    assert payload.relation is ExistingMemoryRelation.POSSIBLE_UPDATE
    assert payload.related_memory_id == old.id
    with pytest.raises(CandidateConflictRequiresExplicitSupersession):
        service.approve(candidate.id)

    new = service.approve(candidate.id, supersede_existing=True)
    document = repository.read_document()
    assert document is not None
    old_after = next(item for item in document.facts if item.id == old.id)
    assert old_after.status is FactStatus.SUPERSEDED
    assert old_after.superseded_by == new.id
    assert new.supersedes_id == old.id


def test_same_rejected_evidence_is_not_reprocessed(tmp_path):
    repository = _repository(tmp_path)
    service = PassiveMemoryService(
        repository=repository,
        detector=PassiveMemoryCandidateDetector(_engine()),
        clock=lambda: NOW,
    )
    request = _request("Я обычно ложусь около полуночи.", message_id="same-evidence")
    first = service.observe(request).persisted_candidates[0]
    service.reject(first.id)

    repeated = service.observe(request)

    assert repeated.persisted_candidates == ()
    assert repeated.duplicate_candidate_ids == (first.id,)


def _isolated_root(tmp_path: Path) -> Path:
    root = tmp_path / "masha-home"
    shutil.copytree(PROJECT_ROOT / "identity", root / "identity")
    shutil.copytree(PROJECT_ROOT / "skills", root / "skills")
    repository = MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    repository.replace_document(_minimal_document(), action="test_setup")
    return root


def test_conversation_integration_creates_candidate_only_after_ordinary_model_turn(tmp_path):
    class CountingProvider(FakeProvider):
        calls = 0

        def generate(self, request):
            self.calls += 1
            return super().generate(request)

    root = _isolated_root(tmp_path)
    provider = CountingProvider(
        provider_id="ollama-local",
        response_text="Хорошо, это многое объясняет про твои привычки.",
    )
    application = build_masha_application(
        project_root=root,
        router=ModelRouter([provider]),
    )

    turn = application.send_message(
        "Я вообще чай всегда пью без сахара, уже много лет.",
        project_id=PROJECT_ID,
    )
    candidates = application.list_pending_memory_candidates()

    assert turn.assistant_message is not None
    assert turn.assistant_message.content == provider.response_text
    assert len(candidates) == 1
    assert candidates[0].candidate_type == "fact"
    assert "чай" in candidates[0].summary
    # One call writes the conversation response; the approved Presence layer
    # makes one additional local-only call to classify its expression cue.
    assert provider.calls == 2

    application.send_message(
        "Сейчас хочу бутерброд.",
        project_id=PROJECT_ID,
        conversation_id=turn.conversation_id,
    )
    request_dump = provider.last_request.model_dump_json()
    assert candidates[0].candidate_id not in request_dump
    assert candidates[0].candidate_id not in application.conversation(
        turn.conversation_id
    ).model_dump_json()
    assert provider.calls == 4

    application.send_message(
        "Маша, запомни, что я люблю какао",
        project_id=PROJECT_ID,
        conversation_id=turn.conversation_id,
    )
    assert len(application.list_pending_memory_candidates()) == 1
    # The explicit memory capability is application-owned and adds no model call.
    assert provider.calls == 4


def test_application_review_and_provenance_boundary(tmp_path):
    root = _isolated_root(tmp_path)
    application = build_masha_application(
        project_root=root,
        router=ModelRouter(
            [FakeProvider(provider_id="ollama-local", response_text="Поняла.")]
        ),
    )
    application.send_message(
        "Я предпочитаю машины на автомате.",
        project_id=PROJECT_ID,
    )
    pending = application.list_pending_memory_candidates()[0]

    resolution = application.approve_memory_candidate(pending.candidate_id)
    provenance = application.memory_provenance(resolution.result_memory_id)

    assert resolution.status == "approved"
    assert provenance.source == "conversation"
    assert provenance.project_id == PROJECT_ID
    assert provenance.reviewed_by == "misha"
    assert provenance.candidate_id == pending.candidate_id


def test_secret_is_rejected_before_candidate_persistence(tmp_path):
    repository = _repository(tmp_path)
    service = PassiveMemoryService(
        repository=repository,
        detector=PassiveMemoryCandidateDetector(_engine()),
        clock=lambda: NOW,
    )

    result = service.observe(_request("Мой пароль qwerty123"))

    assert result.persisted_candidates == ()
    document = repository.read_document()
    assert document is not None
    assert document.memory_candidates == []
    encoded_audit = json.dumps(repository.list_audit_events(), ensure_ascii=False)
    assert "qwerty123" not in encoded_audit


def test_detector_failure_is_optional_and_does_not_write_a_fake_candidate(tmp_path):
    class BrokenDetector(PassiveMemoryCandidateDetector):
        def detect(self, request):
            raise RuntimeError("synthetic detector failure")

    repository = _repository(tmp_path)
    service = PassiveMemoryService(
        repository=repository,
        detector=BrokenDetector(_engine()),
        clock=lambda: NOW,
    )

    result = service.observe_safely(_request("Я предпочитаю машины на автомате."))

    assert result.persisted_candidates == ()
    assert result.failure_reason == "RuntimeError"
    document = repository.read_document()
    assert document is not None
    assert document.memory_candidates == []
    event = repository.list_audit_events()[-1]
    assert event["action"] == "candidate_detection_failed"
    assert "synthetic detector failure" not in json.dumps(event, ensure_ascii=False)
