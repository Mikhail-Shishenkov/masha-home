"""Narrow, application-owned Google Calendar event creation.

The model never receives this writer.  A durable operation id becomes the
provider event id, which makes confirmation retries safe without guessing from
event titles or times.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import quote, urlencode
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from backend.backup.recovery_journal import RecoveryJournal
from backend.runtime.safety import AutonomySafetyStore

from .config import GoogleCalendarConfigStore
from .network import GoogleCalendarNetworkBlocked
from .reader import (
    CalendarEventEvidence,
    GoogleCalendarHttpFailure,
    GoogleCalendarReconnectRequired,
    GoogleCalendarTransport,
    GoogleCalendarUnavailable,
    GoogleTokenInvalidGrant,
    UrllibGoogleCalendarTransport,
    _normalize_event,
)


class CalendarCreateOperation(BaseModel):
    """The complete typed operation approved by the user, with no user secrets."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_id: str = Field(min_length=36, max_length=36)
    calendar_id: Literal["primary"] = "primary"
    calendar_label: Literal["Основной календарь"] = "Основной календарь"
    title: str = Field(min_length=1, max_length=500)
    start: AwareDatetime
    end: AwareDatetime
    home_timezone: str = Field(min_length=1, max_length=100)

    def provider_event_id(self) -> str:
        # Google event ids accept lowercase base32hex; UUID hex plus this
        # prefix is safely inside that alphabet and deterministic.
        UUID(self.operation_id)
        return "mashahome" + self.operation_id.replace("-", "")


class CalendarCreateReceipt(BaseModel):
    """Safe durable mutation truth; deliberately excludes response bodies/tokens."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: CalendarCreateOperation
    status: Literal["proposed", "rejected", "executing", "blocked", "failed", "created_unverified", "verified"]
    provider_event_id: str = Field(min_length=1, max_length=128)
    confirmed_at: AwareDatetime | None = None
    verified_at: AwareDatetime | None = None


class CalendarCreateReceiptStore:
    """Small atomic journal for idempotency and recovery-safe evidence."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._items = self._load()

    def get(self, operation_id: str) -> CalendarCreateReceipt | None:
        return self._items.get(operation_id)

    def put(self, receipt: CalendarCreateReceipt) -> CalendarCreateReceipt:
        items = {**self._items, receipt.operation.operation_id: receipt}
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"receipts": [item.model_dump(mode="json") for item in items.values()]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)
        self._items = items
        return receipt

    def _load(self) -> dict[str, CalendarCreateReceipt]:
        if not self.path.exists():
            return {}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return {
            item["operation"]["operation_id"]: CalendarCreateReceipt.model_validate(item)
            for item in payload.get("receipts", [])
        }


class GoogleCalendarWriter:
    """One primary-calendar create plus a separate fetch-and-verify step."""

    TOKEN_URL = "https://oauth2.googleapis.com/token"
    API_ROOT = "https://www.googleapis.com/calendar/v3"

    def __init__(self, *, config_store: GoogleCalendarConfigStore, secret_store, receipt_store: CalendarCreateReceiptStore, transport: GoogleCalendarTransport | None = None, policy_store=None, safety_store=None, recovery_journal: RecoveryJournal | None = None, clock=None):
        self.config_store = config_store
        self.secret_store = secret_store
        self.receipt_store = receipt_store
        self.transport = transport or UrllibGoogleCalendarTransport()
        self.policy_store = policy_store
        self.safety_store = safety_store
        self.recovery_journal = recovery_journal
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def create_and_verify(self, operation: CalendarCreateOperation) -> tuple[str, CalendarCreateReceipt]:
        """Returns a controlled status; no exception becomes conversation failure."""
        existing = self.receipt_store.get(operation.operation_id)
        if existing is not None:
            if existing.operation != operation or existing.provider_event_id != operation.provider_event_id():
                return "failed", existing
            if existing.status == "verified":
                return "verified", existing
            if existing.status in {"created_unverified", "executing"}:
                return self._reconcile_uncertain(existing)
        if self._blocked():
            receipt = CalendarCreateReceipt(operation=operation, status="blocked", provider_event_id=operation.provider_event_id())
            return "blocked", self.receipt_store.put(receipt)
        config = self.config_store.load()
        if config is None or config.write_secret_ref is None:
            receipt = CalendarCreateReceipt(operation=operation, status="failed", provider_event_id=operation.provider_event_id())
            return "needs_reconnect", self.receipt_store.put(receipt)
        refresh_token = self.secret_store.get(config.write_secret_ref)
        client_secret = self.secret_store.get(config.client_secret_ref)
        if refresh_token is None or client_secret is None:
            receipt = CalendarCreateReceipt(operation=operation, status="failed", provider_event_id=operation.provider_event_id())
            return "needs_reconnect", self.receipt_store.put(receipt)
        executing = CalendarCreateReceipt(operation=operation, status="executing", provider_event_id=operation.provider_event_id(), confirmed_at=self.clock())
        self.receipt_store.put(executing)
        try:
            token = self._access_token(config.client_id, refresh_token, client_secret)
        except GoogleTokenInvalidGrant:
            self.secret_store.delete(config.write_secret_ref)
            return "needs_reconnect", self.receipt_store.put(executing.model_copy(update={"status": "failed"}))
        except (GoogleCalendarUnavailable, GoogleCalendarReconnectRequired, GoogleCalendarNetworkBlocked):
            # No event POST was attempted: this is a known pre-mutation
            # failure and may safely be retried with the same operation id.
            return "failed", self.receipt_store.put(executing.model_copy(update={"status": "failed"}))
        try:
            # Re-check at the immediate mutation boundary, after token work.
            if self._blocked():
                return "blocked", self.receipt_store.put(executing.model_copy(update={"status": "blocked"}))
            body = json.dumps({
                "id": operation.provider_event_id(), "summary": operation.title,
                "start": {"dateTime": operation.start.isoformat(), "timeZone": operation.home_timezone},
                "end": {"dateTime": operation.end.isoformat(), "timeZone": operation.home_timezone},
            }, separators=(",", ":")).encode("utf-8")
            try:
                self._request(f"{self.API_ROOT}/calendars/primary/events", method="POST", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, body=body)
            except GoogleCalendarHttpFailure as error:
                if error.status_code != 409:
                    return "failed", self.receipt_store.put(executing.model_copy(update={"status": "failed"}))
            return self._verify_only(executing, token=token)
        except (GoogleCalendarUnavailable, GoogleCalendarReconnectRequired, GoogleCalendarNetworkBlocked):
            # The POST might have reached Google.  Preserve the operation id
            # and only ever attempt verification on a later retry.
            return "created_unverified", self.receipt_store.put(executing.model_copy(update={"status": "created_unverified"}))

    def _reconcile_uncertain(self, receipt: CalendarCreateReceipt) -> tuple[str, CalendarCreateReceipt]:
        """Reconcile a possibly-sent POST, then safely finish it only on 404.

        The deterministic Google event id is the idempotency key.  A positive
        fetch never posts again; only an explicit not-found result permits the
        same create request to be retried.
        """
        if self._blocked():
            return "blocked", self.receipt_store.put(receipt.model_copy(update={"status": "blocked"}))
        config = self.config_store.load()
        if config is None or config.write_secret_ref is None:
            return "needs_reconnect", receipt
        refresh_token = self.secret_store.get(config.write_secret_ref)
        client_secret = self.secret_store.get(config.client_secret_ref)
        if refresh_token is None or client_secret is None:
            return "needs_reconnect", receipt
        try:
            token = self._access_token(config.client_id, refresh_token, client_secret)
        except GoogleTokenInvalidGrant:
            self.secret_store.delete(config.write_secret_ref)
            return "needs_reconnect", self.receipt_store.put(receipt.model_copy(update={"status": "failed"}))
        except (GoogleCalendarUnavailable, GoogleCalendarReconnectRequired, GoogleCalendarNetworkBlocked):
            return "created_unverified", self.receipt_store.put(receipt.model_copy(update={"status": "created_unverified"}))
        try:
            item = self._get_event(receipt, token)
        except GoogleCalendarHttpFailure as error:
            if error.status_code != 404:
                return "created_unverified", self.receipt_store.put(receipt.model_copy(update={"status": "created_unverified"}))
            # Google has authoritatively said that the id does not exist, so a
            # retry with that exact id cannot duplicate a successful prior POST.
            return self._post_and_verify(receipt, token)
        except (GoogleCalendarUnavailable, GoogleCalendarNetworkBlocked):
            return "created_unverified", self.receipt_store.put(receipt.model_copy(update={"status": "created_unverified"}))
        return self._validate_fetched(receipt, item)

    def _verify_only(self, receipt: CalendarCreateReceipt, *, token: str | None = None) -> tuple[str, CalendarCreateReceipt]:
        if self._blocked():
            return "blocked", self.receipt_store.put(receipt.model_copy(update={"status": "blocked"}))
        config = self.config_store.load()
        if config is None or config.write_secret_ref is None:
            return "needs_reconnect", receipt
        if token is None:
            refresh_token = self.secret_store.get(config.write_secret_ref)
            client_secret = self.secret_store.get(config.client_secret_ref)
            if refresh_token is None or client_secret is None:
                return "needs_reconnect", receipt
            try:
                token = self._access_token(config.client_id, refresh_token, client_secret)
            except GoogleTokenInvalidGrant:
                self.secret_store.delete(config.write_secret_ref)
                return "needs_reconnect", self.receipt_store.put(receipt.model_copy(update={"status": "failed"}))
            except (GoogleCalendarUnavailable, GoogleCalendarReconnectRequired, GoogleCalendarNetworkBlocked):
                return "created_unverified", self.receipt_store.put(receipt.model_copy(update={"status": "created_unverified"}))
        try:
            return self._validate_fetched(receipt, self._get_event(receipt, token))
        except (GoogleCalendarUnavailable, GoogleCalendarNetworkBlocked):
            unverified = receipt.model_copy(update={"status": "created_unverified"})
            return "created_unverified", self.receipt_store.put(unverified)

    def _post_and_verify(self, receipt: CalendarCreateReceipt, token: str) -> tuple[str, CalendarCreateReceipt]:
        operation = receipt.operation
        body = json.dumps({
            "id": receipt.provider_event_id, "summary": operation.title,
            "start": {"dateTime": operation.start.isoformat(), "timeZone": operation.home_timezone},
            "end": {"dateTime": operation.end.isoformat(), "timeZone": operation.home_timezone},
        }, separators=(",", ":")).encode("utf-8")
        try:
            self._request(f"{self.API_ROOT}/calendars/primary/events", method="POST", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, body=body)
        except GoogleCalendarHttpFailure as error:
            if error.status_code != 409:
                return "failed", self.receipt_store.put(receipt.model_copy(update={"status": "failed"}))
        except (GoogleCalendarUnavailable, GoogleCalendarNetworkBlocked):
            return "created_unverified", self.receipt_store.put(receipt.model_copy(update={"status": "created_unverified"}))
        return self._verify_only(receipt, token=token)

    def _get_event(self, receipt: CalendarCreateReceipt, token: str) -> dict:
        return self._request(
            f"{self.API_ROOT}/calendars/primary/events/{quote(receipt.provider_event_id, safe='')}",
            headers={"Authorization": f"Bearer {token}"},
        )

    def _validate_fetched(self, receipt: CalendarCreateReceipt, item: dict) -> tuple[str, CalendarCreateReceipt]:
        evidence = _normalize_event(item, "primary", "Основной календарь", receipt.operation.start.tzinfo)
        if evidence is not None and self._matches(receipt.operation, evidence):
            verified = receipt.model_copy(update={"status": "verified", "verified_at": self.clock()})
            return "verified", self.receipt_store.put(verified)
        failed = receipt.model_copy(update={"status": "failed"})
        return "failed", self.receipt_store.put(failed)

    def reject(self, operation: CalendarCreateOperation) -> CalendarCreateReceipt:
        return self.receipt_store.put(CalendarCreateReceipt(operation=operation, status="rejected", provider_event_id=operation.provider_event_id()))

    def _access_token(self, client_id: str, refresh_token: str, client_secret: str) -> str:
        payload = self._request(self.TOKEN_URL, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"}, body=urlencode({"client_id": client_id, "client_secret": client_secret, "refresh_token": refresh_token, "grant_type": "refresh_token"}).encode("ascii"))
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise GoogleCalendarReconnectRequired("google_reconnect_required")
        return token

    def _request(self, url: str, *, method="GET", headers=None, body=None) -> dict:
        from .network import assert_google_network_allowed
        assert_google_network_allowed(policy_store=self.policy_store, safety_store=self.safety_store)
        return self.transport.request(url, method=method, headers=headers, body=body)

    def _blocked(self) -> bool:
        internet_off = False
        if self.policy_store is not None:
            from backend.external_observation.policy import InternetAccessMode
            internet_off = self.policy_store.load().mode is InternetAccessMode.OFF
        return bool(internet_off or (self.safety_store is not None and self.safety_store.is_engaged()) or (self.recovery_journal is not None and self.recovery_journal.is_hold()))

    @staticmethod
    def _matches(operation: CalendarCreateOperation, evidence: CalendarEventEvidence) -> bool:
        return (
            evidence.calendar_id == "primary" and evidence.event_id == operation.provider_event_id()
            and evidence.title == operation.title and isinstance(evidence.start, datetime) and isinstance(evidence.end, datetime)
            and evidence.start == operation.start and evidence.end == operation.end
        )
