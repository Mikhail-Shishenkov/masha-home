"""Human-readable local CLI for skill discovery and registration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.conversation.cli import PROJECT_ROOT

from .autonomy import (
    ActionAutonomyEngine,
    ActionAutonomyPolicyStore,
    ActionAutonomyService,
    ActionDecision,
    ActionPolicyError,
    ActionRequest,
)
from .models import SkillCapability, SkillDescriptor, SkillIntegrity, SkillRisk
from .registry import SkillRegistry, SkillRegistryError


STATUS_LABELS = {
    SkillIntegrity.UNREGISTERED: "найден, не зарегистрирован",
    SkillIntegrity.VERIFIED: "зарегистрирован и проверен",
    SkillIntegrity.MODIFIED: "изменён после регистрации",
    SkillIntegrity.MISSING: "пакет отсутствует",
    SkillIntegrity.INVALID: "некорректный пакет",
}


def build_registry(project_root: Path = PROJECT_ROOT) -> SkillRegistry:
    return SkillRegistry(
        skills_root=project_root / "skills",
        state_path=project_root / "local-data" / "config" / "skills.json",
    )


def build_autonomy_service(
    registry: SkillRegistry,
    project_root: Path = PROJECT_ROOT,
) -> ActionAutonomyService:
    return ActionAutonomyService(
        store=ActionAutonomyPolicyStore(
            project_root / "local-data" / "config" / "action-autonomy.json"
        ),
        registry=registry,
    )


def run_command(
    command: str,
    *,
    skill_id: str | None = None,
    registry: SkillRegistry,
    autonomy: ActionAutonomyService | None = None,
    arguments: tuple[str, ...] = (),
    raw: bool = False,
    output=print,
) -> int:
    try:
        if command == "list":
            rows = registry.list()
            if raw:
                output(json.dumps([row.model_dump(mode="json") for row in rows], ensure_ascii=False))
            elif not rows:
                output("Навыков пока нет. Добавь пакет в папку skills и выполни skills register <имя>.")
            else:
                output(
                    "Навыки Маши:\n\n"
                    + "\n\n".join(_summary(index, row) for index, row in enumerate(rows, 1))
                )
            return 0

        if command == "policy":
            autonomy = _require_autonomy(autonomy)
            action = arguments[0] if arguments else "status"
            if action == "on":
                policy = autonomy.set_enabled(True)
            elif action == "off":
                policy = autonomy.set_enabled(False)
            elif action == "level" and len(arguments) == 2:
                policy = autonomy.set_level(int(arguments[1]))
            elif action == "status":
                policy = autonomy.policy()
            else:
                output("Команды: skills policy status|on|off|level <0-4>.")
                return 2
            if raw:
                output(json.dumps(policy.model_dump(mode="json"), ensure_ascii=False))
            else:
                output(_policy_details(policy))
            return 0

        if command == "permissions":
            autonomy = _require_autonomy(autonomy)
            grants = autonomy.grants()
            if raw:
                output(json.dumps([item.model_dump(mode="json") for item in grants], ensure_ascii=False))
            elif not grants:
                output("Постоянных разрешений пока нет.")
            else:
                output(
                    "Постоянные разрешения Маши:\n\n"
                    + "\n\n".join(
                        f"{index}. {item.skill_id}: {item.capability.value}\n"
                        f"   Область: {item.scope} · до уровня {item.maximum_autonomy_level}"
                        for index, item in enumerate(grants, 1)
                    )
                )
            return 0

        if command == "grant":
            autonomy = _require_autonomy(autonomy)
            if len(arguments) not in {4, 5}:
                output("Использование: skills grant <skill> <capability> <scope> <level> [risk].")
                return 2
            grant = autonomy.grant(
                skill_id=arguments[0],
                capability=SkillCapability(arguments[1]),
                scope=arguments[2],
                maximum_autonomy_level=int(arguments[3]),
                maximum_risk=SkillRisk(arguments[4]) if len(arguments) == 5 else None,
            )
            if raw:
                output(json.dumps(grant.model_dump(mode="json"), ensure_ascii=False))
            else:
                output(
                    f"Разрешение сохранено: {grant.skill_id} может использовать "
                    f"{grant.capability.value} в области {grant.scope} до уровня "
                    f"{grant.maximum_autonomy_level}. Само действие ещё не запускалось."
                )
            return 0

        if command == "revoke":
            autonomy = _require_autonomy(autonomy)
            if len(arguments) != 1:
                output("Использование: skills revoke <номер>.")
                return 2
            grants = autonomy.grants()
            try:
                grant = grants[int(arguments[0]) - 1]
            except (ValueError, IndexError):
                output("Выбери номер из skills permissions.")
                return 2
            policy = autonomy.revoke(grant.grant_id)
            if raw:
                output(json.dumps(policy.model_dump(mode="json"), ensure_ascii=False))
            else:
                output("Постоянное разрешение отозвано. Новое действие потребует подтверждения.")
            return 0

        if command == "check":
            autonomy = _require_autonomy(autonomy)
            if len(arguments) not in {4, 5}:
                output("Использование: skills check <skill> <capability> <scope> <level> [risk].")
                return 2
            descriptor = registry.inspect(arguments[0])
            if descriptor.manifest is None:
                raise ActionPolicyError("skill manifest is unavailable")
            risk = (
                SkillRisk(arguments[4])
                if len(arguments) == 5
                else descriptor.manifest.risk_level
            )
            evaluation = ActionAutonomyEngine().evaluate(
                ActionRequest(
                    skill_id=arguments[0],
                    capability=SkillCapability(arguments[1]),
                    scope=arguments[2],
                    required_autonomy_level=int(arguments[3]),
                    risk_level=risk,
                ),
                policy=autonomy.policy(),
                registry=registry,
            )
            if raw:
                output(json.dumps(evaluation.model_dump(mode="json"), ensure_ascii=False))
            else:
                output(_evaluation_details(evaluation.decision, evaluation.reason))
            return 0

        if skill_id is None:
            output("Укажи имя навыка.")
            return 2

        if command == "show":
            row = registry.inspect(skill_id)
            if raw:
                output(json.dumps(row.model_dump(mode="json"), ensure_ascii=False))
            else:
                output(_details(row))
            return 0

        if command == "verify":
            row = registry.verify(skill_id)
            if raw:
                output(json.dumps(row.model_dump(mode="json"), ensure_ascii=False))
            else:
                output(f"Навык «{row.manifest.name}» проверен. Статус: {STATUS_LABELS[row.integrity]}.")
            return 0

        if command == "register":
            registered = registry.register(skill_id)
            if raw:
                output(json.dumps(registered.model_dump(mode="json"), ensure_ascii=False))
            else:
                output(
                    f"Навык «{skill_id}» зарегистрирован локально. "
                    "Это ещё не разрешение на выполнение действий."
                )
            return 0
    except (SkillRegistryError, ActionPolicyError, ValueError) as error:
        output(f"Не удалось обработать навык: {error}")
        return 1
    raise ValueError(f"unknown skills command: {command}")


def _summary(index: int, row: SkillDescriptor) -> str:
    name = row.skill_id if row.manifest is None else row.manifest.name
    risk = "неизвестен" if row.manifest is None else row.manifest.risk_level.value
    return f"{index}. {name}\n   {STATUS_LABELS[row.integrity]} · риск: {risk}"


def _details(row: SkillDescriptor) -> str:
    if row.manifest is None:
        return f"Навык: {row.skill_id}\nСтатус: {STATUS_LABELS[row.integrity]}\nОшибка: {row.error}"
    manifest = row.manifest
    capabilities = ", ".join(item.value for item in manifest.capabilities) or "нет"
    scopes = ", ".join(manifest.requested_scopes) or "не запрошены"
    return (
        f"Навык: {manifest.name}\n"
        f"Версия: {manifest.version}\n"
        f"Статус: {STATUS_LABELS[row.integrity]}\n"
        f"Описание: {manifest.description}\n"
        f"Запрашиваемые возможности: {capabilities}\n"
        f"Области: {scopes}\n"
        f"Риск: {manifest.risk_level.value}\n"
        f"Максимальная автономность: {manifest.maximum_autonomy_level} "
        "(декларация, не разрешение)\n"
        f"Проверка результата: {manifest.verification}"
    )


def _require_autonomy(value: ActionAutonomyService | None) -> ActionAutonomyService:
    if value is None:
        raise ActionPolicyError("action autonomy service is unavailable")
    return value


def _policy_details(policy) -> str:
    enabled = "включена" if policy.enabled else "выключена"
    level_labels = {
        0: "только советовать",
        1: "наблюдать и диагностировать",
        2: "безопасные обратимые действия",
        3: "ограниченные многошаговые задачи",
        4: "заранее разрешённые локальные routines",
    }
    return (
        "Автономность действий\n"
        f"Состояние: {enabled}\n"
        f"Уровень: {policy.maximum_autonomy_level} — "
        f"{level_labels[policy.maximum_autonomy_level]}\n"
        f"Постоянных разрешений: {len(policy.grants)}\n"
        "Наличие разрешения не запускает навык само по себе."
    )


def _evaluation_details(decision: ActionDecision, reason: str) -> str:
    labels = {
        ActionDecision.ALLOW: "Разрешено текущими постоянными границами",
        ActionDecision.REQUIRE_CONFIRMATION: "Нужно подтверждение Миши",
        ActionDecision.DENY: "Запрещено текущей архитектурой или настройками",
    }
    return f"{labels[decision]}. Причина: {reason}. Действие не запускалось."


def main() -> None:
    parser = argparse.ArgumentParser(description="Masha Home local skill registry")
    parser.add_argument(
        "command",
        nargs="?",
        default="list",
        choices=(
            "list", "show", "verify", "register", "policy", "permissions",
            "grant", "revoke", "check",
        ),
    )
    parser.add_argument("arguments", nargs="*")
    parser.add_argument("--raw", action="store_true")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()
    registry = build_registry(args.project_root)
    raise SystemExit(
        run_command(
            args.command,
            skill_id=args.arguments[0] if args.arguments else None,
            arguments=tuple(args.arguments),
            registry=registry,
            autonomy=build_autonomy_service(registry, args.project_root),
            raw=args.raw,
        )
    )


if __name__ == "__main__":
    main()
