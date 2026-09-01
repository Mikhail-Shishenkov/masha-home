"""Application-owned context for the most recently presented real entities."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Callable

from backend.conversation.capability_router import normalize_utterance
from backend.conversation.human_reference import (
    HumanEntityKind,
    PresentedEntityRef,
    PresentedEntitySet,
)


class PresentedEntityReferenceKind(str, Enum):
    ORDINAL = "ordinal"
    EXACT_LABEL = "exact_label"
    DEMONSTRATIVE = "demonstrative"
    CONTEXTUAL_CLASS = "contextual_class"


@dataclass(frozen=True)
class PresentedEntityContext:
    """One bounded, conversation-scoped application projection."""

    conversation_id: str
    owner: str
    entity_kind: str
    items: tuple[object, ...]
    presentation_kind: str | None = None


@dataclass(frozen=True)
class PresentedEntityReference:
    kind: PresentedEntityReferenceKind
    ordinal: int | None = None
    label: str | None = None


@dataclass(frozen=True)
class PresentedEntityResolution:
    context: PresentedEntityContext | None
    item: object | None
    status: str


_ORDINALS = {
    "первое": 1, "первый": 1,
    "второе": 2, "второй": 2,
    "третье": 3, "третий": 3,
}


class PresentedReadSetRegistry:
    """The newest real connector presentation owns contextual references."""

    def __init__(self):
        self._rows: dict[str, PresentedEntityContext] = {}

    def present(
        self,
        conversation_id: str,
        owner: str,
        items: tuple[object, ...],
        *,
        entity_kind: str = "item",
        presentation_kind: str | None = None,
    ) -> None:
        self._rows[conversation_id] = PresentedEntityContext(
            conversation_id=conversation_id,
            owner=owner,
            entity_kind=entity_kind,
            items=items,
            presentation_kind=presentation_kind,
        )

    def present_home_entities(self, presented: PresentedEntitySet) -> None:
        """Make a Home-owned list the newest cross-capability reference set."""

        self._rows[presented.conversation_id] = PresentedEntityContext(
            conversation_id=presented.conversation_id,
            owner="home_information",
            entity_kind="mixed",
            items=presented.items,
            presentation_kind=presented.source_kind,
        )

    def discard(self, conversation_id: str, *, owner: str | None = None) -> None:
        current = self._rows.get(conversation_id)
        if current is not None and (owner is None or current.owner == owner):
            self._rows.pop(conversation_id, None)

    def current_context(self, conversation_id: str) -> PresentedEntityContext | None:
        return self._rows.get(conversation_id)

    def items_for(self, conversation_id: str, owner: str) -> tuple[object, ...] | None:
        row = self.current_context(conversation_id)
        return None if row is None or row.owner != owner else row.items

    def model_safe_hints(self, conversation_id: str) -> tuple[dict[str, object], ...]:
        """Project the latest visible set without provider/storage identity."""

        context = self.current_context(conversation_id)
        if context is None:
            return ()
        context_operation_id = {
            "google_drive": "google_drive.read",
            "yandex_disk": "yandex_disk.read",
            "yandex_mail": "yandex_mail.read",
        }.get(context.owner)
        if context_operation_id is None and context.owner != "home_information":
            return ()
        rows = []
        for position, item in enumerate(context.items[:10], start=1):
            if isinstance(item, PresentedEntityRef):
                operation_id = {
                    HumanEntityKind.MEMORY: "home.memory.inspect",
                    HumanEntityKind.HISTORY: "home.continuity.read",
                    HumanEntityKind.TASK: "home.commitments",
                    HumanEntityKind.THREAD: "home.continuity.read",
                }[item.entity_kind]
                label = item.human_label.strip()
                kind = item.entity_kind.value
                time_value = None
            else:
                operation_id = context_operation_id
                label = next((
                    str(value).strip()
                    for name in ("subject", "name", "title")
                    if (value := getattr(item, name, None)) is not None
                    and str(value).strip()
                ), "")
                kind = context.entity_kind
                time_value = next((
                    value
                    for name in (
                        "received_at", "modified_time", "modified_at",
                        "created_at", "start",
                    )
                    if (value := getattr(item, name, None)) is not None
                ), None)
            if not label:
                continue
            assert operation_id is not None
            rows.append({
                "position": position,
                "owner_operation_id": operation_id,
                "kind": kind,
                "human_label": label[:500],
                "time_text": None if time_value is None else str(time_value)[:120],
            })
        return tuple(rows)

    def resolve(
        self,
        conversation_id: str,
        *,
        owner: str,
        entity_kind: str,
        reference: PresentedEntityReference,
        label_of: Callable[[object], str],
        required_presentation_kind: str | None = None,
    ) -> PresentedEntityResolution:
        context = self.current_context(conversation_id)
        if (
            context is None
            or context.owner != owner
            or context.entity_kind != entity_kind
            or (
                required_presentation_kind is not None
                and context.presentation_kind != required_presentation_kind
            )
        ):
            return PresentedEntityResolution(context=context, item=None, status="no_context")
        if reference.kind is PresentedEntityReferenceKind.ORDINAL:
            index = (reference.ordinal or 0) - 1
            if 0 <= index < len(context.items):
                return PresentedEntityResolution(context, context.items[index], "resolved")
            return PresentedEntityResolution(context, None, "clarification_required")
        if reference.kind is PresentedEntityReferenceKind.EXACT_LABEL:
            label = normalize_utterance(reference.label or "")
            matches = tuple(
                item for item in context.items
                if normalize_utterance(label_of(item)) == label
            )
            return PresentedEntityResolution(
                context,
                matches[0] if len(matches) == 1 else None,
                "resolved" if len(matches) == 1 else "clarification_required",
            )
        # Demonstratives and bounded classes only have safe meaning when one
        # current, real item was presented by this owner.
        if len(context.items) == 1:
            return PresentedEntityResolution(context, context.items[0], "resolved")
        return PresentedEntityResolution(context, None, "clarification_required")


def parse_presented_entity_reference(
    message: str,
    *,
    entity_kind: str,
    visible_labels: tuple[str, ...] = (),
    require_read_action: bool = True,
) -> PresentedEntityReference | None:
    """Parse a shared reference vocabulary after an explicit read verb.

    It never routes a provider: it only maps a user reference onto a bounded
    entity set already presented by an application owner.
    """

    text = normalize_utterance(message)
    if (
        require_read_action
        and re.search(r"\bпрочита(?:й|ть|ешь)\b", text) is None
    ):
        return None
    for label in visible_labels:
        if label and normalize_utterance(label) in text:
            return PresentedEntityReference(
                PresentedEntityReferenceKind.EXACT_LABEL,
                label=label,
            )
    for word, ordinal in _ORDINALS.items():
        if re.search(rf"\b{re.escape(word)}\b", text):
            return PresentedEntityReference(PresentedEntityReferenceKind.ORDINAL, ordinal=ordinal)
    if re.search(rf"\b(?:нов(?:ое|ый|ую)|свеже(?:е|е?е))\s+{re.escape(entity_kind)}\b", text):
        return PresentedEntityReference(PresentedEntityReferenceKind.CONTEXTUAL_CLASS)
    if re.search(rf"\b(?:это|его|ее|её)\b(?:\s+{re.escape(entity_kind)})?", text):
        return PresentedEntityReference(PresentedEntityReferenceKind.DEMONSTRATIVE)
    return None

