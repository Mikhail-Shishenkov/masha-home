from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfoNotFoundError

import pytest

from backend.conversation.context_compiler import ConversationContextCompiler
from backend.conversation.conversation_models import ConversationMessageOrigin
from backend.conversation.conversation_service import ConversationService
from backend.conversation.conversation_store import ConversationStore
from backend.conversation.temporal_consistency import enforce_temporal_consistency
from backend.identity.identity_kernel import IdentityKernel
from backend.identity.identity_store import IdentityStore
from backend.llm.fake_provider import FakeProvider
from backend.llm.model_models import ModelMessage
from backend.llm.model_router import ModelRouter
from backend.memory.memory_retriever import MemoryRetriever
from backend.memory.memory_store import MemoryStore
from backend.memory.working_memory import WorkingMemory
from backend.temporal.conversation_grounding import GreetingKind
from backend.temporal.temporal_engine import Daypart, FixedClock, TemporalEngine
from backend.temporal.timezone_provider import (
    HomeTimeZoneConfig,
    HomeTimeZoneProvider,
    HomeTimeZoneResolutionError,
    HomeTimeZoneStore,
)


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ID = "project_masha_home"


def _missing_zone(_name: str):
    raise ZoneInfoNotFoundError


def _saratov_engine(local: datetime) -> tuple[FixedClock, TemporalEngine]:
    assert local.utcoffset() == timedelta(hours=4)
    clock = FixedClock(local)
    provider = HomeTimeZoneProvider(
        HomeTimeZoneConfig(
            timezone="Europe/Saratov",
            fallback_utc_offset_minutes=240,
        ),
        zone_loader=_missing_zone,
    )
    return clock, TemporalEngine(clock, provider)


def _service(tmp_path, clock: FixedClock, engine: TemporalEngine, response="grounded"):
    provider = FakeProvider(provider_id="ollama-local", response_text=response)
    service = ConversationService(
        identity_kernel=IdentityKernel(
            IdentityStore(ROOT / "identity" / "masha.identity.json")
        ),
        memory_retriever=MemoryRetriever(
            MemoryStore(ROOT / "tests" / "fixtures" / "test_memory.json")
        ),
        working_memory=WorkingMemory(),
        router=ModelRouter([provider]),
        history=ConversationStore(
            tmp_path / "history.json",
            clock=clock.now_utc,
        ),
        temporal_engine=engine,
    )
    return service, provider


def test_home_timezone_store_defaults_to_saratov_with_portable_explicit_fallback(
    tmp_path,
):
    store = HomeTimeZoneStore(tmp_path / "home-timezone.json")
    configured = store.load()
    resolved = HomeTimeZoneProvider(
        configured,
        zone_loader=_missing_zone,
    ).resolve()

    assert configured.timezone == "Europe/Saratov"
    assert configured.fallback_utc_offset_minutes == 240
    assert resolved.name == "Europe/Saratov"
    assert resolved.resolution == "configured_offset_fallback"
    assert datetime(2026, 8, 13, tzinfo=timezone.utc).astimezone(
        resolved.tzinfo
    ).utcoffset() == timedelta(hours=4)
    assert json.loads(store.path.read_text(encoding="utf-8"))["timezone"] == (
        "Europe/Saratov"
    )


def test_unavailable_named_zone_without_offset_fails_explicitly():
    provider = HomeTimeZoneProvider(
        HomeTimeZoneConfig(
            timezone="Europe/Unavailable",
            fallback_utc_offset_minutes=None,
        ),
        zone_loader=_missing_zone,
    )

    with pytest.raises(HomeTimeZoneResolutionError, match="Europe/Unavailable"):
        provider.resolve()


@pytest.mark.parametrize(
    ("hour", "message", "expected_daypart", "expected_greeting", "expected_match"),
    [
        (7, "доброе утро", Daypart.MORNING, GreetingKind.MORNING, True),
        (23, "доброе утро)))", Daypart.LATE_EVENING, GreetingKind.MORNING, False),
    ],
)
def test_greeting_is_structured_social_signal_without_rewriting_clock(
    hour,
    message,
    expected_daypart,
    expected_greeting,
    expected_match,
):
    local = datetime(2026, 8, 13, hour, 51, tzinfo=timezone(timedelta(hours=4)))
    _, engine = _saratov_engine(local)

    context = engine.context(None, user_message=message)

    assert context.current_local_time.hour == hour
    assert context.daypart is expected_daypart
    assert context.greeting_kind is expected_greeting
    assert context.greeting_matches_current_daypart is expected_match


@pytest.mark.parametrize(
    ("hour", "expected"),
    [
        (0, Daypart.NIGHT),
        (5, Daypart.NIGHT),
        (6, Daypart.MORNING),
        (11, Daypart.MORNING),
        (12, Daypart.DAY),
        (17, Daypart.DAY),
        (18, Daypart.EVENING),
        (21, Daypart.EVENING),
        (22, Daypart.LATE_EVENING),
        (23, Daypart.LATE_EVENING),
    ],
)
def test_daypart_boundaries_are_deterministic(hour, expected):
    local = datetime(2026, 8, 13, hour, 0, tzinfo=timezone(timedelta(hours=4)))
    _, engine = _saratov_engine(local)

    assert engine.context(None).daypart is expected


def test_production_sequence_keeps_same_day_and_one_minute_relation(tmp_path):
    local = datetime(2026, 8, 13, 23, 50, tzinfo=timezone(timedelta(hours=4)))
    clock, engine = _saratov_engine(local)
    service, provider = _service(tmp_path, clock, engine)

    conversation_id, time_response = service.send(
        "а сколько сейчас времени?",
        project_id=PROJECT_ID,
    )
    assert time_response == "Сейчас 23:50."
    assert provider.last_request is None
    assert service.history.messages(conversation_id)[-1].origin is (
        ConversationMessageOrigin.APPLICATION
    )

    clock.set(local + timedelta(minutes=1))
    _, response = service.send(
        "доброе утро)))",
        project_id=PROJECT_ID,
        conversation_id=conversation_id,
    )
    context = provider.last_request.private_context["temporal_context"]

    assert response == "grounded"
    assert context["current_local_time"].startswith("2026-08-13T23:51:00")
    assert context["same_local_date_as_last_interaction"] is True
    assert context["local_day_delta_from_last_interaction"] == 0
    assert context["previous_turn_relation"] == "same_local_day"
    assert context["absence_duration_seconds"] == 60
    assert context["greeting_kind"] == "morning"
    assert context["greeting_matches_current_daypart"] is False
    assert "sleep" not in context and "wake" not in context and "rest" not in context


def test_midnight_crossing_preserves_calendar_delta_and_short_elapsed_time():
    previous_local = datetime(
        2026, 8, 13, 23, 58, tzinfo=timezone(timedelta(hours=4))
    )
    current_local = previous_local + timedelta(minutes=5)
    _, engine = _saratov_engine(current_local)

    context = engine.context(previous_local)

    assert context.local_date.isoformat() == "2026-08-14"
    assert context.last_interaction_local_date.isoformat() == "2026-08-13"
    assert context.local_day_delta_from_last_interaction == 1
    assert context.previous_turn_relation.value == "previous_local_day"
    assert context.absence_duration_seconds == 300
    assert context.same_local_date_as_last_interaction is False


def test_long_absence_is_elapsed_only_and_never_sleep_state():
    current_local = datetime(
        2026, 8, 14, 8, 0, tzinfo=timezone(timedelta(hours=4))
    )
    _, engine = _saratov_engine(current_local)
    context = engine.context(current_local - timedelta(hours=8))
    data = context.model_dump(mode="json")

    assert context.absence_duration_seconds == 8 * 60 * 60
    assert not any(key in data for key in ("slept", "woke", "rested", "sleep_state"))


def test_exact_date_weekday_and_daypart_questions_are_application_readouts(tmp_path):
    local = datetime(2026, 8, 13, 23, 0, tzinfo=timezone(timedelta(hours=4)))
    clock, engine = _saratov_engine(local)
    service, provider = _service(tmp_path, clock, engine)

    conversation_id, date_response = service.send(
        "какое сегодня число?", project_id=PROJECT_ID
    )
    _, weekday_response = service.send(
        "какой сегодня день недели?",
        project_id=PROJECT_ID,
        conversation_id=conversation_id,
    )
    _, daypart_response = service.send(
        "сейчас утро?",
        project_id=PROJECT_ID,
        conversation_id=conversation_id,
    )

    assert date_response == "Сегодня 13 августа 2026 года."
    assert weekday_response == "Сегодня четверг."
    assert daypart_response == "Нет, сейчас поздний вечер."
    assert provider.last_request is None
    assert all(
        message.origin is ConversationMessageOrigin.APPLICATION
        for message in service.history.messages(conversation_id)
        if message.role.value == "assistant"
    )


def test_saratov_conversation_and_due_parser_share_one_clock_and_timezone():
    local = datetime(2026, 8, 13, 23, 50, tzinfo=timezone(timedelta(hours=4)))
    _, engine = _saratov_engine(local)

    context = engine.context(None)
    relative = engine.parse_due("через 2 минуты")
    tomorrow = engine.parse_due("завтра в 10:30")

    assert context.timezone == relative.timezone == tomorrow.timezone == "Europe/Saratov"
    assert relative.resolved_local == local + timedelta(minutes=2)
    assert relative.resolved_utc == datetime(
        2026, 8, 13, 19, 52, tzinfo=timezone.utc
    )
    assert tomorrow.resolved_local.isoformat().startswith("2026-08-14T10:30:00+04:00")
    assert tomorrow.resolved_utc == datetime(
        2026, 8, 14, 6, 30, tzinfo=timezone.utc
    )


def test_compiler_exposes_compact_authoritative_temporal_contract():
    local = datetime(2026, 8, 13, 23, 51, tzinfo=timezone(timedelta(hours=4)))
    _, engine = _saratov_engine(local)
    context = engine.context(
        local - timedelta(minutes=1),
        user_message="доброе утро)))",
    )
    request = ConversationContextCompiler().compile(
        messages=(ModelMessage(role="user", content="доброе утро)))"),),
        identity_context=IdentityKernel(
            IdentityStore(ROOT / "identity" / "masha.identity.json")
        ).build_context(),
        working_memory=[],
        temporal_context=context,
    )

    private = request.private_context
    assert private["temporal_context"]["daypart"] == "late_evening"
    assert private["temporal_context"]["greeting_kind"] == "morning"
    assert private["temporal_contract"] == {
        "authority": "temporal_context_is_application_owned",
        "visibility": "internal_do_not_quote_or_explain",
        "greetings": "social_signal_not_clock_evidence",
        "absence": "elapsed_without_interaction_not_sleep_wake_or_rest_evidence",
        "recent_interaction": "same_local_date_must_not_be_called_yesterday",
        "calendar_transition": "local_day_delta_and_elapsed_time_are_both_true",
        "relative_language": "interpret_against_home_timezone_and_local_date",
    }


def test_narrow_guard_replaces_proven_mismatch_and_internal_contract_leak():
    local = datetime(2026, 8, 13, 23, 51, tzinfo=timezone(timedelta(hours=4)))
    _, engine = _saratov_engine(local)
    context = engine.context(
        local - timedelta(minutes=1),
        user_message="доброе утро)))",
    )

    guarded = enforce_temporal_consistency(
        "Доброе утро! Солнце уже встало. Примечание: приветствие — социальный сигнал.",
        user_message="доброе утро)))",
        context=context,
    )

    assert guarded == "Доброе утро в 23:51? 😄 Решил начать завтра заранее?"


def test_conversation_service_applies_narrow_guard_after_model_generation(tmp_path):
    local = datetime(2026, 8, 13, 23, 51, tzinfo=timezone(timedelta(hours=4)))
    clock, engine = _saratov_engine(local)
    service, provider = _service(
        tmp_path,
        clock,
        engine,
        response=(
            "Доброе утро! Солнце уже встало. "
            "Примечание: приветствие — социальный сигнал."
        ),
    )

    _, response = service.send("доброе утро)))", project_id=PROJECT_ID)

    assert provider.last_request is not None
    assert response == "Доброе утро в 23:51? 😄 Решил начать завтра заранее?"


def test_narrow_guard_preserves_valid_future_hypothesis_and_explicit_waking():
    local = datetime(2026, 8, 13, 23, 51, tzinfo=timezone(timedelta(hours=4)))
    _, engine = _saratov_engine(local)
    context = engine.context(
        local - timedelta(minutes=1),
        user_message="я только что проснулся",
    )
    valid = "Если завтра утром будет солнце, можно выйти. Ты только что проснулся — как себя чувствуешь?"

    assert enforce_temporal_consistency(
        valid,
        user_message="я только что проснулся",
        context=context,
    ) == valid


def test_narrow_guard_rejects_recent_same_day_yesterday_and_unsupported_sleep():
    local = datetime(2026, 8, 13, 23, 51, tzinfo=timezone(timedelta(hours=4)))
    _, engine = _saratov_engine(local)
    context = engine.context(local - timedelta(minutes=1), user_message="привет")

    yesterday = enforce_temporal_consistency(
        "В нашем вчерашнем разговоре всё было иначе.",
        user_message="привет",
        context=context,
    )
    sleep = enforce_temporal_consistency(
        "Ты снова проснулся и теперь с новыми силами.",
        user_message="привет",
        context=context,
    )

    assert "около 1 мин. назад" in yesterday
    assert "ничего не говорит о сне" in sleep
