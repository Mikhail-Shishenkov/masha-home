"""UI-safe projections and explicit actions for reflections and Honest Help."""

from __future__ import annotations

from backend.conversation.conversation_models import ConversationRole
from backend.memory.reflection import ReflectionUnavailableError

from .contracts import (
    AdoptedReflectionView,
    HonestHelpOfferView,
    HonestHelpResolutionView,
    PendingReflectionView,
    ReflectionResolutionView,
    ReflectionWorkspaceView,
)


class ReflectionApplicationService:
    """Keep reflection decisions explicit while reusing the Stage 15 service."""

    def __init__(self, *, reflections, history):
        self._reflections = reflections
        self._history = history

    def workspace(self, *, limit: int = 8) -> ReflectionWorkspaceView:
        adopted = tuple(
            AdoptedReflectionView(
                reflection_id=view.reflection.id,
                text=view.reflection.text,
                meaning=view.reflection.meaning,
                confidence=view.reflection.confidence,
                scope=view.scope.value,
                created_at=view.reflection.created_at,
                reconsiders_previous=view.reflection.reconsiders_reflection_id is not None,
            )
            for view in self._reflections.reflections()[:limit]
        )
        pending = tuple(
            PendingReflectionView(
                candidate_id=candidate.id,
                text=str(candidate.proposed_payload["reflection"]["text"]),
                meaning=str(candidate.proposed_payload["reflection"]["meaning"]),
                confidence=candidate.confidence,
                scope=str(candidate.proposed_payload["scope"]),
                created_at=candidate.created_at,
            )
            for candidate in self._reflections.pending()[:limit]
        )
        help_offers = []
        for candidate in self._reflections.pending_help()[:limit]:
            raw = candidate.proposed_payload.get("help_offer")
            if not isinstance(raw, dict):
                continue
            help_offers.append(
                HonestHelpOfferView(
                    candidate_id=candidate.id,
                    observation=str(raw["observation"]),
                    offer=str(raw["offer"]),
                    expected_benefit=str(raw["expected_benefit"]),
                    why_now=str(raw["why_now"]),
                )
            )
        return ReflectionWorkspaceView(
            adopted=adopted,
            pending=pending,
            help_offers=tuple(help_offers),
        )

    def resolve_reflection(self, candidate_id: str, decision: str) -> ReflectionResolutionView:
        visible = {item.candidate_id: item for item in self.workspace().pending}
        selected = visible.get(candidate_id)
        if selected is None or decision not in selected.allowed_actions:
            raise ValueError("reflection decision is stale or invalid")
        if decision == "adopt":
            reflection = self._reflections.adopt(candidate_id)
            return ReflectionResolutionView(
                candidate_id=candidate_id,
                status="adopted",
                message=f"Сохранила как свою рефлексию: «{reflection.text}»",
            )
        self._reflections.reject(candidate_id)
        return ReflectionResolutionView(
            candidate_id=candidate_id,
            status="rejected",
            message="Эта интерпретация не закреплена.",
        )

    def resolve_help(self, candidate_id: str, decision: str) -> HonestHelpResolutionView:
        visible = {item.candidate_id: item for item in self.workspace().help_offers}
        selected = visible.get(candidate_id)
        if selected is None or decision not in selected.allowed_actions:
            raise ValueError("help decision is stale or invalid")
        if decision == "dismiss":
            self._reflections.reject_help(candidate_id)
            return HonestHelpResolutionView(
                candidate_id=candidate_id,
                status="dismissed",
                conversation_id=None,
                message="Хорошо, не навязываюсь.",
            )

        candidate = next(
            item
            for item in self._reflections.pending_help()
            if item.id == candidate_id
        )
        conversation_id = str(candidate.proposed_payload["conversation_id"])
        self._history.get(conversation_id)
        user_message = self._history.append(
            conversation_id,
            ConversationRole.USER,
            "Давай, помоги.",
        )
        messages = self._history.messages(conversation_id, limit=8)
        try:
            response = self._reflections.accept_help(
                candidate_id,
                conversation_messages=messages,
            )
        except ReflectionUnavailableError:
            response = (
                "Локальная модель сейчас недоступна. Предложение осталось принятым — "
                "сможем продолжить позже."
            )
            status = "model_unavailable"
        else:
            status = "delivered"
        self._history.append(conversation_id, ConversationRole.ASSISTANT, response)
        return HonestHelpResolutionView(
            candidate_id=candidate_id,
            status=status,
            conversation_id=conversation_id,
            message=response,
            user_message_id=user_message.id,
        )
