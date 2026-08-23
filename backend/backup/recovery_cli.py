"""Minimal offline recovery entry point; passphrases never enter argv or env."""

from __future__ import annotations

import argparse
import getpass
from pathlib import Path

from .recovery import WholeHomeRecoveryService
from .recovery_models import RestoreMode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    preview = commands.add_parser("preview")
    preview.add_argument("backup", type=Path)
    restore = commands.add_parser("restore")
    restore.add_argument("backup", type=Path)
    restore.add_argument("--mode", choices=[item.value for item in RestoreMode], required=True)
    restore.add_argument("--expected-backup-id", required=True)
    commands.add_parser("status")
    commands.add_parser("release")
    interrupted = commands.add_parser("recover-interrupted")
    interrupted.add_argument("backup", type=Path, nargs="?")
    interrupted.add_argument("--expected-backup-id")
    args = parser.parse_args(argv)
    service = WholeHomeRecoveryService(args.project_root)
    if args.command == "status":
        state = service.journal.load()
        print("none" if state is None else state.model_dump_json())
        return 0
    if args.command == "release":
        print(service.release_recovery_hold().model_dump_json())
        return 0
    passphrase = getpass.getpass("Recovery passphrase: ")
    if args.command == "preview":
        print(service.preview_restore(args.backup, passphrase).model_dump_json())
        return 0
    if args.command == "recover-interrupted":
        print(service.recover_interrupted(
            passphrase, backup_path=args.backup, expected_backup_id=args.expected_backup_id,
        ).model_dump_json())
        return 0
    print(service.restore(
        args.backup,
        passphrase,
        expected_backup_id=args.expected_backup_id,
        restore_mode=RestoreMode(args.mode),
    ).model_dump_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
