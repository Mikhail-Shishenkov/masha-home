from datetime import datetime, timezone
from pathlib import Path

from backend.connectors.google_calendar.config import (
    GOOGLE_CALENDAR_WRITE_SCOPE, GOOGLE_CALENDAR_WRITE_SECRET_REF,
    GoogleCalendarConfig, GoogleCalendarConfigStore,
)
from backend.connectors.google_calendar.create_service import GoogleCalendarCreateConversationService
from backend.connectors.google_calendar.intent import calendar_create_intent
from backend.connectors.google_calendar.writer import (
    CalendarCreateOperation, CalendarCreateReceiptStore, GoogleCalendarWriter,
)
from backend.conversation.memory_intent import MemoryProposalStore
from backend.external_observation.policy import InternetAccessMode, InternetAccessPolicy, InternetAccessPolicyStore
from backend.runtime.safety import AutonomySafetyService, AutonomySafetyStore
from backend.secrets import InMemorySecretStore


class _Transport:
    def __init__(self):
        self.calls = []
        self.event = None

    def request(self, url, *, method="GET", headers=None, body=None):
        self.calls.append((url, method, headers or {}, body))
        if "oauth2.googleapis.com/token" in url:
            return {"access_token": "ACCESS_TOKEN"}
        if method == "POST":
            import json
            self.event = json.loads(body)
            return self.event
        if self.event is None:
            return {}
        return {
            "id": self.event["id"], "summary": self.event["summary"],
            "start": {"dateTime": self.event["start"]["dateTime"]},
            "end": {"dateTime": self.event["end"]["dateTime"]},
        }


def _service(tmp_path: Path):
    config_store = GoogleCalendarConfigStore(tmp_path / "local-data/config/google-calendar.json")
    config = GoogleCalendarConfig(
        client_id="desktop-client-identifier", write_secret_ref=GOOGLE_CALENDAR_WRITE_SECRET_REF,
        write_requested_scope=GOOGLE_CALENDAR_WRITE_SCOPE,
    )
    config_store.save(config)
    secrets = InMemorySecretStore()
    secrets.put(config.client_secret_ref, "CLIENT_SECRET_MUST_NOT_ESCAPE")
    secrets.put(config.write_secret_ref, "WRITE_REFRESH_MUST_NOT_ESCAPE")
    transport = _Transport()
    writer = GoogleCalendarWriter(
        config_store=config_store, secret_store=secrets,
        receipt_store=CalendarCreateReceiptStore(tmp_path / "local-data/runtime/google-calendar-create-receipts.json"),
        transport=transport,
    )
    return GoogleCalendarCreateConversationService(
        proposal_store=MemoryProposalStore(tmp_path / "local-data/memory-proposals.json"), writer=writer,
    ), transport, writer


def test_create_intent_parses_narrow_complete_request():
    now = datetime(2026, 8, 25, 12, tzinfo=timezone.utc)
    intent = calendar_create_intent("Маша, поставь занятие по AI завтра в 19:00 на час", now)
    assert intent is not None
    assert (intent.title, intent.start.isoformat(), intent.end.isoformat()) == (
        "занятие по AI", "2026-08-26T19:00:00+00:00", "2026-08-26T20:00:00+00:00",
    )


def test_create_requires_human_confirmation_then_verifies_once(tmp_path: Path):
    service, transport, writer = _service(tmp_path)
    now = datetime(2026, 8, 25, 12, tzinfo=timezone.utc)
    proposal_text = service.propose("Маша, поставь занятие по AI завтра в 19:00 на час", conversation_id="c1", now_local=now)
    assert "Поставить" in proposal_text and transport.calls == []
    pending = service.proposal_store.current_for_conversation("c1")
    response = service.resolve("да", conversation_id="c1")
    assert "Готово" in response
    assert [call[1] for call in transport.calls] == ["POST", "POST", "GET"]
    assert service.proposal_store.get(pending.id).status.value == "confirmed"
    assert writer.receipt_store.get(pending.record_payload["operation_id"]).status == "verified"
    assert "WRITE_REFRESH_MUST_NOT_ESCAPE" not in writer.receipt_store.path.read_text(encoding="utf-8")


def test_reject_and_policy_safety_perform_zero_mutations(tmp_path: Path):
    service, transport, writer = _service(tmp_path)
    now = datetime(2026, 8, 25, 12, tzinfo=timezone.utc)
    service.propose("поставь встречу завтра в 19:00 на час", conversation_id="c1", now_local=now)
    assert service.resolve("нет", conversation_id="c1") == "Хорошо, ничего в календаре не меняю."
    assert transport.calls == []
    service.propose("поставь встречу завтра в 19:00 на час", conversation_id="c2", now_local=now)
    policy = InternetAccessPolicyStore(tmp_path / "local-data/config/internet-access.json")
    policy.save(InternetAccessPolicy(mode=InternetAccessMode.OFF))
    writer.policy_store = policy
    assert "внешние действия" in service.resolve("подтверждаю", conversation_id="c2")
    assert transport.calls == []
    policy.save(InternetAccessPolicy())
    safety = AutonomySafetyStore(tmp_path / "local-data/config/autonomy-safety.json")
    AutonomySafetyService(store=safety).engage()
    writer.safety_store = safety
    service.propose("поставь встречу завтра в 19:00 на час", conversation_id="c3", now_local=now)
    assert "внешние действия" in service.resolve("да", conversation_id="c3")
    assert transport.calls == []


def test_same_operation_receipt_never_posts_twice(tmp_path: Path):
    _, transport, writer = _service(tmp_path)
    operation = CalendarCreateOperation(
        operation_id="00000000-0000-4000-8000-000000000001", title="Встреча",
        start=datetime(2026, 8, 26, 19, tzinfo=timezone.utc),
        end=datetime(2026, 8, 26, 20, tzinfo=timezone.utc), home_timezone="UTC",
    )
    assert writer.create_and_verify(operation)[0] == "verified"
    assert writer.create_and_verify(operation)[0] == "verified"
    assert [call[1] for call in transport.calls].count("POST") == 2  # token + one event POST


def test_altered_pending_payload_fails_closed_before_provider_call(tmp_path: Path):
    service, transport, _ = _service(tmp_path)
    now = datetime(2026, 8, 25, 12, tzinfo=timezone.utc)
    service.propose("поставь встречу завтра в 19:00 на час", conversation_id="c1", now_local=now)
    pending = service.proposal_store.current_for_conversation("c1")
    # Simulate a damaged/stale local proposal: the typed boundary must reject
    # it before a token or Calendar call can happen.
    service.proposal_store._proposals[pending.id] = pending.model_copy(update={"record_payload": {"title": "подмена"}})
    assert "ничего в календаре не меняла" in service.resolve("да", conversation_id="c1")
    assert transport.calls == []
