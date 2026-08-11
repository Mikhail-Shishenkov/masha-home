"""Human-readable local control surface for permissions and emergency stop."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from backend.conversation.cli import PROJECT_ROOT
from backend.runtime.safety import AutonomySafetyService, AutonomySafetyStore
from backend.temporal.proactive import ProactivePolicy

from .agent_loop import AgentRunStore
from .autonomy import ActionAutonomyPolicyStore
from .cli import build_registry
from .installer import SkillInstallProposalStore
from .permissions import PermissionControlService, PermissionsSnapshot


def build_service(project_root: Path = PROJECT_ROOT) -> PermissionControlService:
    root = Path(project_root)
    config = root / "local-data" / "config"
    proactive_path = config / "proactive-policy.json"
    proactive = (
        ProactivePolicy.model_validate(
            json.loads(proactive_path.read_text(encoding="utf-8"))
        )
        if proactive_path.exists()
        else ProactivePolicy()
    )
    return PermissionControlService(
        registry=build_registry(root),
        action_policy_store=ActionAutonomyPolicyStore(config / "action-autonomy.json"),
        safety=AutonomySafetyService(
            store=AutonomySafetyStore(config / "autonomy-safety.json")
        ),
        run_store=AgentRunStore(root / "local-data" / "runtime" / "agent-runs.json"),
        install_store=SkillInstallProposalStore(config / "skill-installs.json"),
        proactive_policy=proactive,
        background_runtime_running=_process_from_lock_is_running(
            root / "local-data" / "runtime" / "proactive-daemon.lock"
        ),
    )


def run_command(
    command: str,
    *,
    service: PermissionControlService,
    arguments: tuple[str, ...] = (),
    raw: bool = False,
    output=print,
) -> int:
    if command == "stop":
        state = service.safety.engage(" ".join(arguments) or "manual_emergency_stop")
        if raw:
            output(json.dumps(state.model_dump(mode="json"), ensure_ascii=False))
        else:
            output(
                "Аварийная остановка включена. Новые шаги навыков и proactive-циклы "
                "заблокированы. Разрешения и настройки сохранены, но сейчас не действуют."
            )
        return 0
    if command == "resume":
        state = service.safety.release()
        if raw:
            output(json.dumps(state.model_dump(mode="json"), ensure_ascii=False))
        else:
            output(
                "Аварийная остановка снята. Настройки и разрешения не менялись; "
                "фоновые процессы не запускались автоматически."
            )
        return 0

    snapshot = service.snapshot()
    if raw:
        output(json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False))
        return 0
    if command == "status":
        output(_status(snapshot))
        return 0
    if command == "skills":
        output(_skills(snapshot))
        return 0
    if command == "grants":
        output(_grants(snapshot))
        return 0
    if command == "pending":
        output(_pending(snapshot))
        return 0
    raise ValueError(f"unknown permissions command: {command}")


def _status(snapshot: PermissionsSnapshot) -> str:
    stopped = snapshot.safety.emergency_stop_engaged
    action = snapshot.action_autonomy
    proactive = snapshot.proactive_autonomy
    lines = [
        "Контроль Маши",
        "",
        f"Аварийная остановка: {'ВКЛЮЧЕНА' if stopped else 'выключена'}",
    ]
    if stopped:
        lines.append(f"Причина: {snapshot.safety.reason}")
    lines += [
        f"Действия навыков: {'разрешены policy' if action.enabled else 'отключены'} · уровень {action.maximum_autonomy_level}",
        f"Действующих постоянных разрешений: {action.grants_effective} из {action.grants_total}",
        f"Инициативность: {'включена' if proactive.enabled else 'выключена'} · уровень {proactive.proactive_level}",
        f"Фоновый runtime: {'работает' if proactive.background_runtime_running else 'не запущен'} · режим {proactive.runtime_mode}",
        f"Навыков найдено: {len(snapshot.skills)}",
        f"Ожидают решения: {len(snapshot.pending)}",
        f"Активных или ожидающих подтверждения agent-задач: {snapshot.active_agent_runs}",
        "",
        "Аварийная остановка имеет приоритет над всеми grants и policy, но не удаляет их.",
    ]
    return "\n".join(lines)


def _skills(snapshot: PermissionsSnapshot) -> str:
    if not snapshot.skills:
        return "Навыков пока нет."
    rows = []
    for index, item in enumerate(snapshot.skills, 1):
        version = "без версии" if item.version is None else item.version
        support = "подключён к runtime" if item.runtime_supported else "нет безопасного runtime-adapter"
        rows.append(
            f"{index}. {item.name} · {version}\n"
            f"   Целостность: {item.integrity.value} · {support}\n"
            f"   Возможности: {', '.join(value.value for value in item.capabilities) or 'нет'}"
        )
    return "Навыки Маши:\n\n" + "\n\n".join(rows)


def _grants(snapshot: PermissionsSnapshot) -> str:
    if not snapshot.grants:
        return "Постоянных разрешений пока нет."
    return "Постоянные разрешения:\n\n" + "\n\n".join(
        f"{index}. {item.skill_id}: {item.capability.value}\n"
        f"   Область: {item.scope} · разрешено до уровня {item.maximum_autonomy_level}"
        f" · сейчас до уровня {item.effective_autonomy_level}\n"
        f"   Сейчас: {'действует' if item.effective else 'не действует'}"
        + ("" if item.effective else f" · причина: {item.reason}")
        for index, item in enumerate(snapshot.grants, 1)
    )


def _pending(snapshot: PermissionsSnapshot) -> str:
    if not snapshot.pending:
        return "Ничего не ожидает решения."
    return "Ожидают решения:\n\n" + "\n\n".join(
        f"{index}. {item.title}\n   Тип: {item.kind.value} · статус: {item.status}"
        for index, item in enumerate(snapshot.pending, 1)
    )


def _process_from_lock_is_running(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        os.kill(int(path.read_text(encoding="ascii")), 0)
        return True
    except (OSError, ValueError):
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Masha Home permissions and safety")
    parser.add_argument(
        "command",
        nargs="?",
        default="status",
        choices=("status", "skills", "grants", "pending", "stop", "resume"),
    )
    parser.add_argument("arguments", nargs="*")
    parser.add_argument("--raw", action="store_true")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()
    raise SystemExit(
        run_command(
            args.command,
            service=build_service(args.project_root),
            arguments=tuple(args.arguments),
            raw=args.raw,
        )
    )


if __name__ == "__main__":
    main()
