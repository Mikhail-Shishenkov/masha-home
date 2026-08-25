"""Minimal desktop setup command for the single read-only Google Calendar connector."""

from __future__ import annotations

import argparse
from pathlib import Path

from backend.secrets import WindowsCredentialManagerSecretStore
from backend.external_observation.policy import InternetAccessPolicyStore
from backend.runtime.safety import AutonomySafetyStore

from .google_calendar.config import (
    GOOGLE_CALENDAR_CLIENT_SECRET_REF,
    GOOGLE_CALENDAR_SECRET_REF,
    GOOGLE_CALENDAR_WRITE_SCOPE,
    GOOGLE_CALENDAR_WRITE_SECRET_REF,
    GoogleCalendarConfig,
    GoogleCalendarConfigStore,
    read_google_desktop_client_json,
)
from .google_calendar.oauth import GoogleDesktopOAuthFlow


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)
    connect = commands.add_parser("connect")
    connect.add_argument("--client-json", type=Path, required=True)
    connect.add_argument("--account-label")
    connect_write = commands.add_parser("connect-write")
    connect_write.add_argument("--client-json", type=Path, required=True)
    commands.add_parser("status")
    commands.add_parser("disconnect")
    args = parser.parse_args(argv)
    store = GoogleCalendarConfigStore(args.project_root / "local-data/config/google-calendar.json")
    secrets = WindowsCredentialManagerSecretStore()
    policy_store = InternetAccessPolicyStore(args.project_root / "local-data/config/internet-access.json")
    safety_store = AutonomySafetyStore(args.project_root / "local-data/config/autonomy-safety.json")
    if args.command == "status":
        config = store.load()
        print("DISCONNECTED" if config is None else config.credential_state(secrets).value.upper())
        return 0
    if args.command == "disconnect":
        disconnect_google_calendar(config_store=store, secret_store=secrets)
        print("DISCONNECTED")
        return 0
    desktop_client = read_google_desktop_client_json(args.client_json)
    if args.command == "connect-write":
        existing = store.load()
        if existing is None or existing.client_id != desktop_client.client_id:
            print("CONNECT_READ_FIRST")
            return 2
        tokens = GoogleDesktopOAuthFlow(policy_store=policy_store, safety_store=safety_store).authorize(
            existing, client_secret=desktop_client.client_secret, scope=GOOGLE_CALENDAR_WRITE_SCOPE,
        )
        # Existing read credential is intentionally untouched until write
        # OAuth has fully succeeded.
        secrets.put(existing.client_secret_ref, desktop_client.client_secret)
        secrets.put(GOOGLE_CALENDAR_WRITE_SECRET_REF, tokens.refresh_token)
        store.save(existing.model_copy(update={
            "write_secret_ref": GOOGLE_CALENDAR_WRITE_SECRET_REF,
            "write_requested_scope": GOOGLE_CALENDAR_WRITE_SCOPE,
        }))
        print("READY")
        return 0
    config = GoogleCalendarConfig(client_id=desktop_client.client_id, account_label=args.account_label)
    tokens = GoogleDesktopOAuthFlow(policy_store=policy_store, safety_store=safety_store).authorize(
        config, client_secret=desktop_client.client_secret,
    )
    secrets.put(config.client_secret_ref, desktop_client.client_secret)
    secrets.put(config.secret_ref, tokens.refresh_token)
    store.save(config)
    print("READY")
    return 0


def disconnect_google_calendar(*, config_store: GoogleCalendarConfigStore, secret_store) -> None:
    """Remove both stored Google credentials; config refs are diagnostic only."""

    config = config_store.load()
    if config is None:
        secret_store.delete(GOOGLE_CALENDAR_SECRET_REF)
        secret_store.delete(GOOGLE_CALENDAR_WRITE_SECRET_REF)
        secret_store.delete(GOOGLE_CALENDAR_CLIENT_SECRET_REF)
    else:
        secret_store.delete(config.secret_ref)
        if config.write_secret_ref is not None:
            secret_store.delete(config.write_secret_ref)
        secret_store.delete(config.client_secret_ref)
    config_store.delete()


if __name__ == "__main__":
    raise SystemExit(main())
