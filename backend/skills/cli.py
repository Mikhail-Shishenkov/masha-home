"""Human-readable local CLI for skill discovery and registration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.conversation.cli import PROJECT_ROOT

from .models import SkillDescriptor, SkillIntegrity
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


def run_command(
    command: str,
    *,
    skill_id: str | None = None,
    registry: SkillRegistry,
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
    except SkillRegistryError as error:
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Masha Home local skill registry")
    parser.add_argument("command", nargs="?", default="list", choices=("list", "show", "verify", "register"))
    parser.add_argument("skill_id", nargs="?")
    parser.add_argument("--raw", action="store_true")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()
    raise SystemExit(
        run_command(
            args.command,
            skill_id=args.skill_id,
            registry=build_registry(args.project_root),
            raw=args.raw,
        )
    )


if __name__ == "__main__":
    main()
