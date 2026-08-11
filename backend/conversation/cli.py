"""Small offline terminal entry point for the existing conversation vertical slice."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from backend.identity.identity_kernel import (
    IdentityKernel,
    IdentityMemoryVersionMismatchError,
)
from backend.identity.identity_store import IdentityStore
from backend.llm.model_router import ModelRouter
from backend.llm.ollama_provider import OllamaProvider
from backend.llm.model_profiles import ModelProfileStore
from backend.memory.memory_retriever import MemoryRetriever
from backend.memory.sqlite_repository import MemorySqliteRepository
from backend.memory.working_memory import WorkingMemory
from backend.memory.confirmed_memory_service import ConfirmedMemoryService
from backend.memory.memory_management import MemoryManagementService, MemoryMutationOperation
from backend.memory.memory_presentation import detail, history, list_views, preview, summary
from backend.memory.shared_continuity import SharedContinuityService
from backend.temporal.temporal_engine import MOSCOW, TemporalEngine
from backend.temporal.temporal_runtime import TemporalRuntime
from backend.temporal.proactive import ProactiveDecisionEngine, ProactivePolicy, ProactivePolicyStore
from backend.temporal.proactive_interaction import ProactiveInteractionService, ProactiveInteractionStore, ProactiveInteractionUnavailableError
from backend.temporal.proactive_daemon import ProactiveDaemon
from backend.temporal.proactive_runtime import ControlledProactiveRuntime
from backend.runtime.daily_runtime import DailyRuntime, DailyRuntimeJournal

from .conversation_service import ConversationService, ConversationUnavailableError
from .conversation_store import ConversationStore
from .memory_intent import MemoryIntentHandler, MemoryProposalStore, ProposalStatus


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROJECT_ID = "project_masha_home"
EXIT_COMMANDS = {":exit", ":quit"}


def build_service(*, project_root: Path = PROJECT_ROOT) -> ConversationService:
    """Assemble the local SQLite memory, identity, router, and Ollama provider."""
    memory_store = MemorySqliteRepository(project_root / "local-data" / "memory" / "masha.sqlite3")
    identity_kernel = IdentityKernel(
        IdentityStore(project_root / "identity" / "masha.identity.json")
    )
    identity_kernel.validate_memory_identity(memory_store)
    memory_management = MemoryManagementService(memory_store)
    shared_continuity = SharedContinuityService(memory_store)
    profiles = ModelProfileStore(project_root / "local-data" / "config" / "models.json")
    return ConversationService(
        identity_kernel=identity_kernel,
        memory_retriever=MemoryRetriever(memory_store),
        working_memory=WorkingMemory(max_items=6),
        router=ModelRouter([OllamaProvider()]),
        history=ConversationStore(project_root / "local-data" / "conversations" / "history.json"),
        memory_intent_handler=MemoryIntentHandler(
            proposal_store=MemoryProposalStore(project_root / "local-data" / "memory-proposals.json"),
            confirmed_memory=ConfirmedMemoryService(memory_store),
            memory_management=memory_management,
            shared_continuity=shared_continuity,
        ),
        model_profiles=profiles,
        proactive_interactions=ProactiveInteractionStore(memory_store),
        shared_continuity=shared_continuity,
    )


def run_cli(
    service: ConversationService,
    *,
    project_id: str = DEFAULT_PROJECT_ID,
    conversation_id: str | None = None,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
    memory_management: MemoryManagementService | None = None,
    proposal_store: MemoryProposalStore | None = None,
) -> None:
    """Run one terminal chat; the latest JSON conversation is reopened by default."""
    active_id = conversation_id
    if active_id is None:
        latest = service.history.latest()
        active_id = latest.id if latest is not None else None

    if active_id is None:
        output_fn("New local conversation. The id will appear after the first reply.")
    else:
        output_fn(f"Continuing local conversation: {active_id}")
    output_fn("Type :exit to stop. History is local and is not long-term memory.")

    while True:
        try:
            user_message = input_fn("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            output_fn("\nConversation stopped.")
            return
        if not user_message:
            continue
        if user_message.lower() in EXIT_COMMANDS:
            output_fn("Conversation stopped.")
            return
        if user_message.startswith("model "):
            _run_model_command(user_message[6:], service=service, output_fn=output_fn)
            continue
        if user_message.startswith("time"):
            _run_time_command(user_message, service=service, conversation_id=active_id, output_fn=output_fn)
            continue
        if user_message.startswith("commitments"):
            _run_commitments_command(user_message, service=service, output_fn=output_fn)
            continue
        if user_message.startswith("proactive"):
            _run_proactive_command(user_message[9:].strip(), service=service, output_fn=output_fn)
            continue
        if user_message.startswith("continuity"):
            _run_continuity_command(
                user_message[10:].strip(),
                service=service,
                conversation_id=active_id or "continuity-cli",
                output_fn=output_fn,
            )
            continue
        if user_message.startswith("memory ") and memory_management is not None and proposal_store is not None:
            _run_memory_command(
                user_message[7:], memory_management=memory_management,
                proposal_store=proposal_store, conversation_id=active_id or "memory-cli", output_fn=output_fn,
            )
            continue
        try:
            active_id, response = service.send(
                user_message,
                project_id=project_id,
                conversation_id=active_id,
            )
        except ConversationUnavailableError:
            output_fn("Masha is unavailable: local Ollama is not responding. No message was sent outside this computer.")
            continue
        output_fn(f"Conversation id: {active_id}")
        output_fn(f"Masha> {response}")


def _run_continuity_command(
    command: str,
    *,
    service: ConversationService,
    conversation_id: str,
    output_fn: Callable[[str], None],
) -> None:
    """Human-readable access to confirmed shared moments and unfinished threads."""
    continuity = service.shared_continuity
    handler = service.memory_intent_handler
    if continuity is None or handler is None:
        output_fn("Общая история сейчас недоступна.")
        return
    raw = "--raw" in command
    clean = command.replace("--raw", "").strip()
    parts = clean.split(maxsplit=1)
    action = parts[0] if parts and parts[0] else "status"
    argument = parts[1] if len(parts) > 1 else ""
    if action in {"status", "show", "list"}:
        output_fn(continuity.raw() if raw else continuity.render())
        return
    if action == "open" and argument:
        proposal = continuity.propose_open_thread(
            handler.proposal_store,
            text=argument,
            conversation_id=conversation_id,
        )
        output_fn(
            f"Оставить открытую нить:\n«{argument}»?\n"
            + (f"Proposal: {proposal.id}" if raw else "Подтверди командой: continuity confirm")
        )
        return
    if action == "resolve" and argument:
        try:
            proposal = continuity.propose_resolve_thread(
                handler.proposal_store,
                query=argument,
                conversation_id=conversation_id,
            )
        except LookupError:
            output_fn("Не нашла такую открытую нить.")
            return
        except ValueError:
            output_fn("Нашла несколько похожих нитей. Уточни формулировку.")
            return
        output_fn(
            f"Закрыть открытую нить:\n«{argument}»?\n"
            + (f"Proposal: {proposal.id}" if raw else "Подтверди командой: continuity confirm")
        )
        return
    if action in {"confirm", "reject"}:
        pending = [
            item
            for item in handler.proposal_store.pending_for_conversation(conversation_id)
            if item.operation in {"continuity_create", "continuity_update"}
        ]
        proposal = handler.proposal_store.get(argument) if argument else pending[0] if len(pending) == 1 else None
        if proposal is None or proposal.conversation_id != conversation_id:
            output_fn("Не нашла одно подходящее предложение общей нити.")
            return
        if action == "reject":
            handler.proposal_store.set_status(proposal.id, ProposalStatus.CANCELLED)
            output_fn("Хорошо, общую нить не меняю.")
            return
        try:
            continuity.confirm_proposal(proposal, handler.proposal_store)
        except Exception as error:
            output_fn(f"Не смогла обновить общую нить: {error}")
            return
        output_fn("Готово. Наша общая нить обновлена.")
        return
    output_fn(
        "Команды: continuity, continuity open <тема>, continuity resolve <тема>, "
        "continuity confirm, continuity reject. Добавь --raw для диагностики."
    )


def _run_memory_command(command: str, *, memory_management: MemoryManagementService,
                        proposal_store: MemoryProposalStore, conversation_id: str,
                        output_fn: Callable[[str], None]) -> None:
    """Small local diagnostic surface over the same SQLite/proposal contracts."""
    raw = "--raw" in command or "--debug" in command
    command = command.replace("--raw", "").replace("--debug", "").strip()
    parts = command.split(maxsplit=2)
    action = parts[0] if parts else ""
    if action in {"list", "find"}:
        query = " ".join(parts[1:]) if action == "find" and len(parts) > 1 else None
        views = memory_management.list(query=query, include_hidden=raw)
        if raw:
            output_fn(json.dumps([view.model_dump(mode="json") for view in views], ensure_ascii=False))
        elif action == "find":
            output_fn("Ничего не нашла." if not views else "Нашла:\n" + "\n".join(f"- {summary(view)} ({view.record_type})" for view in views if view.payload.get("visibility") == "visible"))
        else:
            output_fn(list_views(views))
        return
    if action in {"get", "history"} and len(parts) > 1:
        view = memory_management.get(parts[1])
        output_fn(json.dumps(None if view is None else view.model_dump(mode="json"), ensure_ascii=False) if raw else ("Не нашла такую запись." if view is None else history(view) if action == "history" else detail(view)))
        return
    if action == "conflicts":
        groups = memory_management.conflicts()
        output_fn(json.dumps([[item.model_dump(mode="json") for item in group] for group in groups], ensure_ascii=False) if raw else ("Противоречий не нашла." if not groups else "Обнаружены противоречия:\n" + "\n".join(" / ".join(f"«{summary(item)}»" for item in group) for group in groups)))
        return
    if action in {"archive", "forget"} and len(parts) > 1:
        proposal = memory_management.propose(
            proposal_store, operation=MemoryMutationOperation(action), record_id=parts[1], conversation_id=conversation_id,
        )
        output_fn(preview(action, memory_management.get(parts[1])))
        return
    if action in {"edit", "supersede"} and len(parts) > 2:
        current = memory_management.get(parts[1])
        if current is None:
            output_fn("Не нашла такую запись.")
            return
        replacement = dict(current.payload)
        field = "value" if current.record_type == "fact" else "decision" if current.record_type == "decision" else None
        if field is None:
            output_fn("Сейчас можно изменить только факт или решение.")
            return
        replacement[field] = parts[2]
        if action == "supersede":
            from uuid import uuid4
            replacement["id"] = f"{current.record_type}_{uuid4()}"
            replacement["supersedes_id"] = current.record_id
        proposal = memory_management.propose(
            proposal_store, operation=MemoryMutationOperation(action), record_id=parts[1], conversation_id=conversation_id,
            replacement_payload=replacement,
        )
        output_fn(preview(action, current, replacement))
        return
    if action in {"confirm", "reject"}:
        pending = [item for item in proposal_store.pending_for_conversation(conversation_id) if item.operation != "create"]
        proposal = proposal_store.get(parts[1]) if len(parts) > 1 else pending[0] if len(pending) == 1 else None
        if proposal is None or proposal.conversation_id != conversation_id:
            output_fn("No matching local memory proposal.")
            return
        if action == "reject":
            proposal_store.set_status(proposal.id, ProposalStatus.CANCELLED)
            output_fn("Хорошо, ничего не меняю.")
            return
        try:
            view = memory_management.confirm_proposal(proposal, proposal_store)
        except Exception as error:
            output_fn(f"Memory mutation failed; proposal remains pending: {error}")
            return
        output_fn(f"Applied {proposal.operation}: {view.record_id}")
        return
    output_fn("Команды: list, get <id>, find <текст>, history <id>, conflicts, archive|forget <id>, edit|supersede <id> <новый текст>, confirm, reject. Добавь --raw для диагностики.")


def _run_time_command(command: str, *, service: ConversationService, conversation_id: str | None, output_fn: Callable[[str], None]) -> None:
    context = service.temporal_engine.context(None if conversation_id is None else service.history.last_interaction_at(conversation_id))
    if "--raw" in command:
        output_fn(json.dumps(context.model_dump(mode="json"), ensure_ascii=False))
        return
    local = context.current_local_time.strftime("%d.%m.%Y, %H:%M")
    utc = context.current_utc_time.strftime("%d.%m.%Y, %H:%M")
    lines = ["Время:", f"Москва: {local}", f"UTC: {utc}"]
    if context.last_interaction_at is None:
        lines.append("Последнего разговора пока нет.")
    else:
        minutes = context.absence_duration_seconds // 60
        lines += [f"Последний разговор: {context.last_interaction_at.astimezone(MOSCOW).strftime('%d.%m.%Y, %H:%M')}", f"Тебя не было: {minutes // 60} ч {minutes % 60} мин"]
    output_fn("\n".join(lines))


def _run_model_command(command: str, *, service: ConversationService, output_fn: Callable[[str], None]) -> None:
    store = service.model_profiles
    if store is None:
        output_fn("Профили моделей не настроены."); return
    parts = command.split()
    action = parts[0] if parts else "current"
    provider = None
    if action == "list":
        active = store.get_active_profile().profile_id
        output_fn("Доступные модели:\n" + "\n".join(f"{'* ' if p.profile_id == active else '  '}{p.profile_id}\n  {p.model_id or 'не задана'}\n  {'включена' if p.enabled else 'отключена'}" for p in store.list_profiles())); return
    if action == "current":
        p = store.get_active_profile(); output_fn(f"Текущий профиль:\n{p.profile_id}\nМодель: {p.model_id}\nThink: {str(p.think).lower()}"); return
    if action == "use" and len(parts) == 2:
        old = store.get_active_profile()
        try:
            candidate = store.get_profile(parts[1])
            if not candidate.enabled: raise ValueError("профиль отключён")
            provider = service.router.get_provider(candidate.provider_id)
            if provider is None or not provider.is_available(): raise RuntimeError("Ollama недоступен")
            is_model_available = getattr(provider, "is_model_available", None)
            if not callable(is_model_available) or not is_model_available(candidate.model_id): raise RuntimeError(f"модель {candidate.model_id} недоступна")
            store.set_active_profile(candidate.profile_id)
            output_fn(f"Переключено на {candidate.profile_id} — {candidate.model_id}.")
        except (KeyError, OSError, ValueError, RuntimeError) as error:
            output_fn(f"Не удалось переключиться: {error}. Профиль {old.profile_id} не изменён.")
        return
    output_fn("Команды: model list, model current, model use <profile>.")


_PROACTIVE_REASONS = {
    "authorised": "настройки разрешают это сообщение",
    "proactive_disabled": "инициативность выключена",
    "level_below_checkin": "текущий уровень не разрешает check-in",
    "level_below_reminder": "текущий уровень не разрешает напоминания",
    "checkins_disabled": "check-in выключены",
    "absence_threshold_not_reached": "порог отсутствия ещё не достигнут",
    "quiet_hours": "сейчас тихие часы",
    "daily_limit": "дневной лимит сообщений исчерпан",
    "cooldown": "ещё действует пауза между сообщениями",
    "higher_priority_reminder": "есть более приоритетное напоминание",
    "background_disabled": "выбран ручной режим",
    "cycle_error": "цикл завершился ошибкой",
    "policy_suppressed": "настройки не разрешили сообщение",
    "external_event_not_implemented": "внешние события не подключены и всегда блокируются",
    "awaiting_user_response": "предыдущее сообщение ещё ждёт реакции",
    "cycle_delivery_limit": "за один цикл допускается только одно обращение",
    "reminders_disabled": "напоминания выключены",
    "local_model_unavailable": "локальная модель временно недоступна",
    "no_events": "значимых событий нет",
}


def _local_time_label(value: str | None) -> str:
    if not value:
        return "ещё не было"
    moment = datetime.fromisoformat(value).astimezone(MOSCOW)
    now = datetime.now(MOSCOW)
    return f"сегодня в {moment:%H:%M}" if moment.date() == now.date() else moment.strftime("%d.%m.%Y в %H:%M")


def _interaction_kind(row: dict) -> str:
    return "Check-in" if row.get("proactive_event_id") else "Напоминание"


def _interaction_state(state: str) -> str:
    return {
        "candidate": "готовится",
        "delivered": "ждёт реакции",
        "acknowledged": "подтверждено",
        "dismissed": "отклонено",
        "resolved": "закрыто ответом",
        "expired": "истекло",
    }.get(state, state)


def _run_proactive_command_legacy(command: str, *, service: ConversationService, output_fn: Callable[[str], None]) -> None:
    store = ProactiveInteractionStore(service.memory_retriever.memory_store)
    parts = command.split()
    action = parts[0] if parts else "status"
    policy_store = ProactivePolicyStore(service.model_profiles.path.parent / "proactive-policy.json")
    policy = policy_store.load()
    project_root = service.model_profiles.path.parents[2]
    daemon = ProactiveDaemon(project_root)
    if action in {"status", "settings"}:
        state = daemon.status()
        latest_receipt = journal.latest()
        if latest_receipt is not None and (
            not state.get("last_cycle")
            or latest_receipt.started_at > datetime.fromisoformat(state["last_cycle"])
        ):
            state = {
                **state,
                "last_cycle": latest_receipt.started_at.isoformat(),
                "last_result": latest_receipt.result,
                "last_reason": latest_receipt.reason,
                "last_error": latest_receipt.error,
            }
        output_fn(f"Daemon: {state.get('daemon', 'stopped')}\nРежим: {policy.runtime_mode}\nИнициативность: {'включена' if policy.enabled else 'выключена'}\nУровень: {policy.proactive_level}\nНапоминания: {'включены' if policy.allow_commitment_reminders else 'выключены'}\nCheck-in: {'включён' if policy.allow_checkins else 'выключен'}\nQuiet hours: {policy.quiet_hours_start or 'нет'}–{policy.quiet_hours_end or 'нет'}\nCooldown: {policy.cooldown_seconds // 3600} ч\nЛимит: {policy.daily_message_limit} в день\nПоследний цикл: {state.get('last_cycle', 'нет')}\nРезультат: {state.get('last_result', 'нет')}\nОшибка: {state.get('last_error') or 'нет'}\nСледующий цикл: {state.get('next_cycle', 'нет')}")
        return
    if action == "mode" and len(parts) == 2 and parts[1] in {"manual", "background"}:
        policy_store.save(policy.model_copy(update={"runtime_mode": parts[1]}))
        output_fn(f"Режим инициативности: {parts[1]}.")
        return
    if action == "checkins" and len(parts) == 2 and parts[1] in {"on", "off"}:
        enabled = parts[1] == "on"
        policy_store.save(policy.model_copy(update={"allow_checkins": enabled, "proactive_level": max(2, policy.proactive_level) if enabled else policy.proactive_level}))
        output_fn("Check-in включены." if enabled else "Check-in выключены.")
        return
    if action == "daemon" and len(parts) >= 2:
        if parts[1] == "start":
            if daemon.is_running():
                output_fn("Proactive daemon уже запущен."); return
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
            subprocess.Popen([sys.executable, "-m", "backend.temporal.proactive_daemon", "--project-root", str(project_root)], cwd=project_root, creationflags=flags, close_fds=True)
            output_fn("Proactive daemon запускается."); return
        if parts[1] == "stop":
            daemon.request_stop(); output_fn("Остановка proactive daemon запрошена."); return
        if parts[1] == "status":
            output_fn(json.dumps(daemon.status(), ensure_ascii=False) if "--raw" in parts else f"Daemon: {daemon.status().get('daemon', 'stopped')}"); return
    if action in {"on", "off"}:
        if action == "on":
            policy = policy.model_copy(update={
                "enabled": True,
                "proactive_level": max(1, policy.proactive_level),
                "allow_commitment_reminders": True,
                "maximum_reminders": max(1, policy.maximum_reminders),
                "daily_message_limit": max(1, policy.daily_message_limit),
            })
        else:
            policy = policy.model_copy(update={"enabled": False})
        policy_store.save(policy)
        output_fn("Инициативность включена." if action == "on" else "Инициативность выключена.")
        return
    if action == "level" and len(parts) == 2:
        try: updated = policy.model_copy(update={"proactive_level": int(parts[1])}); ProactivePolicy.model_validate(updated.model_dump())
        except (ValueError, TypeError): output_fn("Уровень должен быть числом от 0 до 5."); return
        policy_store.save(updated); output_fn(f"Уровень инициативности: {updated.proactive_level}."); return
    rows = store.list()
    if action in {"pending", "history"}:
        selected = [row for row in rows if action != "pending" or row["state"] in {"candidate", "delivered"}]
        if not selected:
            output_fn("Инициативных сообщений пока нет."); return
        output_fn("Инициативные сообщения:\n" + "\n".join(f"{i}. {row.get('message_text') or 'Напоминание подготовлено'}\n   Статус: {row['state']}" for i, row in enumerate(selected, 1))); return
    if action in {"acknowledge", "dismiss"} and len(parts) == 2:
        try: row = rows[int(parts[1]) - 1]
        except (ValueError, IndexError): output_fn("Выбери номер сообщения из списка."); return
        result = store.acknowledge(row["event_id"], service.temporal_engine.clock.now_utc()) if action == "acknowledge" else store.dismiss(row["event_id"], service.temporal_engine.clock.now_utc())
        output_fn("Поняла, отметила." if result["state"] == "acknowledged" else "Хорошо, больше не буду повторять это напоминание."); return
    if action in {"recover", "run"}:
        runtime = TemporalRuntime(service.memory_retriever.memory_store, service.temporal_engine)
        context = runtime.recover()
        if "--remind" in parts: policy = policy.model_copy(update={"enabled": True, "proactive_level": max(1, policy.proactive_level), "allow_commitment_reminders": True, "maximum_reminders": max(1, policy.maximum_reminders), "daily_message_limit": max(1, policy.daily_message_limit)})
        interaction = ProactiveInteractionService(store=store, identity_kernel=service.identity_kernel, router=service.router, model_profiles=service.model_profiles)
        document = service.memory_retriever.memory_store.read_document(); commitments = {item.id: item for item in document.commitments}
        delivered = []
        reminders_sent, last_delivery_at = store.delivery_stats(context.generated_at)
        for event in context.events:
            decision_engine = ProactiveDecisionEngine()
            decision = decision_engine.decide(
                event,
                policy,
                now=context.generated_at,
                reminders_sent=reminders_sent,
                last_reminder_at=last_delivery_at,
            )
            if decision.value == "remind":
                reason = "authorised"
            elif not policy.enabled:
                reason = "proactive_disabled"
            elif policy.proactive_level < 1 or not policy.allow_commitment_reminders:
                reason = "level_below_reminder"
            elif decision_engine._in_quiet_hours(context.generated_at, policy):
                reason = "quiet_hours"
            elif reminders_sent >= min(policy.maximum_reminders, policy.daily_message_limit):
                reason = "daily_limit"
            elif last_delivery_at is not None and (context.generated_at - last_delivery_at).total_seconds() < policy.cooldown_seconds:
                reason = "cooldown"
            else:
                reason = "policy_suppressed"
            previous = [item for item in service.memory_retriever.memory_store.list_audit_events() if item["action"] == "proactive_decision" and item["entity_id"] == event.event_id]
            trace = {"decision": decision.value, "reason": reason, "model_profile": service.model_profiles.get_active_profile().profile_id}
            if not previous or previous[-1]["payload"] != trace:
                service.memory_retriever.memory_store.record_event(action="proactive_decision", entity_type="temporal_event", entity_id=event.event_id, payload=trace)
            if decision.value != "remind": continue
            candidate = ProactiveDecisionEngine.candidate(event, commitment_text=commitments[event.source_commitment_id].text, temporal_context=service.temporal_engine.context(None), decision=decision, generated_at=context.generated_at)
            try:
                result = interaction.formulate(candidate)
                delivered.append(result.get("message_text") or "Напоминание подготовлено")
                if result["state"] == "delivered":
                    reminders_sent += 1
                    last_delivery_at = context.generated_at
            except ProactiveInteractionUnavailableError: output_fn("Локальная модель недоступна; состояние кандидата сохранено.")
        try:
            checkin = ControlledProactiveRuntime(history=service.history, temporal_engine=service.temporal_engine, repository=service.memory_retriever.memory_store, identity_kernel=service.identity_kernel, router=service.router, model_profiles=service.model_profiles).run_checkin_cycle(policy)
            if checkin.decision == "delivered" and checkin.message:
                delivered.append(checkin.message)
        except ProactiveInteractionUnavailableError:
            output_fn("Локальная модель недоступна; CHECK_IN остаётся кандидатом для следующей попытки.")
        output_fn("Нет разрешённых напоминаний." if not delivered else "\n".join(delivered)); return
    output_fn("Команды: proactive status|settings, proactive on|off, proactive checkins on|off, proactive level <0-5>, proactive mode manual|background, proactive run, proactive daemon start|stop|status, proactive pending, proactive acknowledge <номер>, proactive dismiss <номер>.")


def _run_proactive_command(command: str, *, service: ConversationService, output_fn: Callable[[str], None]) -> None:
    """Human-first proactive controls; technical IDs are exposed only with --raw."""
    parts = command.split()
    action = parts[0] if parts else "status"
    raw = "--raw" in parts
    repository = service.memory_retriever.memory_store
    store = ProactiveInteractionStore(repository)
    policy = ProactivePolicyStore(service.model_profiles.path.parent / "proactive-policy.json").load()
    daemon = ProactiveDaemon(service.model_profiles.path.parents[2])
    journal = DailyRuntimeJournal(service.model_profiles.path.parents[2] / "local-data" / "runtime" / "daily-runtime-receipts.json")

    if action in {"status", "settings"}:
        state = daemon.status()
        waiting = sum(row["state"] == "delivered" for row in store.list())
        if raw:
            output_fn(json.dumps({"policy": policy.model_dump(mode="json"), "daemon": {**state, "running": daemon.is_running()}, "waiting_for_response": waiting}, ensure_ascii=False))
            return
        result = {"delivered": "сообщение доставлено", "suppress": "новых сообщений нет", "manual_mode": "ручной режим", "error": "цикл завершился ошибкой"}.get(state.get("last_result"), "проверок ещё не было")
        lines = [
            f"Инициативность: {'включена' if policy.enabled else 'выключена'}",
            f"Режим: {policy.runtime_mode}",
            f"Уровень: {policy.proactive_level}",
            f"Check-in: {'включён' if policy.allow_checkins else 'выключен'}",
            f"Напоминания: {'включены' if policy.allow_commitment_reminders else 'выключены'}",
            f"Daemon: {'работает' if daemon.is_running() else 'не запущен'}",
            "",
            f"Последняя проверка: {_local_time_label(state.get('last_cycle'))}",
            f"Результат: {result}",
        ]
        reason = _PROACTIVE_REASONS.get(state.get("last_reason"), state.get("last_reason"))
        if reason:
            lines.append(f"Причина: {reason}")
        if state.get("last_error"):
            lines.append(f"Ошибка: {state['last_error']}")
        lines += ["", f"Ожидают реакции: {waiting}"]
        if action == "settings":
            quiet = "не заданы" if policy.quiet_hours_start is None else f"{policy.quiet_hours_start:%H:%M}–{policy.quiet_hours_end:%H:%M}"
            lines += [f"Тихие часы: {quiet}", f"Пауза: {policy.cooldown_seconds // 3600} ч", f"Лимит: {policy.daily_message_limit} в день"]
        output_fn("\n".join(lines))
        return

    if action == "pending":
        rows = [row for row in store.list() if row["state"] in {"candidate", "delivered"}]
        if raw:
            output_fn(json.dumps(rows, ensure_ascii=False))
            return
        if not rows:
            output_fn("Инициативных сообщений пока нет.")
            return
        blocks = []
        for index, row in enumerate(rows, 1):
            detail = row.get("message_text") or ("Давно не было сообщений" if row.get("proactive_event_id") else "Напоминание подготовлено")
            blocks.append(f"{index}. {_interaction_kind(row)}\n   {detail}\n   Создано: {_local_time_label(row['created_at'])}\n   Статус: {_interaction_state(row['state'])}")
        output_fn("Ожидают реакции:\n\n" + "\n\n".join(blocks))
        return

    if action == "history":
        traces = [item for item in repository.list_audit_events() if item["action"] == "proactive_decision"]
        if raw:
            output_fn(json.dumps(traces, ensure_ascii=False))
            return
        if not traces:
            output_fn("Истории решений пока нет.")
            return
        interactions = {row["event_id"]: row for row in store.list()}
        blocks = []
        for index, trace in enumerate(reversed(traces), 1):
            payload = trace["payload"]
            decision = "отправить" if payload["decision"] in {"check_in", "remind"} else "не отправлять"
            reason = _PROACTIVE_REASONS.get(payload.get("reason"), payload.get("reason", "детерминированное правило runtime"))
            interaction = interactions.get(trace["entity_id"])
            kind = _interaction_kind(interaction) if interaction else ("Напоминание" if trace["entity_type"] == "temporal_event" else "Check-in")
            blocks.append(f"{index}. Событие: {kind}\n   Решение: {decision}\n   Время: {_local_time_label(trace['occurred_at'])}\n   Причина: {reason}\n   Профиль модели: {payload.get('model_profile', 'не применялся')}")
        output_fn("История решений:\n\n" + "\n\n".join(blocks))
        return

    if action in {"acknowledge", "dismiss"} and len(parts) == 2:
        rows = [row for row in store.list() if row["state"] in {"candidate", "delivered"}]
        try:
            row = rows[int(parts[1]) - 1]
        except (ValueError, IndexError):
            output_fn("Выбери номер сообщения из списка proactive pending.")
            return
        now = service.temporal_engine.clock.now_utc()
        result = store.acknowledge(row["event_id"], now) if action == "acknowledge" else store.dismiss(row["event_id"], now)
        output_fn("Поняла, отметила." if result["state"] == "acknowledged" else "Хорошо, больше не буду повторять это сообщение.")
        return

    if action in {"recover", "run"}:
        if "--remind" in parts:
            policy = policy.model_copy(update={"enabled": True, "proactive_level": max(1, policy.proactive_level), "allow_commitment_reminders": True, "maximum_reminders": max(1, policy.maximum_reminders), "daily_message_limit": max(1, policy.daily_message_limit)})
        receipt = journal.append(DailyRuntime(history=service.history, temporal_engine=service.temporal_engine, repository=repository, identity_kernel=service.identity_kernel, router=service.router, model_profiles=service.model_profiles).run_cycle(policy))
        if raw:
            output_fn(json.dumps(receipt.model_dump(mode="json"), ensure_ascii=False))
            return
        messages = [store.get(item.event_id).get("message_text") for item in receipt.items if item.event_id and item.state == "delivered" and store.get(item.event_id)]
        output_fn("\n".join(message for message in messages if message) if messages else f"Новых сообщений нет. Причина: {_PROACTIVE_REASONS.get(receipt.reason, receipt.reason)}.")
        return

    _run_proactive_command_legacy(command, service=service, output_fn=output_fn)


def _run_commitments_command(command: str, *, service: ConversationService, output_fn: Callable[[str], None]) -> None:
    document = service.memory_retriever.memory_store.read_document()
    commitments = [] if document is None else document.commitments
    engine = service.temporal_engine
    mode = command.split(maxsplit=1)[1] if len(command.split(maxsplit=1)) > 1 else "list"
    rows = [(item, engine.commitment_status(item)) for item in commitments if item.visibility.value == "visible"]
    if mode == "overdue": rows = [row for row in rows if row[1] == "overdue"]
    if mode == "upcoming": rows = [row for row in rows if row[1] == "open" and row[0].due_at is not None]
    if "--raw" in command:
        output_fn(json.dumps([{"id": item.id, "status": status, "due_at": item.due_at.isoformat() if item.due_at else None} for item, status in rows], ensure_ascii=False)); return
    if not rows:
        output_fn("Обязательств не нашла."); return
    output_fn("Обязательства:\n" + "\n".join(f"{index}. {item.text}\n   До: {item.due_at.astimezone(MOSCOW).strftime('%d.%m.%Y, %H:%M') if item.due_at else 'без срока'}\n   Статус: {status}" for index, (item, status) in enumerate(rows, 1)))


def main() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Run the local Masha Home conversation.")
    parser.add_argument("--conversation-id", help="Continue this local conversation id.")
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID)
    arguments = parser.parse_args()
    try:
        service = build_service()
    except IdentityMemoryVersionMismatchError as error:
        print(f"Masha cannot start: {error}.")
        return
    assert service.memory_intent_handler is not None
    run_cli(
        service,
        project_id=arguments.project_id,
        conversation_id=arguments.conversation_id,
        memory_management=MemoryManagementService(service.memory_retriever.memory_store),
        proposal_store=service.memory_intent_handler.proposal_store,
    )


if __name__ == "__main__":
    main()
