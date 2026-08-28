from datetime import datetime, timezone
from pathlib import Path

from backend.conversation.context_compiler import ConversationContextCompiler
from backend.identity.identity_kernel import IdentityKernel
from backend.identity.identity_store import IdentityStore
from backend.llm.model_models import ModelMessage


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_compiler_preserves_memory_type_semantics_and_bounded_context():
    working_memory = [
        {"type": "fact", "data": {"id": "fact_1", "subject": "misha", "key": "city", "value": "Moscow"}},
        {"type": "decision", "data": {"id": "decision_1", "title": "Storage", "decision": "Use JSON", "status": "active"}},
        {"type": "commitment", "data": {"id": "commitment_1", "text": "Check tests", "status": "open"}},
        {"type": "episode", "data": {"id": "episode_1", "title": "Started", "summary": "Conversation started", "occurred_at": "2026-08-10T00:00:00+00:00"}},
    ]
    compiler = ConversationContextCompiler(lambda: datetime(2026, 8, 11, 12, 30, tzinfo=timezone.utc))

    request = compiler.compile(
        messages=(ModelMessage(role="user", content="Что мы помним?"),),
        identity_context=IdentityKernel(IdentityStore(PROJECT_ROOT / "identity" / "masha.identity.json")).build_context(),
        working_memory=working_memory,
    )

    records = request.private_context["memory_context"]
    assert len(records) <= 4
    assert {record["category"] for record in records} == {"факт", "решение", "дело", "эпизод"}
    assert "Use JSON" in next(record for record in records if record["category"] == "решение")["content"]
    assert "Check tests" in next(record for record in records if record["category"] == "дело")["content"]
    assert all("id" not in record and "record_type" not in record for record in records)
    assert request.private_context["current_local_time"] == "2026-08-11T12:30:00+00:00"
    assert "не говори «я запомнила»" in request.private_context["behavioral_contract"]


def test_behavioral_contract_requires_feminine_concise_non_technical_voice():
    contract = ConversationContextCompiler().compile(
        messages=(ModelMessage(role="user", content="Почему кошки любят коробки?"),),
        identity_context=IdentityKernel(
            IdentityStore(PROJECT_ROOT / "identity" / "masha.identity.json")
        ).build_context(),
        working_memory=[],
    ).private_context

    assert contract["question_scope"] == "general_knowledge_or_conversation"
    assert "женского лица" in contract["behavioral_contract"]
    assert "0–2" in contract["behavioral_contract"]
    assert "1–4 компактных абзаца" in contract["behavioral_contract"]
    assert "не означает незнание предмета" in contract["behavioral_contract"]
    assert "реальное физическое касание" in contract["behavioral_contract"]

def test_special_evening_changes_conversation_rhythm_without_becoming_memory():
    compiler = ConversationContextCompiler(
        lambda: datetime(2026, 8, 20, 1, 12, tzinfo=timezone.utc)
    )
    identity = IdentityKernel(
        IdentityStore(PROJECT_ROOT / "identity" / "masha.identity.json")
    ).build_context()

    request = compiler.compile(
        messages=(ModelMessage(role="user", content="Маша, какая красивая ночь."),),
        identity_context=identity,
        working_memory=[],
        home_moment="special_evening",
    )

    private = request.private_context
    assert private["home_moment"] == "special_evening"
    assert "РЕЖИМ «ВДВОЁМ»" in private["home_moment_contract"]
    assert "Не устраивай интервью" in private["home_moment_contract"]
    assert "человеческий смысл" in private["home_moment_contract"]
    assert private["memory_context"] == []

def test_active_continuity_is_structured_background_not_synthetic_user_text():
    compiler = ConversationContextCompiler(
        lambda: datetime(2026, 8, 20, 1, 30, tzinfo=timezone.utc)
    )
    identity = IdentityKernel(
        IdentityStore(PROJECT_ROOT / "identity" / "masha.identity.json")
    ).build_context()

    request = compiler.compile(
        messages=(ModelMessage(role="user", content="Я бы начал с места у воды."),),
        identity_context=identity,
        working_memory=[],
        active_continuity={
            "summary": "Обсудить нашу будущую поездку к морю",
            "reason_to_return": "Вернуться к выбору места и времени",
            "topic": "поездка к морю",
        },
    )

    assert request.messages[-1].content == "Я бы начал с места у воды."
    assert request.private_context["active_continuity"]["summary"] == (
        "Обсудить нашу будущую поездку к морю"
    )
    assert "тихий фон" in request.private_context["active_continuity_contract"]



def test_special_evening_boundary_pause_is_high_priority_session_context_not_memory():
    compiler = ConversationContextCompiler(
        lambda: datetime(2026, 8, 28, 20, 15, tzinfo=timezone.utc)
    )
    identity = IdentityKernel(
        IdentityStore(PROJECT_ROOT / "identity" / "masha.identity.json")
    ).build_context()

    request = compiler.compile(
        messages=(ModelMessage(role="user", content="Стоп"),),
        identity_context=identity,
        working_memory=[],
        home_moment="special_evening",
        home_proximity="near",
        home_boundary_pause=True,
    )

    assert request.private_context["special_evening_boundary_pause"] is True
    assert request.private_context["memory_context"] == []
    assert request.messages[0].role.value == "system"
    assert "ПАУЗА БЛИЗОСТИ «ВДВОЁМ»" in request.messages[0].content
    assert "Следующая нейтральная реплика НЕ снимает эту паузу" in request.messages[0].content
