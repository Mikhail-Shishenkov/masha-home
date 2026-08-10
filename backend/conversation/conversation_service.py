from __future__ import annotations

from backend.identity.identity_kernel import IdentityKernel
from backend.llm.model_models import ModelMessage
from backend.llm.model_provider import ModelProviderUnavailableError, ModelTimeoutError
from backend.llm.model_router import ModelRouter
from backend.memory.memory_retriever import MemoryRetriever
from backend.memory.working_memory import WorkingMemory

from .conversation_models import ConversationRole
from .context_compiler import ConversationContextCompiler
from .conversation_store import ConversationStore
from .memory_intent import MemoryIntentHandler


class ConversationUnavailableError(RuntimeError):
    """Controlled application error; callers should present it without a traceback."""


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

    def send(
        self,
        user_message: str,
        *,
        project_id: str,
        conversation_id: str | None = None,
    ) -> tuple[str, str]:
        conversation = self.history.create() if conversation_id is None else self.history.get(conversation_id)
        self.history.append(conversation.id, ConversationRole.USER, user_message)

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
        self.working_memory.load(memories)
        request = self.context_compiler.compile(
            messages=tuple(
                ModelMessage(role=message.role.value, content=message.content)
                for message in self.history.messages(conversation.id, limit=self.history_limit)
            ),
            identity_context=self.identity_kernel.build_context(),
            working_memory=self.working_memory.get_all(),
        )
        try:
            response = self.router.generate(request)
        except (ModelProviderUnavailableError, ModelTimeoutError) as error:
            raise ConversationUnavailableError("Локальная модель сейчас недоступна.") from error
        self.history.append(conversation.id, ConversationRole.ASSISTANT, response.text)
        return conversation.id, response.text
