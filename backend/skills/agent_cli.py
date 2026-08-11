"""Read-only human view of bounded Agent Loop receipts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.conversation.cli import PROJECT_ROOT

from .agent_loop import AgentRunReceipt, AgentRunStore, AgentRunStatus, AgentStepStatus


STATUS_LABELS = {
    AgentRunStatus.RUNNING: "выполняется",
    AgentRunStatus.AWAITING_CONFIRMATION: "ждёт подтверждения",
    AgentRunStatus.COMPLETED: "завершено и проверено",
    AgentRunStatus.DENIED: "запрещено policy",
    AgentRunStatus.FAILED: "не выполнено",
    AgentRunStatus.BUDGET_EXHAUSTED: "остановлено по лимиту",
}


def build_store(project_root: Path = PROJECT_ROOT) -> AgentRunStore:
    return AgentRunStore(project_root / "local-data" / "runtime" / "agent-runs.json")


def run_command(
    command: str,
    *,
    store: AgentRunStore,
    number: str | None = None,
    raw: bool = False,
    output=print,
) -> int:
    rows = store.list()
    if command == "runs":
        if raw:
            output(json.dumps([item.model_dump(mode="json") for item in rows], ensure_ascii=False))
        elif not rows:
            output("Агентных запусков пока нет.")
        else:
            output(
                "Последние агентные задачи:\n\n"
                + "\n\n".join(
                    f"{index}. {item.goal}\n   {STATUS_LABELS[item.status]}"
                    for index, item in enumerate(reversed(rows), 1)
                )
            )
        return 0
    if command == "show":
        try:
            receipt = tuple(reversed(rows))[int(number or "0") - 1]
        except (ValueError, IndexError):
            output("Выбери номер из agent runs.")
            return 2
        if raw:
            output(json.dumps(receipt.model_dump(mode="json"), ensure_ascii=False))
        else:
            output(_details(receipt))
        return 0
    raise ValueError(f"unknown agent command: {command}")


def _details(receipt: AgentRunReceipt) -> str:
    steps = []
    for index, step in enumerate(receipt.steps, 1):
        if step.status is AgentStepStatus.VERIFIED:
            state = "проверено"
        elif step.status is AgentStepStatus.AWAITING_CONFIRMATION:
            state = "нужно подтверждение"
        elif step.status is AgentStepStatus.DENIED:
            state = "запрещено"
        elif step.status is AgentStepStatus.EXECUTING:
            state = "прервано во время выполнения"
        else:
            state = "не выполнено"
        steps.append(f"{index}. {step.title} — {state}")
    rendered_steps = "\n".join(steps) if steps else "Шаги ещё не начинались."
    reason = receipt.terminal_reason or "нет"
    return (
        f"Агентная задача: {receipt.goal}\n"
        f"Статус: {STATUS_LABELS[receipt.status]}\n"
        f"Причина остановки: {reason}\n\n"
        f"Шаги:\n{rendered_steps}\n\n"
        "Технические IDs и hashes доступны только через --raw."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Masha Home bounded Agent Loop receipts")
    parser.add_argument("command", nargs="?", default="runs", choices=("runs", "show"))
    parser.add_argument("number", nargs="?")
    parser.add_argument("--raw", action="store_true")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()
    raise SystemExit(
        run_command(
            args.command,
            store=build_store(args.project_root),
            number=args.number,
            raw=args.raw,
        )
    )


if __name__ == "__main__":
    main()
