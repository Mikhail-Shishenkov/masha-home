from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from backend.connectors.yandex_mail.models import MailOutcome
from backend.connectors.yandex_mail.models import MailMessageSummary, MailMessageContent
from backend.connectors.presented_read_sets import PresentedReadSetRegistry
from backend.connectors.yandex_mail.service import YandexMailConversationService
from backend.conversation.memory_intent import MemoryIntentHandler, MemoryProposalStore
from backend.temporal.temporal_engine import TemporalEngine
from backend.temporal.timezone_provider import HomeTimeZoneConfig, HomeTimeZoneProvider
from backend.conversation.response_contract import render_model_response, UNRECEIPTED_MUTATION_RESPONSE


@pytest.mark.parametrize("zone, expected", [("Europe/Saratov", "09:00"), ("Europe/Moscow", "08:00")])
def test_commitment_preview_uses_home_zone_without_changing_deadline(tmp_path, zone, expected):
    handler = MemoryIntentHandler(
        proposal_store=MemoryProposalStore(tmp_path / "proposals.json"),
        confirmed_memory=Mock(),
        temporal_engine=TemporalEngine(timezone_provider=HomeTimeZoneProvider(HomeTimeZoneConfig(timezone=zone))),
    )
    due = datetime(2026, 9, 14, 5, tzinfo=timezone.utc)
    record = handler._make_record("commitment", "Позвонить маме", "home", due)
    assert f"14.09.2026 {expected}" in handler._proposal_text(None, record)
    assert record.due_at == due


@pytest.mark.parametrize("view", ["unread", "recent", "today", "important"])
def test_mail_listing_never_resolves_an_item_from_previous_results(view):
    reader = Mock()
    reader.search.return_value = MailOutcome("search_completed")
    service = YandexMailConversationService(reader=reader)
    service._contextual_read = Mock(side_effect=AssertionError("listing must not read an item"))
    outcome = service.observe_resolved(
        conversation_id="home", original_utterance="Есть новая почта?",
        view=view, target="новые письма",
    )
    assert outcome.status == "search_completed"
    reader.search.assert_called_once_with(view, None)
    reader.read.assert_not_called()


def test_mail_unresolved_single_target_still_requires_clarification():
    reader = Mock()
    service = YandexMailConversationService(reader=reader)
    outcome = service.observe_resolved(
        conversation_id="home", original_utterance="Прочитай письмо", target="письмо",
    )
    assert outcome.status == "clarification_required"
    reader.search.assert_not_called()
    reader.read.assert_not_called()


@pytest.mark.parametrize("view, kind", [("мою почту", "unread"), ("за сегодня", "today"), ("последние письма", "recent"), ("посмотри", "unread")])
def test_grounded_human_mailbox_view_keeps_temporal_words(view, kind):
    reader = Mock()
    reader.search.return_value = MailOutcome("no_messages")
    service = YandexMailConversationService(reader=reader)
    service.observe_resolved(conversation_id="home", original_utterance=view, view=view)
    reader.search.assert_called_once_with(kind, None)


def test_empty_unread_then_read_subject_searches_real_mail_not_old_list():
    registry = PresentedReadSetRegistry()
    letter = MailMessageSummary("yandex", "PRIVATE", "185 историй вдохновления", "Sender", None, 100, False)
    reader = Mock()
    reader.search.side_effect = [MailOutcome("no_unread"), MailOutcome("search_completed", (letter,))]
    reader.read.return_value = MailOutcome("read_completed", content=MailMessageContent(letter, "Body"))
    service = YandexMailConversationService(reader=reader, presented_read_sets=registry)
    registry.present("home", "yandex_mail", (letter,), entity_kind="письмо")
    assert service.observe_resolved(conversation_id="home", original_utterance="Посмотри мою почту").status == "no_unread"
    assert registry.items_for("home", "yandex_mail") == ()
    assert service.observe_resolved(conversation_id="home", original_utterance="первое", target="первое").status == "clarification_required"
    result = service.observe_resolved(
        conversation_id="home", original_utterance="Прочитай тогда пожалуйста письмо 185 историй вдохновления",
        target=letter.subject, view="unread",
    )
    assert result.status == "read_completed"
    assert reader.search.call_args_list == [(("unread", None),), (("topic", letter.subject),)]
    reader.read.assert_called_once_with(letter)
    assert registry.current_context("home").focused_position == 1


@pytest.mark.parametrize("count", [0, 2])
def test_subject_search_does_not_arbitrarily_read_multiple_or_missing_matches(count):
    reader = Mock()
    rows = tuple(MailMessageSummary("yandex", str(i), "Report", "Sender", None, 1, False) for i in range(count))
    reader.search.return_value = MailOutcome("search_completed" if rows else "no_messages", rows)
    service = YandexMailConversationService(reader=reader, presented_read_sets=PresentedReadSetRegistry())
    result = service.observe_resolved(conversation_id="home", original_utterance="Прочитай Report", target="Report")
    assert result.messages == rows
    reader.read.assert_not_called()


def test_observed_schedule_is_not_execution_authority():
    readout = "Событие «Звонок маме» запланировано на завтра."
    evidence = {"observed_calendar_titles": ("Звонок маме",)}
    assert render_model_response(readout, **evidence) == readout
    assert render_model_response(readout) == UNRECEIPTED_MUTATION_RESPONSE
    for claim in (
        "Я создала событие «Звонок маме».",
        "Я перенесла событие «Звонок маме».",
        readout + " Событие «Визит к врачу» запланировано на завтра.",
    ):
        assert render_model_response(claim, **evidence) == UNRECEIPTED_MUTATION_RESPONSE
