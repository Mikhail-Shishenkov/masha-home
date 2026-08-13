"""Deterministic query-aware selection of bounded local memory context."""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from .shared_continuity import is_readable_continuity_text
from .text_normalization import meaningful_tokens


class ContextLens(str, Enum):
    GENERAL = "general"
    SHARED_CONTINUITY = "shared_continuity"
    MASHA_PERSPECTIVE = "masha_perspective"


class SemanticRelevanceScorer(Protocol):
    """Optional local-only batch hook; no implementation ships in v0.2."""

    def score_many(
        self,
        query: str,
        candidate_texts: tuple[str, ...],
    ) -> tuple[float, ...]: ...


class MemoryRetrievalRequest(BaseModel):
    """One explicit conversational retrieval boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str
    project_id: str | None = None
    limit: int = Field(default=6, ge=0, le=50)
    lens: ContextLens = ContextLens.GENERAL
    # Conservative payload estimate; no tokenizer dependency is required.
    memory_budget_chars: int = Field(default=3_600, ge=256, le=50_000)
    max_record_chars: int = Field(default=2_000, ge=128, le=20_000)


class RetrievalScoreComponents(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    lexical: float
    semantic: float
    importance: float
    recency: float
    lens: float
    type: float


class RetrievalTraceItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: str
    record_type: str
    total_score: float
    components: RetrievalScoreComponents
    lexical_threshold: float
    passed_threshold: bool
    selected: bool
    estimated_chars: int
    reasons: tuple[str, ...]


class MemoryRetrievalResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    records: tuple[dict[str, Any], ...]
    trace: tuple[RetrievalTraceItem, ...]
    estimated_chars: int = Field(ge=0)


_COLLECTIONS = (
    ("fact", "facts"),
    ("decision", "decisions"),
    ("commitment", "commitments"),
    ("episode", "episodes"),
    ("reflection", "reflections"),
    ("relationship_memory", "relationship_memories"),
    ("continuity_state", "continuity_states"),
)
_LENS_TYPES = {
    ContextLens.GENERAL: {
        "fact", "decision", "commitment", "episode",
        "relationship_memory", "continuity_state",
    },
    ContextLens.SHARED_CONTINUITY: {"relationship_memory", "continuity_state"},
    ContextLens.MASHA_PERSPECTIVE: {"reflection"},
}
_BROAD_LENS_TOKENS = {
    ContextLens.SHARED_CONTINUITY: {
        "истор", "наш", "общ", "отношен", "межд", "продолжа", "открыт", "вернут",
    },
    ContextLens.MASHA_PERSPECTIVE: {
        "дум", "дума", "мнени", "рефлекси", "счита", "взгляд", "перспектив",
    },
}
_BASE_TYPE_SIGNAL = {
    "decision": 0.15,
    "episode": 0.10,
    "fact": 0.06,
    "reflection": 0.06,
    "relationship_memory": 0.05,
    "continuity_state": 0.05,
    "commitment": 0.03,
}
_QUERY_TYPE_TOKENS = {
    "decision": {"реш", "решен", "выбр", "выбран"},
    "episode": {"обсужд", "произош", "случ", "разговарив"},
}


class MemoryRetriever:
    """Ranks local candidates; it never invokes a model or exposes storage."""

    LEXICAL_WEIGHT = 10.0
    SPECIFIC_THRESHOLDS = {
        ContextLens.GENERAL: 0.30,
        ContextLens.SHARED_CONTINUITY: 0.26,
        ContextLens.MASHA_PERSPECTIVE: 0.26,
    }

    def __init__(
        self,
        memory_store,
        *,
        clock: Callable[[], datetime] | None = None,
        semantic_scorer: SemanticRelevanceScorer | None = None,
    ):
        self.memory_store = memory_store
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._semantic_scorer = semantic_scorer

    def retrieve(self, request: MemoryRetrievalRequest) -> list[dict[str, Any]]:
        return list(self.retrieve_with_trace(request).records)

    def retrieve_with_trace(self, request: MemoryRetrievalRequest) -> MemoryRetrievalResult:
        if request.limit == 0:
            return MemoryRetrievalResult(records=(), trace=(), estimated_chars=0)
        candidates = self._candidates(request)
        query_tokens = meaningful_tokens(request.query)
        broad_lens = self._is_broad_lens_query(request.lens, query_tokens)
        semantic_scores, semantic_failed = self._semantic_scores(
            request.query,
            candidates,
        )
        frequencies = Counter(
            token
            for candidate in candidates
            for token in set(candidate["tokens"])
        )
        corpus_size = max(1, len(candidates))
        threshold = 0.0 if broad_lens else self.SPECIFIC_THRESHOLDS[request.lens]
        ranked: list[dict[str, Any]] = []

        for candidate, semantic in zip(candidates, semantic_scores):
            lexical = self._lexical_relevance(
                query_tokens,
                candidate["tokens"],
                frequencies,
                corpus_size,
            )
            importance = self._importance(candidate["data"], candidate["type"]) * 0.55
            recency = self._recency(candidate["data"]) * 0.30
            lens = 0.25 if candidate["type"] in _LENS_TYPES[request.lens] else 0.0
            type_signal, type_reason = self._type_signal(
                candidate["type"],
                query_tokens,
            )
            passed = broad_lens or lexical >= threshold or semantic >= 0.72
            components = RetrievalScoreComponents(
                lexical=round(lexical, 6),
                semantic=round(semantic, 6),
                importance=round(importance, 6),
                recency=round(recency, 6),
                lens=round(lens, 6),
                type=round(type_signal, 6),
            )
            total = (
                lexical * self.LEXICAL_WEIGHT
                + semantic * 3.0
                + importance
                + recency
                + lens
                + type_signal
            )
            reasons = list(candidate["reasons"])
            reasons.append(f"lens:{request.lens.value}")
            if semantic_failed:
                reasons.append("semantic_fallback_to_lexical")
            if type_reason is not None:
                reasons.append(type_reason)
            reasons.append(
                "broad_lens_selection"
                if broad_lens
                else (
                    "lexical_threshold_passed"
                    if lexical >= threshold
                    else (
                        "semantic_threshold_passed"
                        if semantic >= 0.72
                        else "below_relevance_threshold"
                    )
                )
            )
            ranked.append(
                {
                    **candidate,
                    "lexical": lexical,
                    "components": components,
                    "score": total,
                    "passed": passed,
                    "threshold": threshold,
                    "reasons": reasons,
                    "estimated_chars": self._estimated_chars(candidate),
                }
            )

        ranked.sort(
            key=lambda item: (
                -item["score"],
                -self._timestamp(item["data"]).timestamp(),
                item["type"],
                item["data"]["id"],
            )
        )
        selected: list[dict[str, Any]] = []
        selected_ids: set[str] = set()
        used_chars = 0
        for item in ranked:
            if not item["passed"]:
                continue
            if len(selected) >= request.limit:
                break
            if item["estimated_chars"] > request.max_record_chars:
                item["reasons"].append("record_budget_exceeded")
                continue
            if used_chars + item["estimated_chars"] > request.memory_budget_chars:
                item["reasons"].append("memory_budget_exceeded")
                continue
            item["reasons"].extend(("selected_by_score", "within_memory_budget"))
            selected_ids.add(item["data"]["id"])
            used_chars += item["estimated_chars"]
            selected.append(
                {
                    "type": item["type"],
                    "data": item["data"],
                    "score": round(item["score"], 6),
                    "components": item["components"].model_dump(),
                    "reasons": item["reasons"],
                }
            )

        trace = tuple(
            RetrievalTraceItem(
                record_id=item["data"]["id"],
                record_type=item["type"],
                total_score=round(item["score"], 6),
                components=item["components"],
                lexical_threshold=item["threshold"],
                passed_threshold=item["passed"],
                selected=item["data"]["id"] in selected_ids,
                estimated_chars=item["estimated_chars"],
                reasons=tuple(item["reasons"]),
            )
            for item in ranked
        )
        return MemoryRetrievalResult(
            records=tuple(selected),
            trace=trace,
            estimated_chars=used_chars,
        )

    def _candidates(self, request: MemoryRetrievalRequest) -> list[dict[str, Any]]:
        allowed = _LENS_TYPES[request.lens]
        candidates: list[dict[str, Any]] = []
        data = self.memory_store.data
        for item_type, collection in _COLLECTIONS:
            if item_type not in allowed:
                continue
            for item in data.get(collection, []):
                if item_type == "continuity_state" and not self._usable_continuity(item):
                    continue
                if not self._matches_project(item, request.project_id):
                    continue
                if not self._matches_status(item):
                    continue
                text = self.searchable_text(item_type, item)
                tokens = meaningful_tokens(text)
                reasons = ["visible"]
                if item.get("status") is not None:
                    reasons.append("active_status")
                if item_type == "continuity_state":
                    reasons.append("relationship_scope")
                if request.project_id is not None:
                    reasons.append(f"project:{request.project_id}")
                candidates.append(
                    {
                        "type": item_type,
                        "data": item,
                        "text": text,
                        "tokens": tokens,
                        "reasons": reasons,
                    }
                )
        return candidates

    @staticmethod
    def searchable_text(item_type: str, item: dict[str, Any]) -> str:
        """Render only user-meaningful fields; IDs and audit metadata are excluded."""
        if item_type == "fact":
            fields = (item.get("subject"), item.get("key"), item.get("value"))
        elif item_type == "decision":
            fields = (item.get("title"), item.get("decision"))
        elif item_type == "commitment":
            fields = (item.get("text"),)
        elif item_type == "episode":
            fields = (item.get("title"), item.get("summary"))
        elif item_type == "relationship_memory":
            fields = (item.get("title"), MemoryRetriever._content_text(item.get("content")))
        elif item_type == "continuity_state":
            fields = (
                *(
                    value
                    for value in item.get("current_focus", [])
                    if is_readable_continuity_text(value)
                ),
                *(
                    " ".join(
                        str(value)
                        for value in (
                            follow_up.get("topic"),
                            follow_up.get("summary"),
                            follow_up.get("reason_to_return"),
                        )
                        if value
                    )
                    for follow_up in item.get("intended_follow_ups", [])
                    if follow_up.get("status") == "open"
                    and is_readable_continuity_text(follow_up.get("summary", ""))
                    and is_readable_continuity_text(
                        follow_up.get("reason_to_return", "")
                    )
                ),
            )
        elif item_type == "reflection":
            fields = (item.get("text"), item.get("meaning"))
        else:
            fields = ()
        return " ".join(str(value) for value in fields if value is not None).strip()

    @staticmethod
    def _content_text(value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            return " ".join(MemoryRetriever._content_text(item) for item in value.values())
        if isinstance(value, list):
            return " ".join(MemoryRetriever._content_text(item) for item in value)
        return "" if value is None else str(value)

    @staticmethod
    def _lexical_relevance(
        query_tokens: tuple[str, ...],
        candidate_tokens: tuple[str, ...],
        frequencies: Counter[str],
        corpus_size: int,
    ) -> float:
        if not query_tokens or not candidate_tokens:
            return 0.0
        query_unique = tuple(dict.fromkeys(query_tokens))
        candidate_set = set(candidate_tokens)
        matched = [token for token in query_unique if token in candidate_set]
        if not matched:
            return 0.0

        def weight(token: str) -> float:
            return 1.0 + math.log((corpus_size + 1) / (frequencies[token] + 1))

        query_coverage = sum(weight(token) for token in matched) / sum(
            weight(token) for token in query_unique
        )
        record_coverage = len(set(matched)) / max(1, min(len(set(candidate_tokens)), 8))
        longest = MemoryRetriever._longest_ordered_phrase(query_tokens, candidate_tokens)
        phrase = longest / len(query_tokens) if longest >= 2 else 0.0
        distinctiveness = max(weight(token) for token in matched) / max(
            weight(token) for token in query_unique
        )
        relevance = (
            query_coverage * 0.68
            + min(1.0, record_coverage) * 0.12
            + phrase * 0.15
            + distinctiveness * 0.05
        )
        return min(1.0, relevance)

    def _semantic_scores(
        self,
        query: str,
        candidates: list[dict[str, Any]],
    ) -> tuple[tuple[float, ...], bool]:
        """Run at most one optional local batch and fail closed to lexical."""
        fallback = tuple(0.0 for _ in candidates)
        if self._semantic_scorer is None or not candidates:
            return fallback, False
        try:
            values = tuple(
                float(value)
                for value in self._semantic_scorer.score_many(
                    query,
                    tuple(candidate["text"] for candidate in candidates),
                )
            )
        except Exception:
            return fallback, True
        if len(values) != len(candidates) or any(
            not math.isfinite(value) or value < 0.0 or value > 1.0
            for value in values
        ):
            return fallback, True
        return values, False

    @staticmethod
    def _longest_ordered_phrase(left: tuple[str, ...], right: tuple[str, ...]) -> int:
        longest = 0
        for left_index in range(len(left)):
            for right_index in range(len(right)):
                size = 0
                while (
                    left_index + size < len(left)
                    and right_index + size < len(right)
                    and left[left_index + size] == right[right_index + size]
                ):
                    size += 1
                longest = max(longest, size)
        return longest

    @staticmethod
    def _is_broad_lens_query(lens: ContextLens, tokens: tuple[str, ...]) -> bool:
        if lens is ContextLens.GENERAL:
            return False
        return not tokens or set(tokens) <= _BROAD_LENS_TOKENS[lens]

    @staticmethod
    def _type_signal(
        item_type: str,
        query_tokens: tuple[str, ...],
    ) -> tuple[float, str | None]:
        """Use a small query-intent tie-breaker, never a relevance substitute."""
        base = _BASE_TYPE_SIGNAL.get(item_type, 0.0)
        intent_tokens = _QUERY_TYPE_TOKENS.get(item_type, set())
        if set(query_tokens) & intent_tokens:
            return base + 0.25, "query_type_intent"
        return base, None

    @staticmethod
    def _matches_project(item: dict[str, Any], project_id: str | None) -> bool:
        if project_id is None or item.get("relationship_key"):
            return True
        project_ids = item.get("project_ids", [])
        return project_id in project_ids or item.get("id") == project_id

    @staticmethod
    def _matches_status(item: dict[str, Any]) -> bool:
        if item.get("visibility", "visible") != "visible":
            return False
        status = item.get("status")
        return status is None or status in ("active", "open", "current")

    @staticmethod
    def _usable_continuity(item: dict[str, Any]) -> bool:
        return any(
            is_readable_continuity_text(value)
            for value in item.get("current_focus", [])
        ) or any(
            follow_up.get("status") == "open"
            and is_readable_continuity_text(follow_up.get("summary", ""))
            and is_readable_continuity_text(follow_up.get("reason_to_return", ""))
            for follow_up in item.get("intended_follow_ups", [])
        )

    @staticmethod
    def _importance(item: dict[str, Any], item_type: str) -> float:
        if "importance" in item:
            return float(item["importance"])
        if item_type == "continuity_state":
            priorities = [
                float(row.get("priority", 0.0))
                for row in item.get("intended_follow_ups", [])
                if row.get("status") == "open"
            ]
            return max(priorities, default=0.5)
        return 0.5

    def _recency(self, item: dict[str, Any]) -> float:
        parsed = self._timestamp(item)
        if parsed == datetime.min.replace(tzinfo=timezone.utc):
            return 0.0
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            now = now.replace(tzinfo=timezone.utc)
        age_days = max(0.0, (now.astimezone(timezone.utc) - parsed).total_seconds() / 86_400)
        if age_days <= 1:
            return 1.0
        if age_days <= 7:
            return 0.66
        if age_days <= 30:
            return 0.33
        return 0.0

    @staticmethod
    def _timestamp(item: dict[str, Any]) -> datetime:
        value = item.get("updated_at", item.get("created_at", ""))
        if not value:
            return datetime.min.replace(tzinfo=timezone.utc)
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return datetime.min.replace(tzinfo=timezone.utc)
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)

    @staticmethod
    def _estimated_chars(candidate: dict[str, Any]) -> int:
        # Count the same semantic payload shape that can reach Memory Context.
        # The fixed allowance covers record/type/source/status wrappers and
        # short grounding reasons without adding a tokenizer dependency.
        item_type = candidate["type"]
        item = candidate["data"]
        if item_type == "fact":
            payload = (item.get("subject"), item.get("key"), item.get("value"))
        elif item_type == "decision":
            payload = (item.get("title"), item.get("decision"))
        elif item_type == "commitment":
            payload = (item.get("text"),)
        elif item_type == "episode":
            payload = (item.get("title"), item.get("summary"), item.get("occurred_at"))
        elif item_type == "relationship_memory":
            payload = (item.get("kind"), item.get("title"), item.get("content"))
        elif item_type == "continuity_state":
            payload = (
                [
                    value
                    for value in item.get("current_focus", [])
                    if is_readable_continuity_text(value)
                ],
                [
                    {
                        "topic": row.get("topic"),
                        "summary": row.get("summary"),
                        "reason_to_return": row.get("reason_to_return"),
                        "revisit_after": row.get("revisit_after"),
                    }
                    for row in item.get("intended_follow_ups", [])
                    if row.get("status") == "open"
                    and is_readable_continuity_text(row.get("summary", ""))
                    and is_readable_continuity_text(
                        row.get("reason_to_return", "")
                    )
                ],
            )
        elif item_type == "reflection":
            payload = (
                item.get("text"),
                item.get("meaning"),
                item.get("confidence"),
                item.get("importance"),
                item.get("reconsiders_reflection_id"),
            )
        else:  # pragma: no cover - collection/type table prevents this branch
            payload = (candidate["text"],)
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
        return len(serialized) + 200
