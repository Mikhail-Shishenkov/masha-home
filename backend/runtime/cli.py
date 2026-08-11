"""Small human-facing entry point for the local Daily Runtime."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.conversation.cli import PROJECT_ROOT, build_service
from backend.temporal.proactive import ProactivePolicyStore
from backend.temporal.proactive_daemon import ProactiveDaemon

from .daily_runtime import DailyRuntime, DailyRuntimeJournal
from .health import RuntimeHealthService
from .safety import AutonomySafetyStore


def _runtime(service):
    return DailyRuntime(
        history=service.history,
        temporal_engine=service.temporal_engine,
        repository=service.memory_retriever.memory_store,
        identity_kernel=service.identity_kernel,
        router=service.router,
        model_profiles=service.model_profiles,
        safety_store=AutonomySafetyStore(
            service.model_profiles.path.parent / "autonomy-safety.json"
        ),
    )


def run_command(command: str, *, project_root: Path = PROJECT_ROOT, raw: bool = False, output=print) -> int:
    service = build_service(project_root=project_root)
    daemon = ProactiveDaemon(project_root)
    journal = DailyRuntimeJournal(project_root / "local-data" / "runtime" / "daily-runtime-receipts.json")

    if command == "status":
        report = RuntimeHealthService(service=service, project_root=project_root, daemon=daemon).inspect()
        if raw:
            output(json.dumps(report.model_dump(mode="json"), ensure_ascii=False))
        else:
            labels = {"ok": "✓", "warning": "!", "error": "×"}
            title = {"ready": "Маша готова", "degraded": "Маша работает с ограничениями", "unavailable": "Маша не готова"}[report.status]
            output(title + "\n\n" + "\n".join(f"{labels[item.status]} {item.name}: {item.detail}" for item in report.checks))
        return 0 if report.status != "unavailable" else 1

    if command == "run":
        policy = ProactivePolicyStore(service.model_profiles.path.parent / "proactive-policy.json").load()
        receipt = journal.append(_runtime(service).run_cycle(policy))
        if raw:
            output(json.dumps(receipt.model_dump(mode="json"), ensure_ascii=False))
        elif receipt.delivered_count:
            output(f"Цикл завершён. Доставлено сообщений: {receipt.delivered_count}.")
        else:
            output(f"Цикл завершён без новых сообщений. Причина: {receipt.reason}.")
        return 0

    if command == "receipts":
        rows = journal.list()
        if raw:
            output(json.dumps([row.model_dump(mode="json") for row in rows], ensure_ascii=False))
        elif not rows:
            output("Квитанций Daily Runtime пока нет.")
        else:
            output("Последние циклы:\n" + "\n".join(f"{index}. {row.started_at.astimezone().strftime('%d.%m.%Y %H:%M')} — {row.result}; {row.reason}" for index, row in enumerate(reversed(rows[-10:]), 1)))
        return 0

    raise ValueError(f"unknown runtime command: {command}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Masha Home Daily Runtime")
    parser.add_argument("command", choices=("status", "run", "receipts"))
    parser.add_argument("--raw", action="store_true")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()
    raise SystemExit(run_command(args.command, project_root=args.project_root, raw=args.raw))


if __name__ == "__main__":
    main()
