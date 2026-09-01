"""Bounded, confirmed Google Calendar event updates for the primary calendar."""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from datetime import date as calendar_date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import quote, urlencode
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from backend.backup.recovery_journal import RecoveryJournal
from backend.conversation.memory_intent import MemoryProposal, MemoryProposalStore, PendingProposalConflict, ProposalStatus
from backend.runtime.action_contracts import (
    ProposalPreparation,
    ProposalPreparationStatus,
)

from .config import GoogleCalendarConfigStore
from .network import GoogleCalendarNetworkBlocked, assert_google_network_allowed
from .reader import (
    GoogleCalendarHttpFailure, GoogleCalendarReconnectRequired,
    GoogleCalendarTransport, GoogleCalendarUnavailable, GoogleTokenInvalidGrant,
    UrllibGoogleCalendarTransport,
)


_SPACE = re.compile(r"\s+")
_MOVE = re.compile(
    r"^\s*(?:маш(?:а)?\s*,?\s*)?перенеси\s+(?P<title>.+?)\s+завтра"
    r"(?:\s+с\s+(?P<old>\d{1,2}:\d{2}))?\s+на\s+(?P<new>\d{1,2}:\d{2})"
    r"(?:\s+на\s+(?P<duration>\d+|два|две)\s+(?P<unit>час(?:а|ов)?|минут(?:у|ы)?))?\s*[.!?]?\s*$",
    re.IGNORECASE,
)
_RENAME = re.compile(
    r"^\s*(?:маш(?:а)?\s*,?\s*)?переименуй\s+(?P<title>.+?)\s+завтра\s+в\s+[«\"](?P<new_title>.{1,500}?)[»\"]\s*[.!?]?\s*$",
    re.IGNORECASE,
)
_REMINDER = re.compile(r"\b(?:напомни|напоминани\w*)\b", re.IGNORECASE)


class CalendarEventState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=1, max_length=500)
    start: AwareDatetime
    end: AwareDatetime


class CalendarUpdateIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    lookup_title: str = Field(min_length=1, max_length=500)
    date: datetime
    old_start_time: str | None = None
    desired_title: str | None = None
    desired_start_time: str | None = None
    desired_duration_minutes: int | None = Field(default=None, ge=1, le=24 * 60)


class CalendarUpdateOperation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_id: str = Field(min_length=36, max_length=36)
    calendar_id: Literal["primary"] = "primary"
    calendar_label: Literal["Основной календарь"] = "Основной календарь"
    provider_event_id: str = Field(min_length=1, max_length=300)
    before: CalendarEventState
    desired: CalendarEventState
    etag: str = Field(min_length=1, max_length=500)
    home_timezone: str = Field(min_length=1, max_length=100)


class CalendarResolvedTarget(BaseModel):
    """One real provider object bound by Home before any mutation proposal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_event_id: str = Field(min_length=1, max_length=300)
    before: CalendarEventState
    etag: str = Field(min_length=1, max_length=500)
    home_timezone: str = Field(min_length=1, max_length=100)


class CalendarUpdateReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: CalendarUpdateOperation
    status: Literal["proposed", "rejected", "executing", "blocked", "failed", "updated_unverified", "conflict", "target_missing", "verified"]
    confirmed_at: AwareDatetime | None = None
    verified_at: AwareDatetime | None = None


class CalendarUpdateReceiptStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._items = self._load()

    def get(self, operation_id: str) -> CalendarUpdateReceipt | None:
        return self._items.get(operation_id)

    def put(self, receipt: CalendarUpdateReceipt) -> CalendarUpdateReceipt:
        items = {**self._items, receipt.operation.operation_id: receipt}
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"receipts": [row.model_dump(mode="json") for row in items.values()]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)
        self._items = items
        return receipt

    def _load(self) -> dict[str, CalendarUpdateReceipt]:
        if not self.path.exists():
            return {}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return {row["operation"]["operation_id"]: CalendarUpdateReceipt.model_validate(row) for row in payload.get("receipts", [])}


def calendar_update_intent(message: str, now_local: datetime) -> CalendarUpdateIntent | None:
    """Only A2's explicit human update forms; reminder language never routes here."""
    normalized = _SPACE.sub(" ", message.casefold().replace("ё", "е")).strip()
    if _REMINDER.search(normalized):
        return None
    day = (now_local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    if match := _MOVE.match(normalized):
        duration = None
        if match.group("duration"):
            amount = match.group("duration")
            value = 2 if amount in {"два", "две"} else int(amount)
            duration = value if match.group("unit").startswith("мин") else value * 60
        return CalendarUpdateIntent(
            lookup_title=match.group("title").strip(), date=day,
            old_start_time=match.group("old"), desired_start_time=match.group("new"),
            desired_duration_minutes=duration,
        )
    if match := _RENAME.match(message):
        return CalendarUpdateIntent(
            lookup_title=match.group("title").strip(), date=day,
            desired_title=match.group("new_title").strip(),
        )
    return None


class GoogleCalendarUpdater:
    """Application-owned target resolution, conditional PATCH and verification."""

    API_ROOT = "https://www.googleapis.com/calendar/v3"
    TOKEN_URL = "https://oauth2.googleapis.com/token"

    def __init__(self, *, config_store: GoogleCalendarConfigStore, secret_store, receipt_store: CalendarUpdateReceiptStore, transport: GoogleCalendarTransport | None = None, policy_store=None, safety_store=None, recovery_journal: RecoveryJournal | None = None, clock=None):
        self.config_store = config_store
        self.secret_store = secret_store
        self.receipt_store = receipt_store
        self.transport = transport or UrllibGoogleCalendarTransport()
        self.policy_store = policy_store
        self.safety_store = safety_store
        self.recovery_journal = recovery_journal
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def resolve(self, intent: CalendarUpdateIntent) -> tuple[str, CalendarUpdateOperation | None]:
        """Bind exactly one current primary-calendar event before a proposal."""
        status, target = self.resolve_target(intent)
        if status != "resolved" or target is None:
            return status, None
        before = target.before
        desired_start = (
            before.start
            if intent.desired_start_time is None
            else self._at(intent.date, intent.desired_start_time)
        )
        duration = (
            before.end - before.start
            if intent.desired_duration_minutes is None
            else timedelta(minutes=intent.desired_duration_minutes)
        )
        desired = CalendarEventState(
            title=intent.desired_title or before.title,
            start=desired_start,
            end=desired_start + duration,
        )
        return "resolved", CalendarUpdateOperation(
            operation_id=str(uuid4()),
            provider_event_id=target.provider_event_id,
            before=before,
            desired=desired,
            etag=target.etag,
            home_timezone=target.home_timezone,
        )

    def resolve_target(
        self,
        intent: CalendarUpdateIntent,
    ) -> tuple[str, CalendarResolvedTarget | None]:
        """Resolve one provider-owned event without implying an update."""
        if self._blocked():
            return "blocked", None
        try:
            # Resolving a target is read-only and deliberately keeps the
            # Calendar read grant separate from the later write grant.
            token = self._read_token()
            start = intent.date
            end = start + timedelta(days=1)
            items = self._request(
                f"{self.API_ROOT}/calendars/primary/events?" + urlencode({
                    "timeMin": start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "timeMax": end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "singleEvents": "true", "orderBy": "startTime", "maxResults": "20",
                }), headers={"Authorization": f"Bearer {token}"},
            ).get("items", [])
        except GoogleTokenInvalidGrant:
            self._delete_read_secret()
            return "needs_reconnect", None
        except (GoogleCalendarUnavailable, GoogleCalendarReconnectRequired, GoogleCalendarNetworkBlocked):
            return "unavailable", None
        raw_items = [item for item in items if isinstance(item, dict)]
        candidates = [self._state_from_item(item, start.tzinfo) for item in raw_items]
        candidates = [
            row for row in candidates
            if row is not None
            and self._title_score(row[1].title, intent.lookup_title) >= 0.82
            and (
                intent.old_start_time is None
                or row[1].start.strftime("%H:%M") == intent.old_start_time
            )
        ]
        if not candidates:
            if any(
                isinstance(item.get("summary"), str)
                and self._title_matches(item["summary"], intent.lookup_title)
                and (item.get("recurrence") or item.get("recurringEventId") or item.get("start", {}).get("date"))
                for item in raw_items
            ):
                return "unsupported", None
            return "not_found", None
        if len(candidates) != 1:
            return "ambiguous", None
        event_id, _, _ = candidates[0]
        # The list response only narrows ownership.  Bind the preview to a
        # freshly read single event, including its current optimistic-lock tag.
        try:
            before, etag = self._fetch_event(event_id, start.tzinfo, token)
        except GoogleCalendarHttpFailure as error:
            return ("not_found" if error.status_code == 404 else "unavailable"), None
        except (GoogleCalendarUnavailable, GoogleCalendarReconnectRequired, GoogleCalendarNetworkBlocked):
            return "unavailable", None
        if not self._title_matches(before.title, intent.lookup_title) or (
            intent.old_start_time is not None and before.start.strftime("%H:%M") != intent.old_start_time
        ):
            return "not_found", None
        return "resolved", CalendarResolvedTarget(
            provider_event_id=event_id,
            before=before,
            etag=etag,
            home_timezone=str(start.tzinfo),
        )

    def update_and_verify(self, operation: CalendarUpdateOperation) -> tuple[str, CalendarUpdateReceipt]:
        existing = self.receipt_store.get(operation.operation_id)
        if existing is not None:
            if existing.operation != operation:
                return "failed", existing
            if existing.status == "verified":
                return "verified", existing
            if existing.status == "updated_unverified":
                return self._reconcile(existing)
        if self._blocked():
            return "blocked", self.receipt_store.put(CalendarUpdateReceipt(operation=operation, status="blocked"))
        executing = self.receipt_store.put(CalendarUpdateReceipt(operation=operation, status="executing", confirmed_at=self.clock()))
        try:
            token = self._write_token()
        except GoogleTokenInvalidGrant:
            self._delete_write_secret()
            return "needs_reconnect", self.receipt_store.put(executing.model_copy(update={"status": "failed"}))
        except (GoogleCalendarUnavailable, GoogleCalendarReconnectRequired, GoogleCalendarNetworkBlocked):
            return "failed", self.receipt_store.put(executing.model_copy(update={"status": "failed"}))
        return self._guard_patch_verify(executing, token)

    def _reconcile(self, receipt: CalendarUpdateReceipt) -> tuple[str, CalendarUpdateReceipt]:
        if self._blocked():
            return "blocked", self.receipt_store.put(receipt.model_copy(update={"status": "blocked"}))
        try:
            token = self._write_token()
            current, etag = self._fetch_current(receipt.operation, token)
        except GoogleCalendarHttpFailure as error:
            if error.status_code == 404:
                return "target_missing", self.receipt_store.put(receipt.model_copy(update={"status": "target_missing"}))
            return "updated_unverified", self.receipt_store.put(receipt.model_copy(update={"status": "updated_unverified"}))
        except GoogleTokenInvalidGrant:
            self._delete_write_secret()
            return "needs_reconnect", self.receipt_store.put(receipt.model_copy(update={"status": "failed"}))
        except (GoogleCalendarUnavailable, GoogleCalendarReconnectRequired, GoogleCalendarNetworkBlocked):
            return "updated_unverified", self.receipt_store.put(receipt.model_copy(update={"status": "updated_unverified"}))
        if current == receipt.operation.desired:
            return self._verified(receipt)
        if current != receipt.operation.before:
            return "conflict", self.receipt_store.put(receipt.model_copy(update={"status": "conflict"}))
        fresh = receipt.model_copy(update={"operation": receipt.operation.model_copy(update={"etag": etag})})
        return self._patch_then_verify(fresh, token)

    def _guard_patch_verify(self, receipt: CalendarUpdateReceipt, token: str) -> tuple[str, CalendarUpdateReceipt]:
        try:
            current, etag = self._fetch_current(receipt.operation, token)
        except GoogleCalendarHttpFailure as error:
            if error.status_code == 404:
                return "target_missing", self.receipt_store.put(receipt.model_copy(update={"status": "target_missing"}))
            return "failed", self.receipt_store.put(receipt.model_copy(update={"status": "failed"}))
        except (GoogleCalendarUnavailable, GoogleCalendarNetworkBlocked):
            return "failed", self.receipt_store.put(receipt.model_copy(update={"status": "failed"}))
        if current == receipt.operation.desired:
            return self._verified(receipt)
        if current != receipt.operation.before:
            return "conflict", self.receipt_store.put(receipt.model_copy(update={"status": "conflict"}))
        return self._patch_then_verify(receipt.model_copy(update={"operation": receipt.operation.model_copy(update={"etag": etag})}), token)

    def _patch_then_verify(self, receipt: CalendarUpdateReceipt, token: str) -> tuple[str, CalendarUpdateReceipt]:
        if self._blocked():
            return "blocked", self.receipt_store.put(receipt.model_copy(update={"status": "blocked"}))
        operation = receipt.operation
        payload: dict[str, object] = {}
        if operation.before.title != operation.desired.title:
            payload["summary"] = operation.desired.title
        if operation.before.start != operation.desired.start:
            payload["start"] = {"dateTime": operation.desired.start.isoformat(), "timeZone": operation.home_timezone}
        if operation.before.end != operation.desired.end:
            payload["end"] = {"dateTime": operation.desired.end.isoformat(), "timeZone": operation.home_timezone}
        try:
            self._request(
                f"{self.API_ROOT}/calendars/primary/events/{quote(operation.provider_event_id, safe='')}", method="PATCH",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "If-Match": operation.etag},
                body=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            )
        except GoogleCalendarHttpFailure as error:
            if error.status_code == 412:
                return self._reconcile_after_precondition(receipt, token)
            if error.status_code == 404:
                return "target_missing", self.receipt_store.put(receipt.model_copy(update={"status": "target_missing"}))
            return "failed", self.receipt_store.put(receipt.model_copy(update={"status": "failed"}))
        except (GoogleCalendarUnavailable, GoogleCalendarNetworkBlocked):
            return "updated_unverified", self.receipt_store.put(receipt.model_copy(update={"status": "updated_unverified"}))
        try:
            current, _ = self._fetch_current(operation, token)
        except (GoogleCalendarUnavailable, GoogleCalendarNetworkBlocked, GoogleCalendarHttpFailure):
            return "updated_unverified", self.receipt_store.put(receipt.model_copy(update={"status": "updated_unverified"}))
        if current == operation.desired:
            return self._verified(receipt)
        return "conflict", self.receipt_store.put(receipt.model_copy(update={"status": "conflict"}))

    def _reconcile_after_precondition(self, receipt: CalendarUpdateReceipt, token: str) -> tuple[str, CalendarUpdateReceipt]:
        try:
            current, _ = self._fetch_current(receipt.operation, token)
        except GoogleCalendarHttpFailure as error:
            if error.status_code == 404:
                return "target_missing", self.receipt_store.put(receipt.model_copy(update={"status": "target_missing"}))
            return "conflict", self.receipt_store.put(receipt.model_copy(update={"status": "conflict"}))
        except (GoogleCalendarUnavailable, GoogleCalendarNetworkBlocked):
            return "updated_unverified", self.receipt_store.put(receipt.model_copy(update={"status": "updated_unverified"}))
        return self._verified(receipt) if current == receipt.operation.desired else ("conflict", self.receipt_store.put(receipt.model_copy(update={"status": "conflict"})))

    def reject(self, operation: CalendarUpdateOperation) -> CalendarUpdateReceipt:
        return self.receipt_store.put(CalendarUpdateReceipt(operation=operation, status="rejected"))

    def _read_token(self) -> str:
        config = self.config_store.load()
        if config is None:
            raise GoogleCalendarReconnectRequired("google_reconnect_required")
        refresh = self.secret_store.get(config.secret_ref)
        secret = self.secret_store.get(config.client_secret_ref)
        if refresh is None or secret is None:
            raise GoogleCalendarReconnectRequired("google_reconnect_required")
        return self._access_token(config.client_id, refresh, secret)

    def _write_token(self) -> str:
        config = self.config_store.load()
        if config is None or config.write_secret_ref is None:
            raise GoogleCalendarReconnectRequired("google_reconnect_required")
        refresh = self.secret_store.get(config.write_secret_ref)
        secret = self.secret_store.get(config.client_secret_ref)
        if refresh is None or secret is None:
            raise GoogleCalendarReconnectRequired("google_reconnect_required")
        return self._access_token(config.client_id, refresh, secret)

    def _access_token(self, client_id: str, refresh: str, secret: str) -> str:
        payload = self._request(self.TOKEN_URL, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"}, body=urlencode({"client_id": client_id, "client_secret": secret, "refresh_token": refresh, "grant_type": "refresh_token"}).encode("ascii"))
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise GoogleCalendarReconnectRequired("google_reconnect_required")
        return token

    def _fetch_current(self, operation: CalendarUpdateOperation, token: str) -> tuple[CalendarEventState, str]:
        return self._fetch_event(operation.provider_event_id, operation.before.start.tzinfo, token)

    def _fetch_event(self, event_id: str, home_timezone, token: str) -> tuple[CalendarEventState, str]:
        item = self._request(f"{self.API_ROOT}/calendars/primary/events/{quote(event_id, safe='')}", headers={"Authorization": f"Bearer {token}"})
        parsed = self._state_from_item(item, home_timezone)
        if parsed is None or parsed[0] != event_id:
            raise GoogleCalendarUnavailable("google_calendar_unavailable")
        return parsed[1], parsed[2]

    @staticmethod
    def _state_from_item(item: dict, home_timezone):
        if item.get("recurrence") or item.get("recurringEventId") or item.get("start", {}).get("date"):
            return None
        identifier, title, etag = item.get("id"), item.get("summary"), item.get("etag")
        start, end = item.get("start", {}).get("dateTime"), item.get("end", {}).get("dateTime")
        if not all(isinstance(value, str) and value for value in (identifier, title, etag, start, end)):
            return None
        try:
            before = CalendarEventState(
                title=title[:500], start=datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(home_timezone),
                end=datetime.fromisoformat(end.replace("Z", "+00:00")).astimezone(home_timezone),
            )
        except ValueError:
            return None
        return identifier[:300], before, etag[:500]

    @staticmethod
    def _title_matches(actual: str, query: str) -> bool:
        return GoogleCalendarUpdater._title_score(actual, query) >= 0.82

    @staticmethod
    def _title_score(actual: str, query: str) -> float:
        """Bounded reference similarity over real provider-owned summaries."""

        def normalized(value: str) -> str:
            return " ".join(re.findall(
                r"[a-zа-яё0-9]+", value.casefold().replace("ё", "е"),
            ))

        actual_text, query_text = normalized(actual), normalized(query)
        if not actual_text or not query_text:
            return 0.0
        if actual_text == query_text:
            return 1.0
        return SequenceMatcher(None, actual_text, query_text, autojunk=False).ratio()

    @staticmethod
    def _at(day: datetime, value: str) -> datetime:
        hour, minute = map(int, value.split(":"))
        return day.replace(hour=hour, minute=minute)

    def _request(self, url: str, *, method="GET", headers=None, body=None) -> dict:
        assert_google_network_allowed(policy_store=self.policy_store, safety_store=self.safety_store)
        return self.transport.request(url, method=method, headers=headers, body=body)

    def _blocked(self) -> bool:
        from backend.external_observation.policy import InternetAccessMode
        return bool(
            (self.policy_store is not None and self.policy_store.load().mode is InternetAccessMode.OFF)
            or (self.safety_store is not None and self.safety_store.is_engaged())
            or (self.recovery_journal is not None and self.recovery_journal.is_hold())
        )

    def _delete_write_secret(self) -> None:
        config = self.config_store.load()
        if config is not None and config.write_secret_ref is not None:
            self.secret_store.delete(config.write_secret_ref)

    def _delete_read_secret(self) -> None:
        config = self.config_store.load()
        if config is not None:
            self.secret_store.delete(config.secret_ref)

    def _verified(self, receipt: CalendarUpdateReceipt) -> tuple[str, CalendarUpdateReceipt]:
        return "verified", self.receipt_store.put(receipt.model_copy(update={"status": "verified", "verified_at": self.clock()}))


class GoogleCalendarUpdateConversationService:
    def __init__(self, *, proposal_store: MemoryProposalStore, updater: GoogleCalendarUpdater):
        self.proposal_store = proposal_store
        self.updater = updater

    def propose(self, message: str, *, conversation_id: str, now_local: datetime):
        intent = calendar_update_intent(message, now_local)
        if intent is None:
            return None
        return self.propose_intent(intent, conversation_id=conversation_id, now_local=now_local)

    def propose_from_resolved_intent(
        self,
        *,
        subject: str,
        date: str,
        start_time: str,
        conversation_id: str,
        now_local: datetime,
        old_time: str | None = None,
        duration_minutes: str | None = None,
    ) -> str | None:
        """Compatibility text projection over structured preparation truth."""
        return self.prepare_from_resolved_intent(
            subject=subject,
            date=date,
            start_time=start_time,
            conversation_id=conversation_id,
            now_local=now_local,
            old_time=old_time,
            duration_minutes=duration_minutes,
        ).response

    def prepare_from_resolved_intent(
        self,
        *,
        subject: str,
        date: str,
        start_time: str,
        conversation_id: str,
        now_local: datetime,
        old_time: str | None = None,
        duration_minutes: str | None = None,
    ) -> ProposalPreparation:
        """Bridge validated V2 meaning into the mature update owner.

        It deliberately receives no provider event ID.  The updater still
        performs its own bounded read lookup and binds exactly one event before
        any confirmation can exist.
        """
        try:
            day = datetime.combine(
                calendar_date.fromisoformat(date),
                time.min,
                tzinfo=now_local.tzinfo,
            )
            duration = None if duration_minutes is None else int(duration_minutes)
        except (TypeError, ValueError):
            return ProposalPreparation(
                response="Не смогла безопасно разобрать изменение. Ничего в календаре не меняю.",
                status=ProposalPreparationStatus.NO_ACTION,
            )
        if not subject.strip() or not re.fullmatch(r"\d{2}:\d{2}", start_time):
            return ProposalPreparation(
                response="Не смогла безопасно разобрать изменение. Ничего в календаре не меняю.",
                status=ProposalPreparationStatus.NO_ACTION,
            )
        if old_time is not None and re.fullmatch(r"\d{2}:\d{2}", old_time) is None:
            return ProposalPreparation(
                response="Не смогла безопасно разобрать прежнее время. Ничего в календаре не меняю.",
                status=ProposalPreparationStatus.NO_ACTION,
            )
        intent = CalendarUpdateIntent(
            lookup_title=subject.strip(), date=day,
            old_start_time=old_time,
            desired_start_time=start_time,
            desired_duration_minutes=duration,
        )
        return self._prepare_intent(
            intent,
            conversation_id=conversation_id,
            now_local=now_local,
        )

    def propose_intent(
        self,
        intent: CalendarUpdateIntent,
        *,
        conversation_id: str,
        now_local: datetime,
    ) -> str:
        return self._prepare_intent(
            intent,
            conversation_id=conversation_id,
            now_local=now_local,
        ).response

    def _prepare_intent(
        self,
        intent: CalendarUpdateIntent,
        *,
        conversation_id: str,
        now_local: datetime,
    ) -> ProposalPreparation:
        status, operation = self.updater.resolve(intent)
        if status != "resolved" or operation is None:
            response = {
                "not_found": "Не нашла это событие в Основном календаре — ничего нового не создаю.",
                "unsupported": "Не могу безопасно изменить повторяющееся или особое событие — ничего не меняю.",
                "ambiguous": "Нашла несколько похожих событий. Уточни время точнее — ничего не меняю.",
                "blocked": "Сейчас внешние действия остановлены, поэтому ничего в календаре не меняю.",
                "needs_reconnect": "Для изменения событий нужно отдельно переподключить Google Calendar.",
            }.get(status, "Сейчас не удалось проверить календарь для изменения.")
            return ProposalPreparation(
                response=response,
                status=ProposalPreparationStatus.NO_ACTION,
            )
        proposal = MemoryProposal(id=str(uuid4()), conversation_id=conversation_id, record_type="google_calendar_event", record_payload=operation.model_dump(mode="json"), created_at=now_local, status=ProposalStatus.PENDING, operation="google_calendar_update")
        try:
            self.proposal_store.create(proposal)
        except PendingProposalConflict:
            return ProposalPreparation(
                response="Сначала закончим предыдущее подтверждение — пока ничего нового не меняю.",
                status=ProposalPreparationStatus.NO_ACTION,
            )
        self.updater.receipt_store.put(CalendarUpdateReceipt(operation=operation, status="proposed"))
        response = f"Перенести «{operation.before.title}» в Основном календаре: {operation.before.start:%d.%m, %H:%M}–{operation.before.end:%H:%M} → {operation.desired.start:%H:%M}–{operation.desired.end:%H:%M}?" if operation.before.title == operation.desired.title else f"Переименовать «{operation.before.title}» в «{operation.desired.title}» в Основном календаре?"
        return ProposalPreparation(
            response=response,
            status=ProposalPreparationStatus.PENDING_CONFIRMATION,
            application_operation="google_calendar_update",
        )

    def resolve(self, message: str, *, conversation_id: str, proposal_id: str | None = None):
        match = re.match(r"^\s*(?:да|подтверждаю|измени|перенеси)(?:\s+(?P<id>[0-9a-f-]{36}))?\s*[.!]?\s*$", message, re.IGNORECASE)
        reject = re.match(r"^\s*(?:нет|не надо|не сейчас|отмена)(?:\s+(?P<id>[0-9a-f-]{36}))?\s*[.!]?\s*$", message, re.IGNORECASE)
        command = match or reject
        if command is None:
            return None
        proposal = self.proposal_store.current_for_conversation(conversation_id)
        expected = proposal_id or command.group("id")
        if proposal is None or (expected is not None and proposal.id != expected) or proposal.operation != "google_calendar_update":
            return None
        try:
            operation = CalendarUpdateOperation.model_validate(proposal.record_payload)
        except Exception:
            self.proposal_store.set_status(proposal.id, ProposalStatus.CANCELLED)
            return "Не смогла безопасно проверить изменение, поэтому ничего в календаре не меняла."
        if reject is not None:
            self.updater.reject(operation)
            self.proposal_store.set_status(proposal.id, ProposalStatus.CANCELLED)
            return "Хорошо, ничего в календаре не меняю."
        status, _ = self.updater.update_and_verify(operation)
        if status == "verified":
            self.proposal_store.set_status(proposal.id, ProposalStatus.CONFIRMED)
            return f"Готово: «{operation.desired.title}» обновила в Основном календаре."
        if status == "updated_unverified":
            return "Изменение могло примениться, но я пока не смогла его проверить. Повторно не перезаписываю событие."
        if status == "conflict":
            return "Событие изменилось после предпросмотра. Покажи его заново — я ничего не перезаписываю."
        if status == "target_missing":
            return "Этого события больше нет в календаре, поэтому ничего нового не создаю."
        if status == "needs_reconnect":
            return "Для изменения событий нужно отдельно переподключить Google Calendar."
        if status == "blocked":
            return "Сейчас внешние действия остановлены, поэтому ничего в календаре не меняю."
        return "Не удалось изменить событие — ничего не утверждаю как готовое."
