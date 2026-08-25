import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from backend.backup.recovery_journal import RecoveryJournal
from backend.backup.recovery_models import RecoveryPhase, RecoveryState, RestoreMode
from backend.connectors.google_calendar.config import (
    GOOGLE_CALENDAR_WRITE_SCOPE, GOOGLE_CALENDAR_WRITE_SECRET_REF,
    GoogleCalendarConfig, GoogleCalendarConfigStore,
)
from backend.connectors.google_calendar.reader import GoogleCalendarHttpFailure, GoogleCalendarUnavailable
from backend.connectors.google_calendar.update import (
    CalendarUpdateReceipt, CalendarUpdateReceiptStore, GoogleCalendarUpdateConversationService,
    GoogleCalendarUpdater, calendar_update_intent,
)
from backend.conversation.memory_intent import MemoryProposalStore
from backend.external_observation.policy import InternetAccessMode, InternetAccessPolicy, InternetAccessPolicyStore
from backend.runtime.safety import AutonomySafetyService, AutonomySafetyStore
from backend.secrets import InMemorySecretStore


HOME_TZ = ZoneInfo("Europe/Saratov")
NOW = datetime(2026, 8, 25, 12, tzinfo=HOME_TZ)


class _Transport:
    def __init__(self, events=None):
        self.calls = []
        self.events = {item["id"]: dict(item) for item in (events or [])}
        self.next_patch_error = None
        self.fail_token_once = False
        self.fail_after_patch = False

    def request(self, url, *, method="GET", headers=None, body=None):
        self.calls.append((url, method, headers or {}, body))
        if "oauth2.googleapis.com/token" in url:
            if self.fail_token_once:
                self.fail_token_once = False
                raise GoogleCalendarUnavailable("token_unavailable")
            return {"access_token": "ACCESS_TOKEN"}
        if method == "GET" and "/events?" in url:
            return {"items": list(self.events.values())}
        if method == "GET" and "/events/" in url:
            event_id = url.rsplit("/", 1)[-1]
            if event_id not in self.events:
                raise GoogleCalendarHttpFailure(404)
            return dict(self.events[event_id])
        if method == "PATCH":
            if self.next_patch_error is not None:
                error, self.next_patch_error = self.next_patch_error, None
                if error.status_code == 412:
                    self.events[url.rsplit("/", 1)[-1]]["summary"] = "чужая правка"
                raise error
            event_id = url.rsplit("/", 1)[-1]
            event = self.events[event_id]
            if headers.get("If-Match") != event["etag"]:
                raise GoogleCalendarHttpFailure(412)
            patch = json.loads(body)
            event.update({key: value for key, value in patch.items() if key == "summary"})
            for key in ("start", "end"):
                if key in patch:
                    event[key] = patch[key]
            event["etag"] = '"v2"'
            if self.fail_after_patch:
                raise GoogleCalendarUnavailable("after_patch")
            return dict(event)
        raise AssertionError((url, method))


def _event(identifier="evt-1", title="занятие по AI", start="2026-08-26T15:00:00Z", end="2026-08-26T16:00:00Z", etag='"v1"'):
    return {"id": identifier, "summary": title, "etag": etag, "start": {"dateTime": start}, "end": {"dateTime": end}}


def _service(tmp_path: Path, transport=None):
    config_store = GoogleCalendarConfigStore(tmp_path / "local-data/config/google-calendar.json")
    config = GoogleCalendarConfig(client_id="desktop-client-identifier", write_secret_ref=GOOGLE_CALENDAR_WRITE_SECRET_REF, write_requested_scope=GOOGLE_CALENDAR_WRITE_SCOPE)
    config_store.save(config)
    secrets = InMemorySecretStore()
    secrets.put(config.client_secret_ref, "CLIENT_SECRET_MUST_NOT_ESCAPE")
    secrets.put(config.secret_ref, "READ_REFRESH_MUST_NOT_ESCAPE")
    secrets.put(config.write_secret_ref, "WRITE_REFRESH_MUST_NOT_ESCAPE")
    transport = transport or _Transport([_event()])
    updater = GoogleCalendarUpdater(
        config_store=config_store, secret_store=secrets,
        receipt_store=CalendarUpdateReceiptStore(tmp_path / "local-data/runtime/google-calendar-update-receipts.json"),
        transport=transport,
    )
    service = GoogleCalendarUpdateConversationService(
        proposal_store=MemoryProposalStore(tmp_path / "local-data/memory-proposals.json"), updater=updater,
    )
    return service, updater, transport, secrets


def _event_patches(transport):
    return [call for call in transport.calls if call[1] == "PATCH"]


def _recovery_state(phase: RecoveryPhase) -> RecoveryState:
    return RecoveryState(
        recovery_id="recovery-a2-0001", backup_id="backup-a2-0001",
        restore_mode=RestoreMode.REPLACE, phase=phase,
        created_at=NOW, updated_at=NOW,
    )


def test_canonical_move_resolves_real_event_home_time_and_confirms_once(tmp_path: Path):
    service, updater, transport, _ = _service(tmp_path)
    message = "Маш, перенеси занятие по AI завтра с 19:00 на 20:00."
    preview = service.propose(message, conversation_id="c1", now_local=NOW)
    pending = service.proposal_store.current_for_conversation("c1")
    operation = pending.record_payload
    assert preview == "Перенести «занятие по AI» в Основном календаре: 26.08, 19:00–20:00 → 20:00–21:00?"
    assert operation["provider_event_id"] == "evt-1"
    assert operation["desired"]["start"].endswith("20:00:00+04:00")
    assert sum(method == "GET" and url.endswith("/events/evt-1") for url, method, *_ in transport.calls) == 1
    assert _event_patches(transport) == []
    assert "Готово" in service.resolve("да", conversation_id="c1")
    assert len(_event_patches(transport)) == 1
    assert _event_patches(transport)[0][2]["If-Match"] == '"v1"'
    receipt = updater.receipt_store.get(operation["operation_id"])
    assert receipt.status == "verified"
    receipt_json = updater.receipt_store.path.read_text(encoding="utf-8")
    assert "WRITE_REFRESH_MUST_NOT_ESCAPE" not in receipt_json
    assert "READ_REFRESH_MUST_NOT_ESCAPE" not in receipt_json


def test_target_resolution_uses_read_grant_and_confirmation_uses_write_grant(tmp_path: Path):
    service, _, transport, _ = _service(tmp_path)

    service.propose("Маш, перенеси занятие по AI завтра с 19:00 на 20:00.", conversation_id="grants", now_local=NOW)
    token_calls = [call for call in transport.calls if "oauth2.googleapis.com/token" in call[0]]
    assert len(token_calls) == 1 and b"READ_REFRESH_MUST_NOT_ESCAPE" in token_calls[0][3]
    service.resolve("да", conversation_id="grants")
    token_calls = [call for call in transport.calls if "oauth2.googleapis.com/token" in call[0]]
    assert b"WRITE_REFRESH_MUST_NOT_ESCAPE" in token_calls[-1][3]


def test_duration_and_rename_only_change_their_owned_fields(tmp_path: Path):
    service, _, transport, _ = _service(tmp_path)
    preview = service.propose("Маш, перенеси занятие по AI завтра на 20:00 на два часа.", conversation_id="move", now_local=NOW)
    assert "20:00–22:00" in preview
    service.resolve("да", conversation_id="move")
    patch = json.loads(_event_patches(transport)[0][3])
    assert set(patch) == {"start", "end"}

    service, _, transport, _ = _service(tmp_path / "rename")
    assert "Переименовать" in service.propose("Маш, переименуй занятие по AI завтра в «Практика по AI».", conversation_id="rename", now_local=NOW)
    service.resolve("да", conversation_id="rename")
    patch = json.loads(_event_patches(transport)[0][3])
    assert patch == {"summary": "Практика по AI"}


def test_reject_not_found_multiple_reminder_and_factual_turn_never_patch(tmp_path: Path):
    service, _, transport, _ = _service(tmp_path)
    service.propose("Маш, перенеси занятие по AI завтра с 19:00 на 20:00.", conversation_id="reject", now_local=NOW)
    assert service.resolve("нет", conversation_id="reject") == "Хорошо, ничего в календаре не меняю."
    assert _event_patches(transport) == []
    service, _, transport, _ = _service(tmp_path / "none", _Transport([]))
    assert "не нашла" in service.propose("Маш, перенеси занятие по AI завтра с 19:00 на 20:00.", conversation_id="none", now_local=NOW).casefold()
    assert _event_patches(transport) == []
    service, _, transport, _ = _service(tmp_path / "many", _Transport([_event(), _event("evt-2")]))
    assert "несколько" in service.propose("Маш, перенеси занятие по AI завтра на 20:00.", conversation_id="many", now_local=NOW)
    assert _event_patches(transport) == []
    assert service.propose("Поставь напоминание завтра в 10:00", conversation_id="reminder", now_local=NOW) is None
    assert service.propose("У меня концерт во вторник в 20:00", conversation_id="fact", now_local=NOW) is None


def test_stale_preview_and_412_never_blindly_overwrite(tmp_path: Path):
    service, _, transport, _ = _service(tmp_path)
    service.propose("Маш, перенеси занятие по AI завтра с 19:00 на 20:00.", conversation_id="stale", now_local=NOW)
    transport.events["evt-1"]["summary"] = "другое событие"
    transport.events["evt-1"]["etag"] = '"v2"'
    assert "изменилось" in service.resolve("да", conversation_id="stale")
    assert _event_patches(transport) == []

    service, _, transport, _ = _service(tmp_path / "412")
    service.propose("Маш, перенеси занятие по AI завтра с 19:00 на 20:00.", conversation_id="precondition", now_local=NOW)
    transport.next_patch_error = GoogleCalendarHttpFailure(412)
    assert "изменилось" in service.resolve("да", conversation_id="precondition")
    assert len(_event_patches(transport)) == 1


def test_known_and_uncertain_retries_are_idempotent(tmp_path: Path):
    service, updater, transport, _ = _service(tmp_path)
    service.propose("Маш, перенеси занятие по AI завтра с 19:00 на 20:00.", conversation_id="known", now_local=NOW)
    transport.fail_token_once = True
    assert "не удалось" in service.resolve("да", conversation_id="known").casefold()
    assert _event_patches(transport) == []
    assert "Готово" in service.resolve("да", conversation_id="known")
    assert len(_event_patches(transport)) == 1

    service, updater, transport, _ = _service(tmp_path / "uncertain")
    service.propose("Маш, перенеси занятие по AI завтра с 19:00 на 20:00.", conversation_id="uncertain", now_local=NOW)
    transport.fail_after_patch = True
    assert "могло примениться" in service.resolve("да", conversation_id="uncertain")
    assert len(_event_patches(transport)) == 1
    transport.fail_after_patch = False
    assert "Готово" in service.resolve("да", conversation_id="uncertain")
    assert len(_event_patches(transport)) == 1


def test_update_safety_recurring_and_backup_safe_receipt(tmp_path: Path):
    service, updater, transport, _ = _service(tmp_path, _Transport([_event()]))
    policy = InternetAccessPolicyStore(tmp_path / "local-data/config/internet-access.json")
    policy.save(InternetAccessPolicy(mode=InternetAccessMode.OFF))
    updater.policy_store = policy
    assert "остановлены" in service.propose("Маш, перенеси занятие по AI завтра с 19:00 на 20:00.", conversation_id="off", now_local=NOW)
    assert _event_patches(transport) == []
    policy.save(InternetAccessPolicy())
    safety = AutonomySafetyStore(tmp_path / "local-data/config/autonomy-safety.json")
    AutonomySafetyService(store=safety).engage()
    updater.safety_store = safety
    assert "остановлены" in service.propose("Маш, перенеси занятие по AI завтра с 19:00 на 20:00.", conversation_id="stop", now_local=NOW)
    assert _event_patches(transport) == []
    service, _, transport, _ = _service(tmp_path / "recurring", _Transport([{**_event(), "recurringEventId": "series"}]))
    assert "не могу безопасно" in service.propose("Маш, перенеси занятие по AI завтра с 19:00 на 20:00.", conversation_id="recurring", now_local=NOW).casefold()
    assert _event_patches(transport) == []


def test_recovery_hold_blocks_update_but_absent_and_released_journal_do_not(tmp_path: Path):
    service, updater, transport, _ = _service(tmp_path)
    journal = RecoveryJournal(tmp_path)
    updater.recovery_journal = journal

    assert updater._blocked() is False
    journal.save(_recovery_state(RecoveryPhase.HOLD))
    assert updater._blocked() is True
    assert "остановлены" in service.propose(
        "Маш, перенеси занятие по AI завтра с 19:00 на 20:00.",
        conversation_id="hold", now_local=NOW,
    )
    assert transport.calls == []
    journal.save(_recovery_state(RecoveryPhase.RELEASED))
    assert updater._blocked() is False
