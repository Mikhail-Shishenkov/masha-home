"""Human-readable rendering for local memory CLI; no storage logic lives here."""

from __future__ import annotations

from datetime import datetime


TYPE_NAMES = {"fact": "факт", "decision": "решение", "commitment": "обязательство", "episode": "эпизод"}
STATUS_NAMES = {"active": "активно", "open": "активно", "current": "актуально", "superseded": "заменено", "hidden": "скрыто", "visible": "активно"}
SOURCE_NAMES = {"explicit_user_input": "ты сам попросил это запомнить", "conversation": "разговор", "system": "система", "inference": "вывод системы"}


def summary(view) -> str:
    data = view.payload
    if view.record_type == "fact":
        return f"{data['subject'].capitalize()}: {data['key']} — {data['value']}"
    if view.record_type == "decision":
        return data["decision"]
    if view.record_type == "commitment":
        return data["text"]
    return data["summary"]


def date(value: str | None) -> str:
    if not value:
        return "дата не указана"
    try:
        return datetime.fromisoformat(value).strftime("%d.%m.%Y")
    except ValueError:
        return value


def status(view) -> str:
    if view.payload.get("visibility") == "hidden":
        return "скрыто из обычной памяти"
    return STATUS_NAMES.get(view.status or "", view.status or "без статуса")


def list_views(views) -> str:
    active = [view for view in views if view.payload.get("visibility", "visible") == "visible" and view.status != "superseded"]
    if not active:
        return "Обычная память пока пуста."
    lines = ["Что я помню:"]
    for index, view in enumerate(active, 1):
        lines += [f"{index}. {summary(view)}", f"   {TYPE_NAMES[view.record_type]} · {status(view)} · {date(view.created_at)}"]
    return "\n".join(lines)


def detail(view) -> str:
    lines = ["Память:", f"«{summary(view)}».", "", f"Тип: {TYPE_NAMES[view.record_type]}", f"Статус: {status(view)}", f"Источник: {SOURCE_NAMES.get(view.source or '', view.source or 'не указан')}", f"Дата: {date(view.created_at)}"]
    if view.supersedes_id:
        lines.append("Эта запись заменила более раннюю запись.")
    if view.superseded_by:
        lines.append("Эта запись заменена более новой; она осталась в истории.")
    return "\n".join(lines)


def preview(operation: str, view, replacement=None) -> str:
    action = {"archive": "скрыть из обычной памяти", "forget": "забыть в обычном контексте", "edit": "изменить", "supersede": "заменить новой записью"}[operation]
    lines = [f"Предлагаю {action}:", f"«{summary(view)}». "]
    if replacement is not None:
        clone = view.model_copy(update={"payload": replacement})
        lines += ["", "Станет:", f"«{summary(clone)}». "]
    if operation in {"archive", "forget"}:
        lines += ["", "Это не удаление: запись останется в истории и audit."]
    if operation == "supersede":
        lines += ["", "Старая запись останется в истории, новая станет актуальной."]
    lines += ["", "Применить? Напиши: memory confirm"]
    return "\n".join(lines)


def history(view) -> str:
    if not view.audit_events:
        return "История изменений для этой записи пока пуста."
    lines = ["История памяти:"]
    labels = {"confirmed_memory": "сохранено после подтверждения", "memory_edit": "изменено", "memory_archive": "скрыто из обычной памяти", "memory_forget": "забыто в обычном контексте", "memory_supersede": "заменено новой записью"}
    for event in view.audit_events:
        lines += [f"{date(event['occurred_at'])} — {labels.get(event['action'], event['action'])}."]
    return "\n".join(lines)
