"""Minimal desktop setup command for the single read-only Google Calendar connector."""

from __future__ import annotations

import argparse
from pathlib import Path

from backend.secrets import WindowsCredentialManagerSecretStore

from .google_calendar.config import GoogleCalendarConfig, GoogleCalendarConfigStore
from .google_calendar.oauth import GoogleDesktopOAuthFlow


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)
    connect = commands.add_parser("connect")
    connect.add_argument("--client-id", required=True)
    connect.add_argument("--client-secret")
    connect.add_argument("--account-label")
    commands.add_parser("status")
    commands.add_parser("disconnect")
    args = parser.parse_args(argv)
    store = GoogleCalendarConfigStore(args.project_root / "local-data/config/google-calendar.json")
    secrets = WindowsCredentialManagerSecretStore()
    if args.command == "status":
        config = store.load()
        print("DISCONNECTED" if config is None else config.credential_metadata().credential_state(secrets).value.upper())
        return 0
    if args.command == "disconnect":
        config = store.load()
        if config is not None:
            secrets.delete(config.secret_ref)
        store.delete()
        print("DISCONNECTED")
        return 0
    config = GoogleCalendarConfig(client_id=args.client_id, client_secret=args.client_secret, account_label=args.account_label)
    tokens = GoogleDesktopOAuthFlow().authorize(config)
    secrets.put(config.secret_ref, tokens.refresh_token)
    store.save(config)
    print("READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
