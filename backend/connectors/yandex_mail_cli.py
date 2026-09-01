from __future__ import annotations

import argparse
import getpass
from pathlib import Path

from backend.external_observation.policy import InternetAccessPolicyStore
from backend.runtime.safety import AutonomySafetyStore
from backend.secrets import WindowsCredentialManagerSecretStore

from .yandex_mail.config import (
    YANDEX_MAIL_CLIENT_SECRET_REF,
    YANDEX_MAIL_SECRET_REF,
    YANDEX_MAIL_WRITE_SCOPE,
    YANDEX_MAIL_WRITE_SECRET_REF,
    YandexMailConfig,
    YandexMailConfigStore,
)
from .yandex_mail.oauth import authorize


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)
    connect = commands.add_parser("connect")
    connect.add_argument("--client-id", required=True)
    connect.add_argument("--email", required=True)
    commands.add_parser("connect-write")
    commands.add_parser("status")
    commands.add_parser("disconnect")
    args = parser.parse_args(argv)
    root = args.project_root
    store = YandexMailConfigStore(root / "local-data/config/yandex-mail.json")
    secrets = WindowsCredentialManagerSecretStore()
    policy = InternetAccessPolicyStore(root / "local-data/config/internet-access.json")
    safety = AutonomySafetyStore(root / "local-data/config/autonomy-safety.json")

    if args.command == "status":
        config = store.load()
        if config is None:
            print("DISCONNECTED")
        else:
            print(
                f"READ_{config.credential_state(secrets).value.upper()} "
                f"MANAGE_{config.write_credential_state(secrets).value.upper()}"
            )
        return 0
    if args.command == "disconnect":
        config = store.load()
        secrets.delete(YANDEX_MAIL_SECRET_REF if config is None else config.secret_ref)
        secrets.delete(
            YANDEX_MAIL_CLIENT_SECRET_REF if config is None else config.client_secret_ref
        )
        secrets.delete(
            YANDEX_MAIL_WRITE_SECRET_REF
            if config is None or config.write_secret_ref is None
            else config.write_secret_ref
        )
        store.delete()
        print("DISCONNECTED")
        return 0

    if args.command == "connect-write":
        config = store.load()
        if config is None:
            raise RuntimeError("yandex_mail_read_connection_required")
        client_secret = secrets.get(config.client_secret_ref)
        if client_secret is None:
            raise RuntimeError("yandex_mail_client_secret_missing")
        tokens = authorize(
            client_id=config.client_id,
            client_secret=client_secret,
            code_prompt=lambda _: getpass.getpass("Yandex authorization code: "),
            policy_store=policy,
            safety_store=safety,
            scope=YANDEX_MAIL_WRITE_SCOPE,
        )
        refresh = tokens.get("refresh_token")
        if not isinstance(refresh, str) or not refresh:
            raise RuntimeError("yandex_write_refresh_token_missing")
        secrets.put(YANDEX_MAIL_WRITE_SECRET_REF, refresh)
        store.save(config.model_copy(update={
            "write_secret_ref": YANDEX_MAIL_WRITE_SECRET_REF,
            "write_requested_scope": YANDEX_MAIL_WRITE_SCOPE,
        }))
        print("MANAGE_READY")
        return 0

    client_secret = getpass.getpass("Yandex OAuth client secret: ")
    config = YandexMailConfig(client_id=args.client_id, account_email=args.email)
    tokens = authorize(
        client_id=config.client_id,
        client_secret=client_secret,
        code_prompt=lambda _: getpass.getpass("Yandex authorization code: "),
        policy_store=policy,
        safety_store=safety,
    )
    refresh = tokens.get("refresh_token")
    if not isinstance(refresh, str) or not refresh:
        raise RuntimeError("yandex_refresh_token_missing")
    secrets.put(config.client_secret_ref, client_secret)
    secrets.put(config.secret_ref, refresh)
    store.save(config)
    print("READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
