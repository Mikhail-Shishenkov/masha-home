from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from backend.connectors.google_calendar.config import (
    GOOGLE_CALENDAR_WRITE_SCOPE,
    GOOGLE_CALENDAR_WRITE_SECRET_REF,
    GoogleCalendarConfig,
    GoogleCalendarConfigStore,
)
from backend.connectors.google_calendar.delete import (
    CalendarDeleteReceiptStore,
    GoogleCalendarDeleter,
    GoogleCalendarDeleteConversationService,
)
from backend.connectors.google_calendar.reader import (
    GoogleCalendarHttpFailure,
    GoogleCalendarUnavailable,
)
from backend.connectors.google_calendar.update import (
    CalendarUpdateReceiptStore,
    GoogleCalendarUpdater,
)
from backend.conversation.memory_intent import MemoryProposalStore, ProposalStatus
from backend.secrets import InMemorySecretStore


HOME_TZ = ZoneInfo("Europe/Saratov")
NOW = datetime(2026, 8, 31, 12, tzinfo=HOME_TZ)


def _event():
    return {
        "id": "evt-delete-1",
        "summary": "встреча команды",
        "etag": '"v1"',
        "start": {"dateTime": "2026-09-01T12:00:00Z"},
        "end": {"dateTime": "2026-09-01T13:00:00Z"},
    }


class _Transport:
    def __init__(self):
        self.events = {"evt-delete-1": _event()}
        self.calls = []
        self.fail_after_delete = False
        self.fail_next_event_get = False

    def request(self, url, *, method="GET", headers=None, body=None):
        self.calls.append((url, method, headers or {}, body))
        if "oauth2.googleapis.com/token" in url:
            return {"access_token": "ACCESS"}
        if method == "GET" and "/events?" in url:
            return {"items": list(self.events.values())}
        if method == "GET" and "/events/" in url:
            if self.fail_next_event_get:
                self.fail_next_event_get = False
                raise GoogleCalendarUnavailable("event_get_unavailable")
            event_id = url.rsplit("/", 1)[-1]
            if event_id not in self.events:
                raise GoogleCalendarHttpFailure(404)
            return dict(self.events[event_id])
        if method == "DELETE":
            event_id = url.rsplit("/", 1)[-1]
            event = self.events.get(event_id)
            if event is None:
                raise GoogleCalendarHttpFailure(404)
            if (headers or {}).get("If-Match") != event["etag"]:
                raise GoogleCalendarHttpFailure(412)
            del self.events[event_id]
            if self.fail_after_delete:
                self.fail_after_delete = False
                raise GoogleCalendarUnavailable("lost_delete_response")
            return {}
        raise AssertionError((url, method))


def _service(tmp_path: Path):
    config_store = GoogleCalendarConfigStore(
        tmp_path / "local-data/config/google-calendar.json"
    )
    config = GoogleCalendarConfig(
        client_id="desktop-client-identifier",
        write_secret_ref=GOOGLE_CALENDAR_WRITE_SECRET_REF,
        write_requested_scope=GOOGLE_CALENDAR_WRITE_SCOPE,
    )
    config_store.save(config)
    secrets = InMemorySecretStore()
    secrets.put(config.client_secret_ref, "CLIENT_SECRET")
    secrets.put(config.secret_ref, "READ_REFRESH")
    secrets.put(config.write_secret_ref, "WRITE_REFRESH")
    transport = _Transport()
    updater = GoogleCalendarUpdater(
        config_store=config_store,
        secret_store=secrets,
        receipt_store=CalendarUpdateReceiptStore(
            tmp_path / "local-data/runtime/calendar-update.json"
        ),
        transport=transport,
    )
    deleter = GoogleCalendarDeleter(
        target_resolver=updater,
        receipt_store=CalendarDeleteReceiptStore(
            tmp_path / "local-data/runtime/calendar-delete.json"
        ),
    )
    service = GoogleCalendarDeleteConversationService(
        proposal_store=MemoryProposalStore(
            tmp_path / "local-data/runtime/memory-proposals.json"
        ),
        deleter=deleter,
    )
    return service, deleter, transport


def _delete_calls(transport):
    return [call for call in transport.calls if call[1] == "DELETE"]


def _prepare(service, conversation_id="delete-1"):
    return service.prepare_from_resolved_intent(
        subject="встреча команды",
        date="2026-09-01",
        time_value="16:00",
        conversation_id=conversation_id,
        now_local=NOW,
    )


def test_delete_requires_confirmation_and_reports_success_only_after_404_verify(tmp_path):
    service, deleter, transport = _service(tmp_path)

    preparation = _prepare(service)
    proposal = service.proposal_store.current_for_conversation("delete-1")

    assert preparation.response == (
        "Удалить «встреча команды» из Основного календаря 01.09, 16:00–17:00?"
    )
    assert proposal is not None and proposal.status is ProposalStatus.PENDING
    assert _delete_calls(transport) == []
    assert deleter.receipt_store.get(proposal.record_payload["operation_id"]).status == "proposed"

    response = service.resolve("да", conversation_id="delete-1")
    repeated = deleter.delete_and_verify(
        deleter.receipt_store.get(proposal.record_payload["operation_id"]).operation
    )

    assert response == "Готово: «встреча команды» удалено из Основного календаря."
    assert len(_delete_calls(transport)) == 1
    assert repeated[0] == "verified"
    assert len(_delete_calls(transport)) == 1


def test_lost_delete_response_reconciles_same_event_without_second_delete(tmp_path):
    service, deleter, transport = _service(tmp_path)
    _prepare(service, "delete-uncertain")
    proposal = service.proposal_store.current_for_conversation("delete-uncertain")
    operation = deleter.receipt_store.get(
        proposal.record_payload["operation_id"]
    ).operation
    transport.fail_after_delete = True

    first_status, first = deleter.delete_and_verify(operation)
    second_status, second = deleter.delete_and_verify(operation)

    assert first_status == "deleted_unverified"
    assert first.status == "deleted_unverified"
    assert second_status == "verified" and second.verified_at is not None
    assert first.operation.operation_id == second.operation.operation_id
    assert len(_delete_calls(transport)) == 1


def test_deferring_uncertain_delete_preserves_truth_instead_of_claiming_unchanged(
    tmp_path,
):
    service, deleter, transport = _service(tmp_path)
    _prepare(service, "delete-deferred")
    proposal = service.proposal_store.current_for_conversation("delete-deferred")
    transport.fail_after_delete = True

    first = service.resolve("да", conversation_id="delete-deferred")
    deferred = service.resolve("не сейчас", conversation_id="delete-deferred")
    receipt = deleter.receipt_store.get(
        proposal.record_payload["operation_id"]
    )

    assert "могло примениться" in first
    assert "могло уже примениться" in deferred
    assert "оставляю" not in deferred
    assert receipt.status == "deleted_unverified"
    assert service.proposal_store.get(proposal.id).status is ProposalStatus.CANCELLED
    assert len(_delete_calls(transport)) == 1


def test_failure_before_delete_dispatch_is_truthful_and_retry_creates_one_delete(
    tmp_path,
):
    service, deleter, transport = _service(tmp_path)
    _prepare(service, "delete-preflight-failure")
    proposal = service.proposal_store.current_for_conversation(
        "delete-preflight-failure"
    )
    transport.fail_next_event_get = True

    first = service.resolve("да", conversation_id="delete-preflight-failure")
    receipt = deleter.receipt_store.get(
        proposal.record_payload["operation_id"]
    )

    assert "могло" not in first
    assert receipt.status == "failed"
    assert receipt.dispatch_started_at is None
    assert _delete_calls(transport) == []

    second = service.resolve("да", conversation_id="delete-preflight-failure")
    receipt = deleter.receipt_store.get(
        proposal.record_payload["operation_id"]
    )
    assert second.startswith("Готово:")
    assert receipt.status == "verified"
    assert receipt.dispatch_started_at is not None
    assert len(_delete_calls(transport)) == 1


def test_changed_target_conflicts_before_delete_and_rejection_never_mutates(tmp_path):
    service, deleter, transport = _service(tmp_path)
    _prepare(service, "delete-conflict")
    proposal = service.proposal_store.current_for_conversation("delete-conflict")
    operation = deleter.receipt_store.get(
        proposal.record_payload["operation_id"]
    ).operation
    transport.events[operation.provider_event_id]["etag"] = '"v2"'

    status, receipt = deleter.delete_and_verify(operation)

    assert status == "conflict" and receipt.status == "conflict"
    assert _delete_calls(transport) == []
    response = service.resolve("да", conversation_id="delete-conflict")
    assert "изменилось" in response
    assert service.proposal_store.get(proposal.id).status is ProposalStatus.CANCELLED

    service2, _, transport2 = _service(tmp_path / "reject")
    _prepare(service2, "delete-reject")
    response = service2.resolve("не сейчас", conversation_id="delete-reject")
    assert response == "Хорошо, событие оставляю в календаре."
    assert _delete_calls(transport2) == []
