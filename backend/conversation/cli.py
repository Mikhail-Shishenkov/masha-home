"""Small offline terminal entry point for the existing conversation vertical slice."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

from backend.identity.identity_kernel import (
    IdentityKernel,
    IdentityMemoryVersionMismatchError,
)
from backend.identity.identity_store import IdentityStore
from backend.llm.model_router import ModelRouter
from backend.llm.ollama_provider import OllamaProvider
from backend.memory.memory_retriever import MemoryRetriever
from backend.memory.sqlite_repository import MemorySqliteRepository
from backend.memory.working_memory import WorkingMemory
from backend.memory.confirmed_memory_service import ConfirmedMemoryService
from backend.memory.memory_management import MemoryManagementService, MemoryMutationOperation
from backend.memory.memory_presentation import detail, history, list_views, preview, summary
from backend.temporal.temporal_engine import MOSCOW, TemporalEngine

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
        ),
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
        if user_message.startswith("time"):
            _run_time_command(user_message, service=service, conversation_id=active_id, output_fn=output_fn)
            continue
        if user_message.startswith("commitments"):
            _run_commitments_command(user_message, service=service, output_fn=output_fn)
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
