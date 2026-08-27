"""Minimal local setup command for the read-only Google Drive connector."""

from __future__ import annotations

import argparse
from pathlib import Path

from backend.connectors.google_calendar.config import read_google_desktop_client_json
from backend.connectors.google_calendar.oauth import GoogleDesktopOAuthFlow
from backend.external_observation.policy import InternetAccessPolicyStore
from backend.runtime.safety import AutonomySafetyStore
from backend.secrets import WindowsCredentialManagerSecretStore

from .google_drive.config import (
    GOOGLE_DRIVE_CLIENT_SECRET_REF,
    GOOGLE_DRIVE_SECRET_REF,
    GOOGLE_DOCUMENTS_WRITE_SCOPE,
    GOOGLE_DOCUMENTS_WRITE_SECRET_REF,
    GoogleDriveConfig,
    GoogleDriveConfigStore,
)


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
    store = GoogleDriveConfigStore(args.project_root / "local-data/config/google-drive.json")
    secrets = WindowsCredentialManagerSecretStore()
    policy_store = InternetAccessPolicyStore(args.project_root / "local-data/config/internet-access.json")
    safety_store = AutonomySafetyStore(args.project_root / "local-data/config/autonomy-safety.json")
    if args.command == "status":
        config = store.load()
        print("DISCONNECTED" if config is None else config.credential_state(secrets).value.upper())
        return 0
    if args.command == "disconnect":
        disconnect_google_drive(config_store=store, secret_store=secrets)
        print("DISCONNECTED")
        return 0
    desktop_client = read_google_desktop_client_json(args.client_json)
    if args.command == "connect-write":
        config = store.load()
        if config is None:
            print("Сначала подключи чтение Google Drive.")
            return 2
        if config.client_id != desktop_client.client_id:
            print("OAuth client не совпадает с подключённым Google Drive.")
            return 2
        write_config = config.model_copy(update={
            "document_write_secret_ref": GOOGLE_DOCUMENTS_WRITE_SECRET_REF,
            "document_write_requested_scope": GOOGLE_DOCUMENTS_WRITE_SCOPE,
        })
        tokens = GoogleDesktopOAuthFlow(policy_store=policy_store, safety_store=safety_store).authorize(
            write_config, client_secret=desktop_client.client_secret, scope=GOOGLE_DOCUMENTS_WRITE_SCOPE,
        )
        secrets.put(write_config.client_secret_ref, desktop_client.client_secret)
        secrets.put(GOOGLE_DOCUMENTS_WRITE_SECRET_REF, tokens.refresh_token)
        store.save(write_config)
        print("READY")
        return 0
    config = GoogleDriveConfig(client_id=desktop_client.client_id, account_label=args.account_label)
    tokens = GoogleDesktopOAuthFlow(policy_store=policy_store, safety_store=safety_store).authorize(
        config, client_secret=desktop_client.client_secret,
    )
    secrets.put(config.client_secret_ref, desktop_client.client_secret)
    secrets.put(config.secret_ref, tokens.refresh_token)
    store.save(config)
    print("READY")
    return 0


def disconnect_google_drive(*, config_store: GoogleDriveConfigStore, secret_store) -> None:
    config = config_store.load()
    if config is None:
        secret_store.delete(GOOGLE_DRIVE_SECRET_REF)
        secret_store.delete(GOOGLE_DRIVE_CLIENT_SECRET_REF)
        secret_store.delete(GOOGLE_DOCUMENTS_WRITE_SECRET_REF)
    else:
        secret_store.delete(config.secret_ref)
        secret_store.delete(config.client_secret_ref)
        if config.document_write_secret_ref is not None:
            secret_store.delete(config.document_write_secret_ref)
    config_store.delete()


if __name__ == "__main__":
    raise SystemExit(main())
