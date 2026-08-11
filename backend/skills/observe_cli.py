"""Human-readable CLI for the bounded local Project Observer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.conversation.cli import PROJECT_ROOT
from backend.runtime.safety import AutonomySafetyStore

from .agent_loop import AgentRunStatus, AgentRunStore, BoundedAgentLoop
from .autonomy import ActionAutonomyPolicyStore
from .cli import build_registry
from .project_observer import ProjectObserverTool
from .project_observer_service import ProjectObservation, ProjectObserverService


def build_service(project_root: Path = PROJECT_ROOT) -> ProjectObserverService:
    root = Path(project_root).resolve(strict=True)
    return ProjectObserverService(
        agent_loop=BoundedAgentLoop(
            registry=build_registry(root),
            policy_store=ActionAutonomyPolicyStore(
                root / "local-data" / "config" / "action-autonomy.json"
            ),
            safety_store=AutonomySafetyStore(
                root / "local-data" / "config" / "autonomy-safety.json"
            ),
            run_store=AgentRunStore(root / "local-data" / "runtime" / "agent-runs.json"),
            tools=(ProjectObserverTool(root),),
        )
    )


def run_command(
    command: str,
    *,
    service: ProjectObserverService,
    path: str = ".",
    max_depth: int = 2,
    max_entries: int = 200,
    max_chars: int = 8_000,
    raw: bool = False,
    output=print,
) -> int:
    operations = {
        "tree": ("list_tree", {"path": path, "max_depth": max_depth, "max_entries": max_entries}),
        "read": ("read_text", {"path": path, "max_chars": max_chars}),
        "inspect": ("inspect_path", {"path": path}),
    }
    operation, inputs = operations[command]
    observation = service.observe(operation, inputs)
    if raw:
        output(json.dumps(observation.model_dump(mode="json"), ensure_ascii=False))
    elif observation.output is not None:
        output(_render(command, observation.output))
    else:
        output(_blocked_message(observation))
    return 0 if observation.output is not None else 1


def _render(command: str, value) -> str:
    if command == "tree":
        rows = value["entries"]
        lines = [f"Проект: {value['root']}", ""]
        for item in rows:
            marker = "[папка]" if item["type"] == "directory" else "[файл]"
            lines.append(f"{marker} {item['path']}")
        if value["truncated"]:
            lines.extend(("", "Показана только ограниченная часть дерева."))
        return "\n".join(lines)
    if command == "read":
        suffix = "\n\n[текст ограничен по длине]" if value["truncated"] else ""
        return f"Файл: {value['path']}\n\n{value['content']}{suffix}"
    kind = "папка" if value["type"] == "directory" else "файл"
    lines = [f"Путь: {value['path']}", f"Тип: {kind}"]
    if value["type"] == "file":
        lines.append(f"Размер: {value['size_bytes']} байт")
        lines.append(f"SHA-256: {value['sha256']}")
    return "\n".join(lines)


def _blocked_message(observation: ProjectObservation) -> str:
    receipt = observation.receipt
    reason = receipt.terminal_reason or "unknown"
    if receipt.status is AgentRunStatus.AWAITING_CONFIRMATION:
        return (
            "Наблюдение не запускалось: требуется явное разрешение. "
            "Зарегистрируй навык и настрой local_read через команды skills."
        )
    return f"Наблюдение не выполнено. Причина: {reason}."


def main() -> None:
    parser = argparse.ArgumentParser(description="Masha Home bounded Project Observer")
    parser.add_argument("command", choices=("tree", "read", "inspect"))
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--max-depth", type=int, default=2)
    parser.add_argument("--max-entries", type=int, default=200)
    parser.add_argument("--max-chars", type=int, default=8_000)
    parser.add_argument("--raw", action="store_true")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()
    raise SystemExit(
        run_command(
            args.command,
            service=build_service(args.project_root),
            path=args.path,
            max_depth=args.max_depth,
            max_entries=args.max_entries,
            max_chars=args.max_chars,
            raw=args.raw,
        )
    )


if __name__ == "__main__":
    main()
