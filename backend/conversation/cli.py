"""Small offline terminal entry point for the existing conversation vertical slice."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path

from backend.identity.identity_kernel import IdentityKernel
from backend.identity.identity_store import IdentityStore
from backend.llm.model_router import ModelRouter
from backend.llm.ollama_provider import OllamaProvider
from backend.memory.memory_retriever import MemoryRetriever
from backend.memory.sqlite_repository import MemorySqliteRepository
from backend.memory.working_memory import WorkingMemory
from backend.memory.confirmed_memory_service import ConfirmedMemoryService

from .conversation_service import ConversationService, ConversationUnavailableError
from .conversation_store import ConversationStore
from .memory_intent import MemoryIntentHandler, MemoryProposalStore


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROJECT_ID = "project_masha_home"
EXIT_COMMANDS = {":exit", ":quit"}


def build_service(*, project_root: Path = PROJECT_ROOT) -> ConversationService:
    """Assemble only the local JSON memory, identity, router, and Ollama provider."""
    memory_store = MemorySqliteRepository(project_root / "local-data" / "memory" / "masha.sqlite3")
    return ConversationService(
        identity_kernel=IdentityKernel(
            IdentityStore(project_root / "identity" / "masha.identity.json")
        ),
        memory_retriever=MemoryRetriever(memory_store),
        working_memory=WorkingMemory(max_items=6),
        router=ModelRouter([OllamaProvider()]),
        history=ConversationStore(project_root / "local-data" / "conversations" / "history.json"),
        memory_intent_handler=MemoryIntentHandler(
            proposal_store=MemoryProposalStore(project_root / "local-data" / "memory-proposals.json"),
            confirmed_memory=ConfirmedMemoryService(memory_store),
        ),
    )


def run_cli(
    service: ConversationService,
    *,
    project_id: str = DEFAULT_PROJECT_ID,
    conversation_id: str | None = None,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local Masha Home conversation.")
    parser.add_argument("--conversation-id", help="Continue this local conversation id.")
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID)
    arguments = parser.parse_args()
    run_cli(
        build_service(),
        project_id=arguments.project_id,
        conversation_id=arguments.conversation_id,
    )


if __name__ == "__main__":
    main()
