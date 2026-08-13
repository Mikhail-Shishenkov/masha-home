from __future__ import annotations

import re

from backend.identity.identity_kernel import IdentityKernel
from backend.llm.model_models import MessageRole, ModelMessage
from backend.memory.text_normalization import meaningful_tokens
from backend.llm.model_provider import ModelProviderUnavailableError, ModelTimeoutError
from backend.llm.model_router import ModelRouter
from backend.llm.model_profiles import ModelProfileStore
from backend.memory.memory_retriever import ContextLens, MemoryRetrievalRequest, MemoryRetriever
from backend.memory.working_memory import WorkingMemory
from backend.temporal.temporal_engine import TemporalEngine
from backend.temporal.temporal_intent import temporal_readout

from .conversation_models import ConversationMessageOrigin, ConversationRole
from .context_compiler import ConversationContextCompiler
from .conversation_store import ConversationStore
from .memory_intent import MemoryIntentHandler
from .reflection_intent import ReflectionIntentHandler
from .response_contract import render_model_response
from .temporal_consistency import enforce_temporal_consistency


class ConversationUnavailableError(RuntimeError):
    """Controlled application error; callers should present it without a traceback."""


_LENS_SPACE = re.compile(r"\s+")
_LENS_PUNCTUATION = re.compile(r"[^\w\s'-]+", re.UNICODE)
_SHARED_CONTINUITY_QUERY = re.compile(
    r"\b(?:между\s+нами|наш(?:а|ей|у)\s+истори(?:я|и|ю)|общ(?:ая|ей|ую)\s+истори(?:я|и|ю)|"
    r"открыт(?:ая|ые|ую)\s+нит(?:ь|и)|что\s+у\s+нас\s+продолжается)\b"
)
_PERSPECTIVE_QUERY = re.compile(
    r"\b(?:"
    r"что\s+ты(?:\s+(?:сама|вообще)){0,2}\s+думаешь|"
    r"ты(?:\s+(?:сама|вообще)){0,2}\s+что\s+думаешь|"
    r"ты(?:\s+сама)?\s+что\s+(?:про\s+(?:это|нее)|об\s+этом)\s+думаешь|"
    r"каково\s+твое\s+мнение|"
    r"как\s+изменилось\s+твое\s+мнение|"
    r"ты\s+все\s+еще\s+так\s+считаешь|"
    r"тво(?:е\s+мнение|и\s+рефлекси\w*)"
    r")\b"
)


def _normalized_lens_query(value: str) -> str:
    text = value.casefold().replace("ё", "е")
    return _LENS_SPACE.sub(" ", _LENS_PUNCTUATION.sub(" ", text)).strip()


def select_context_lens(user_message: str) -> ContextLens:
    """Classify only the three established context lenses, deterministically."""
    query = _normalized_lens_query(user_message)
    if _SHARED_CONTINUITY_QUERY.search(query):
        return ContextLens.SHARED_CONTINUITY
    if _PERSPECTIVE_QUERY.search(query):
        return ContextLens.MASHA_PERSPECTIVE
    return ContextLens.GENERAL


def _retrieval_query(user_message: str, lens: ContextLens) -> str:
    """Remove only lens framing so it cannot masquerade as topical evidence."""
    if lens is not ContextLens.MASHA_PERSPECTIVE:
        return user_message
    normalized = _normalized_lens_query(user_message)
    topic = _LENS_SPACE.sub(" ", _PERSPECTIVE_QUERY.sub(" ", normalized)).strip()
    return topic


_EXPLICIT_BROAD_PERSPECTIVE = re.compile(
    r"\b(?:вообще|в\s+целом)\b.*\b(?:думаешь|мнение|считаешь)\b|"
    r"\b(?:думаешь|мнение|считаешь)\b.*\b(?:вообще|в\s+целом)\b"
)


def contextualized_retrieval_query(
    user_message: str,
    lens: ContextLens,
    recent_user_messages: tuple[str, ...] = (),
) -> str:
    """Resolve a pronoun-only topic from at most two prior user turns."""
    topic = _retrieval_query(user_message, lens)
    if lens is not ContextLens.MASHA_PERSPECTIVE:
        return topic
    normalized = _normalized_lens_query(user_message)
    if _EXPLICIT_BROAD_PERSPECTIVE.search(normalized):
        return ""
    if meaningful_tokens(topic):
        return topic
    for previous in reversed(recent_user_messages[-2:]):
        previous_topic = _retrieval_query(previous, select_context_lens(previous))
        if meaningful_tokens(previous_topic):
            return previous_topic
    return topic


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
        reflection_intent_handler: ReflectionIntentHandler | None = None,
        reflection_service=None,
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
        self.reflection_intent_handler = reflection_intent_handler
        self.reflection_service = reflection_service

    def send(
        self,
        user_message: str,
        *,
        project_id: str,
        conversation_id: str | None = None,
        allow_capability_routing: bool = True,
        active_continuity_thread_id: str | None = None,
    ) -> tuple[str, str]:
        conversation = self.history.create() if conversation_id is None else self.history.get(conversation_id)
        last_interaction_at = self.history.last_interaction_at(conversation.id)
        temporal_context = self.temporal_engine.context(
            last_interaction_at,
            user_message=user_message,
        )
        user_history_message = self.history.append(conversation.id, ConversationRole.USER, user_message)
        if self.proactive_interactions is not None:
            self.proactive_interactions.resolve_check_ins_for_user_message(user_history_message.created_at)

        readout = temporal_readout(user_message, temporal_context)
        if readout is not None:
            self.history.append(
                conversation.id,
                ConversationRole.ASSISTANT,
                readout.response,
                origin=ConversationMessageOrigin.APPLICATION,
            )
            return conversation.id, readout.response

        if self.reflection_intent_handler is not None:
            reflection_intent = self.reflection_intent_handler.handle(
                user_message,
                message_id=user_history_message.id,
                conversation_id=conversation.id,
                project_id=project_id,
                conversation_messages=self.history.messages(
                    conversation.id,
                    limit=self.history_limit,
                ),
            )
            if reflection_intent.handled:
                assert reflection_intent.response is not None
                self.history.append(
                    conversation.id,
                    ConversationRole.ASSISTANT,
                    reflection_intent.response,
                    origin=ConversationMessageOrigin.APPLICATION,
                )
                return conversation.id, reflection_intent.response

        if allow_capability_routing and self.memory_intent_handler is not None:
            intent = self.memory_intent_handler.handle(
                user_message,
                conversation_id=conversation.id,
                project_id=project_id,
                active_continuity_thread_id=active_continuity_thread_id,
                conversation_messages=self.history.messages(
                    conversation.id,
                    limit=self.history_limit,
                ),
            )
            if intent.handled:
                assert intent.response is not None
                self.history.append(
                    conversation.id,
                    ConversationRole.ASSISTANT,
                    intent.response,
                    origin=ConversationMessageOrigin.APPLICATION,
                )
                return conversation.id, intent.response

        context_lens = select_context_lens(user_message)
        recent_user_messages = tuple(
            message.content
            for message in self.history.messages(conversation.id, limit=self.history_limit)
            if message.role is ConversationRole.USER and message.id != user_history_message.id
        )
        memories = self.memory_retriever.retrieve(
            MemoryRetrievalRequest(
                query=contextualized_retrieval_query(
                    user_message,
                    context_lens,
                    recent_user_messages,
                ),
                project_id=project_id,
                limit=self.memory_limit,
                lens=context_lens,
            )
        )
        self.working_memory.load(memories)
        active_profile = None if self.model_profiles is None else self.model_profiles.get_active_profile()
        request = self.context_compiler.compile(
            messages=tuple(
                self._model_history_message(message)
                for message in self.history.messages(conversation.id, limit=self.history_limit)
            ),
            identity_context=self.identity_kernel.build_context(),
            working_memory=self.working_memory.get_all(),
            temporal_context=temporal_context,
            execution_model_id=None if active_profile is None else active_profile.model_id,
            execution_think=False if active_profile is None else active_profile.think,
            execution_timeout_seconds=30.0 if active_profile is None else active_profile.timeout_seconds,
            context_lens=context_lens.value,
        )
        try:
            response = self.router.generate(request)
        except (ModelProviderUnavailableError, ModelTimeoutError) as error:
            raise ConversationUnavailableError("Локальная модель сейчас недоступна.") from error
        # This branch is an ordinary model turn: no application/domain
        # mutation receipt can exist here. Enforce that contract before the
        # text enters history or crosses the desktop boundary.
        grounded_response = enforce_temporal_consistency(
            response.text,
            user_message=user_message,
            context=temporal_context,
        )
        rendered = render_model_response(grounded_response, application_receipts=())
        self.history.append(conversation.id, ConversationRole.ASSISTANT, rendered)
        return conversation.id, rendered

    def resolve_memory_proposal(
        self,
        *,
        conversation_id: str,
        proposal_id: str,
        confirm: bool,
        project_id: str,
    ) -> tuple[str, str]:
        """Resolve one explicit proposal without exposing its ID in human history."""
        if self.memory_intent_handler is None:
            raise RuntimeError("memory intent handler is unavailable")
        self.history.get(conversation_id)
        user_text = "Подтверждаю." if confirm else "Не сейчас."
        command = f"{'да' if confirm else 'нет'} {proposal_id}"
        self.history.append(conversation_id, ConversationRole.USER, user_text)
        result = self.memory_intent_handler.handle(
            command,
            conversation_id=conversation_id,
            project_id=project_id,
        )
        if not result.handled or result.response is None:
            raise RuntimeError("proposal resolution was not handled")
        assistant = self.history.append(
            conversation_id,
            ConversationRole.ASSISTANT,
            result.response,
            origin=ConversationMessageOrigin.APPLICATION,
        )
        proposal = self.memory_intent_handler.proposal_store.get(proposal_id)
        status = "missing" if proposal is None else proposal.status.value
        return assistant.content, status

    def propose_commitment_completion(
        self,
        *,
        commitment_id: str,
        conversation_id: str | None,
        project_id: str,
    ):
        if self.memory_intent_handler is None:
            raise RuntimeError("memory intent handler is unavailable")
        conversation = self.history.create() if conversation_id is None else self.history.get(conversation_id)
        pending = tuple(
            item
            for item in self.memory_intent_handler.proposal_store.pending_for_conversation(conversation.id)
            if item.record_type == "commitment"
        )
        if pending:
            raise ValueError("a commitment confirmation is already pending")
        view = self.memory_intent_handler.memory_management.get(commitment_id)
        if view is None or view.record_type != "commitment":
            raise KeyError("commitment not found")
        if view.payload.get("status") != "open":
            raise ValueError("commitment is not open")
        user = self.history.append(
            conversation.id,
            ConversationRole.USER,
            f"Маша, отметь «{view.payload['text']}» выполненным.",
        )
        result = self.memory_intent_handler.propose_completion_by_id(
            commitment_id,
            conversation.id,
        )
        if not result.handled or result.response is None:
            raise RuntimeError("completion proposal was not created")
        assistant = self.history.append(
            conversation.id,
            ConversationRole.ASSISTANT,
            result.response,
            origin=ConversationMessageOrigin.APPLICATION,
        )
        return conversation.id, user, assistant

    @staticmethod
    def _model_history_message(message) -> ModelMessage:
        if message.origin is ConversationMessageOrigin.APPLICATION:
            return ModelMessage(
                role=MessageRole.SYSTEM,
                content=(
                    "Результат приложения из предыдущего хода; это факт интерфейса, "
                    "а не образец стиля ответа:\n" + message.content
                ),
            )
        return ModelMessage(role=message.role.value, content=message.content)
