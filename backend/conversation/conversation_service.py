from __future__ import annotations

import re

from backend.identity.identity_kernel import IdentityKernel
from backend.llm.model_models import ModelMessage
from backend.llm.model_provider import ModelProviderUnavailableError, ModelTimeoutError
from backend.llm.model_router import ModelRouter
from backend.llm.model_profiles import ModelProfileStore
from backend.memory.memory_retriever import MemoryRetriever
from backend.memory.working_memory import WorkingMemory
from backend.temporal.temporal_engine import TemporalEngine

from .conversation_models import ConversationRole
from .context_compiler import ConversationContextCompiler
from .conversation_store import ConversationStore
from .memory_intent import MemoryIntentHandler


class ConversationUnavailableError(RuntimeError):
    """Controlled application error; callers should present it without a traceback."""


_SHARED_CONTINUITY_QUERY = re.compile(
    r"\b(?:между\s+нами|наш(?:а|ей|у)\s+истори(?:я|и|ю)|общ(?:ая|ей|ую)\s+истори(?:я|и|ю)|"
    r"открыт(?:ая|ые|ую)\s+нит(?:ь|и)|что\s+у\s+нас\s+продолжается)\b",
    re.IGNORECASE,
)


class ConversationService:
    def __init__(
        self,
        *,
        identity_kernel: IdentityKernel,
        memory_retriever: MemoryRetriever,
        working_memory: WorkingMemory,
        router: ModelRouter,
        history: ConversationStore,
        context_compiler: ConversationContextCompiler | None = None,
        memory_intent_handler: MemoryIntentHandler | None = None,
        memory_limit: int = 6,
        history_limit: int = 16,
        temporal_engine: TemporalEngine | None = None,
        model_profiles: ModelProfileStore | None = None,
        proactive_interactions=None,
        shared_continuity=None,
    ):
        self.identity_kernel = identity_kernel
        self.memory_retriever = memory_retriever
        self.working_memory = working_memory
        self.router = router
        self.history = history
        self.context_compiler = context_compiler or ConversationContextCompiler()
        self.memory_intent_handler = memory_intent_handler
        self.memory_limit = memory_limit
        self.history_limit = history_limit
        self.temporal_engine = temporal_engine or TemporalEngine()
        self.model_profiles = model_profiles
        self.proactive_interactions = proactive_interactions
        self.shared_continuity = shared_continuity

    def send(
        self,
        user_message: str,
        *,
        project_id: str,
        conversation_id: str | None = None,
    ) -> tuple[str, str]:
        conversation = self.history.create() if conversation_id is None else self.history.get(conversation_id)
        last_interaction_at = self.history.last_interaction_at(conversation.id)
        temporal_context = self.temporal_engine.context(last_interaction_at)
        user_history_message = self.history.append(conversation.id, ConversationRole.USER, user_message)
        if self.proactive_interactions is not None:
            self.proactive_interactions.resolve_check_ins_for_user_message(user_history_message.created_at)

        if self.memory_intent_handler is not None:
            intent = self.memory_intent_handler.handle(
                user_message,
                conversation_id=conversation.id,
                project_id=project_id,
            )
            if intent.handled:
                assert intent.response is not None
                self.history.append(conversation.id, ConversationRole.ASSISTANT, intent.response)
                return conversation.id, intent.response

        memories = self.memory_retriever.retrieve(project_id=project_id, limit=self.memory_limit)
        context_lens = "general"
        if _SHARED_CONTINUITY_QUERY.search(user_message):
            context_lens = "shared_continuity"
            memories = [
                item
                for item in memories
                if item["type"] in {"relationship_memory", "continuity_state"}
            ]
        self.working_memory.load(memories)
        active_profile = None if self.model_profiles is None else self.model_profiles.get_active_profile()
        request = self.context_compiler.compile(
            messages=tuple(
                ModelMessage(role=message.role.value, content=message.content)
                for message in self.history.messages(conversation.id, limit=self.history_limit)
            ),
            identity_context=self.identity_kernel.build_context(),
            working_memory=self.working_memory.get_all(),
            temporal_context=temporal_context,
            execution_model_id=None if active_profile is None else active_profile.model_id,
            execution_think=False if active_profile is None else active_profile.think,
            execution_timeout_seconds=30.0 if active_profile is None else active_profile.timeout_seconds,
            context_lens=context_lens,
        )
        try:
            response = self.router.generate(request)
        except (ModelProviderUnavailableError, ModelTimeoutError) as error:
            raise ConversationUnavailableError("Локальная модель сейчас недоступна.") from error
        self.history.append(conversation.id, ConversationRole.ASSISTANT, response.text)
        return conversation.id, response.text
