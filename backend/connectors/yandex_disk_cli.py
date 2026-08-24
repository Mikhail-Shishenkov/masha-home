"""Interactive local setup for the read-only Yandex Disk connector."""

from __future__ import annotations

import argparse
import getpass
from pathlib import Path

from backend.external_observation.policy import InternetAccessPolicyStore
from backend.runtime.safety import AutonomySafetyStore
from backend.secrets import WindowsCredentialManagerSecretStore

from .yandex_disk.config import YANDEX_DISK_CLIENT_SECRET_REF, YANDEX_DISK_SECRET_REF, YandexDiskConfig, YandexDiskConfigStore
from .yandex_disk.oauth import authorize


def disconnect_yandex_disk(*, config_store: YandexDiskConfigStore, secret_store) -> None:
    config = config_store.load()
    secret_store.delete(YANDEX_DISK_SECRET_REF if config is None else config.secret_ref)
    secret_store.delete(YANDEX_DISK_CLIENT_SECRET_REF if config is None else config.client_secret_ref)
    config_store.delete()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)
    connect = commands.add_parser("connect")
    connect.add_argument("--client-id", required=True)
    connect.add_argument("--account-label")
    commands.add_parser("status")
    commands.add_parser("disconnect")
    args = parser.parse_args(argv)
    store = YandexDiskConfigStore(args.project_root / "local-data/config/yandex-disk.json")
    secrets = WindowsCredentialManagerSecretStore()
    if args.command == "status":
        config = store.load()
        print("DISCONNECTED" if config is None else config.credential_state(secrets).value.upper())
        return 0
    if args.command == "disconnect":
        disconnect_yandex_disk(config_store=store, secret_store=secrets)
        print("DISCONNECTED")
        return 0
    config = YandexDiskConfig(client_id=args.client_id, account_label=args.account_label)
    client_secret = getpass.getpass("Yandex OAuth client secret: ")
    tokens = authorize(client_id=config.client_id, client_secret=client_secret, code_prompt=lambda _: getpass.getpass("Yandex authorization code: "), policy_store=InternetAccessPolicyStore(args.project_root / "local-data/config/internet-access.json"), safety_store=AutonomySafetyStore(args.project_root / "local-data/config/autonomy-safety.json"))
    refresh_token = tokens.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise RuntimeError("yandex_disk_refresh_token_missing")
    secrets.put(config.client_secret_ref, client_secret)
    secrets.put(config.secret_ref, refresh_token)
    store.save(config)
    print("READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
