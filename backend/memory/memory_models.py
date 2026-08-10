from enum import Enum
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)


NonEmptyStr = Annotated[str, Field(min_length=1)]
Score = Annotated[float, Field(ge=0.0, le=1.0)]


class IdentityCode(str, Enum):
    MISHA = "misha"
    MASHA = "masha"
    SYSTEM = "system"


class SourceType(str, Enum):
    EXPLICIT_USER_INPUT = "explicit_user_input"
    CONVERSATION = "conversation"
    SYSTEM = "system"
    INFERENCE = "inference"


class Visibility(str, Enum):
    VISIBLE = "visible"
    HIDDEN = "hidden"


class ProjectStatus(str, Enum):
    ACTIVE = "active"
    DORMANT = "dormant"
    COMPLETED = "completed"


class FactStatus(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"


class DecisionStatus(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"


class CommitmentStatus(str, Enum):
    OPEN = "open"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class CandidateType(str, Enum):
    FACT = "fact"
    DECISION = "decision"
    COMMITMENT = "commitment"
    REFLECTION = "reflection"
    RELATIONSHIP_MEMORY = "relationship_memory"
    AFFECTIVE_RECORD = "affective_record"


class CandidateStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class RelationshipKind(str, Enum):
    SHARED_MILESTONE = "shared_milestone"
    INTERACTION_PREFERENCE = "interaction_preference"
    HELPFUL_PATTERN = "helpful_pattern"
    SHARED_SYMBOL = "shared_symbol"
    BOUNDARY = "boundary"
    RELATIONSHIP_NOTE = "relationship_note"


class RelationshipStatus(str, Enum):
    CURRENT = "current"
    REVISED = "revised"


class AffectiveStatus(str, Enum):
    ACTIVE = "active"
    RESOLVED = "resolved"


class FollowUpStatus(str, Enum):
    OPEN = "open"
    SNOOZED = "snoozed"
    RESOLVED = "resolved"


UNIQUE_LIST_FIELDS = {
    "known_by",
    "project_ids",
    "source_episode_ids",
    "participants",
    "topics",
    "related_memory_ids",
    "facts",
    "decisions",
    "commitments",
    "reflections",
    "relationship_memories",
    "affective_records",
    "project_changes",
    "continuity_states",
    "evidence_episode_ids",
    "cause_episode_ids",
    "affective_record_ids",
    "current_focus",
    "based_on_episode_ids",
    "source_memory_ids",
}


class StrictMemoryModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    @field_validator("*")
    @classmethod
    def validate_unique_lists(cls, value, info):
        if info.field_name not in UNIQUE_LIST_FIELDS or not isinstance(value, list):
            return value

        comparable = [
            item.value
            if isinstance(item, Enum)
            else item.id
            if isinstance(item, BaseModel) and hasattr(item, "id")
            else item
            for item in value
        ]
        if len(comparable) != len(set(comparable)):
            raise ValueError(f"{info.field_name} must contain unique values")
        return value


class Project(StrictMemoryModel):
    id: NonEmptyStr
    name: NonEmptyStr
    description: str | None
    status: ProjectStatus
    created_at: AwareDatetime
    updated_at: AwareDatetime
    completed_at: AwareDatetime | None

    @model_validator(mode="after")
    def validate_completion(self):
        if self.status == ProjectStatus.COMPLETED and self.completed_at is None:
            raise ValueError("completed Project requires completed_at")
        if self.status != ProjectStatus.COMPLETED and self.completed_at is not None:
            raise ValueError("non-completed Project cannot have completed_at")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at")
        return self


class Fact(StrictMemoryModel):
    id: NonEmptyStr
    subject: NonEmptyStr
    key: NonEmptyStr
    value: JsonValue
    status: FactStatus
    visibility: Visibility
    importance: Score
    confidence: Score
    source: SourceType
    owner: IdentityCode
    known_by: list[IdentityCode]
    project_ids: list[NonEmptyStr]
    source_episode_ids: list[NonEmptyStr]
    superseded_by: NonEmptyStr | None
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @model_validator(mode="after")
    def validate_lifecycle(self):
        if self.status == FactStatus.SUPERSEDED and self.superseded_by is None:
            raise ValueError("superseded Fact requires superseded_by")
        if self.status == FactStatus.ACTIVE and self.superseded_by is not None:
            raise ValueError("active Fact cannot have superseded_by")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at")
        return self


class Decision(StrictMemoryModel):
    id: NonEmptyStr
    title: NonEmptyStr
    decision: NonEmptyStr
    reason: NonEmptyStr
    status: DecisionStatus
    visibility: Visibility
    project_ids: list[NonEmptyStr]
    source: SourceType
    source_episode_ids: list[NonEmptyStr]
    superseded_by: NonEmptyStr | None
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @model_validator(mode="after")
    def validate_lifecycle(self):
        if self.status == DecisionStatus.SUPERSEDED and self.superseded_by is None:
            raise ValueError("superseded Decision requires superseded_by")
        if self.status != DecisionStatus.SUPERSEDED and self.superseded_by is not None:
            raise ValueError("only superseded Decision can have superseded_by")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at")
        return self


class Commitment(StrictMemoryModel):
    id: NonEmptyStr
    text: NonEmptyStr
    owner: IdentityCode
    status: CommitmentStatus
    visibility: Visibility
    project_ids: list[NonEmptyStr]
    due_at: AwareDatetime | None
    completed_at: AwareDatetime | None
    importance: Score
    source: SourceType
    source_episode_ids: list[NonEmptyStr]
    replaces_id: NonEmptyStr | None
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @model_validator(mode="after")
    def validate_lifecycle(self):
        if self.status == CommitmentStatus.COMPLETED and self.completed_at is None:
            raise ValueError("completed Commitment requires completed_at")
        if self.status != CommitmentStatus.COMPLETED and self.completed_at is not None:
            raise ValueError("non-completed Commitment cannot have completed_at")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at")
        return self


class EpisodeProduced(StrictMemoryModel):
    facts: list[NonEmptyStr]
    decisions: list[NonEmptyStr]
    commitments: list[NonEmptyStr]
    reflections: list[NonEmptyStr]
    relationship_memories: list[NonEmptyStr]
    affective_records: list[NonEmptyStr]
    project_changes: list[NonEmptyStr]


class EpisodeUpdated(StrictMemoryModel):
    facts: list[NonEmptyStr]
    decisions: list[NonEmptyStr]
    commitments: list[NonEmptyStr]
    continuity_states: list[NonEmptyStr]
    projects: list[NonEmptyStr]


class EpisodeSuperseded(StrictMemoryModel):
    facts: list[NonEmptyStr]
    decisions: list[NonEmptyStr]
    commitments: list[NonEmptyStr]


class Episode(StrictMemoryModel):
    id: NonEmptyStr
    title: NonEmptyStr
    summary: NonEmptyStr
    occurred_at: AwareDatetime
    source: SourceType
    importance: Score
    visibility: Visibility
    project_ids: list[NonEmptyStr]
    participants: list[IdentityCode]
    topics: list[NonEmptyStr]
    produced: EpisodeProduced
    updated: EpisodeUpdated
    superseded: EpisodeSuperseded
    related_memory_ids: list[NonEmptyStr]
    created_at: AwareDatetime


class MemoryCandidate(StrictMemoryModel):
    id: NonEmptyStr
    candidate_type: CandidateType
    proposed_payload: dict[str, JsonValue]
    status: CandidateStatus
    confidence: Score
    source: SourceType
    project_ids: list[NonEmptyStr]
    evidence_episode_ids: list[NonEmptyStr]
    created_by: IdentityCode
    reviewed_by: IdentityCode | None
    created_at: AwareDatetime
    reviewed_at: AwareDatetime | None
    result_memory_id: NonEmptyStr | None

    @model_validator(mode="after")
    def validate_review(self):
        reviewed = self.status in {
            CandidateStatus.APPROVED,
            CandidateStatus.REJECTED,
        }
        if reviewed and (self.reviewed_by is None or self.reviewed_at is None):
            raise ValueError("reviewed candidate requires reviewer and reviewed_at")
        if self.status == CandidateStatus.APPROVED and self.result_memory_id is None:
            raise ValueError("approved candidate requires result_memory_id")
        if self.status != CandidateStatus.APPROVED and self.result_memory_id is not None:
            raise ValueError("only approved candidate can have result_memory_id")
        if not reviewed and (self.reviewed_by is not None or self.reviewed_at is not None):
            raise ValueError("unreviewed candidate cannot have review metadata")
        return self


class MashaReflection(StrictMemoryModel):
    id: NonEmptyStr
    text: NonEmptyStr
    meaning: NonEmptyStr
    importance: Score
    confidence: Score
    source: SourceType
    visibility: Visibility
    project_ids: list[NonEmptyStr]
    source_episode_ids: list[NonEmptyStr]
    related_memory_ids: list[NonEmptyStr]
    reconsiders_reflection_id: NonEmptyStr | None
    created_at: AwareDatetime


class RelationshipMemory(StrictMemoryModel):
    id: NonEmptyStr
    kind: RelationshipKind
    title: NonEmptyStr
    content: JsonValue
    status: RelationshipStatus
    visibility: Visibility
    importance: Score
    confidence: Score
    source: SourceType
    project_ids: list[NonEmptyStr]
    source_episode_ids: list[NonEmptyStr]
    revises_id: NonEmptyStr | None
    created_at: AwareDatetime


class AffectiveRecord(StrictMemoryModel):
    id: NonEmptyStr
    emotion: NonEmptyStr
    description: NonEmptyStr
    intensity: Score
    significance: Score
    status: AffectiveStatus
    source: SourceType
    visibility: Visibility
    project_ids: list[NonEmptyStr]
    cause_episode_ids: list[NonEmptyStr]
    related_memory_ids: list[NonEmptyStr]
    reflection_id: NonEmptyStr | None
    started_at: AwareDatetime
    updated_at: AwareDatetime
    resolved_at: AwareDatetime | None

    @model_validator(mode="after")
    def validate_lifecycle(self):
        if not self.cause_episode_ids and self.source != SourceType.SYSTEM:
            raise ValueError("non-system AffectiveRecord requires a cause Episode")
        if self.status == AffectiveStatus.RESOLVED and self.resolved_at is None:
            raise ValueError("resolved AffectiveRecord requires resolved_at")
        if self.status == AffectiveStatus.ACTIVE and self.resolved_at is not None:
            raise ValueError("active AffectiveRecord cannot have resolved_at")
        if self.updated_at < self.started_at:
            raise ValueError("updated_at cannot be earlier than started_at")
        return self


class ContinuityFollowUp(StrictMemoryModel):
    id: NonEmptyStr
    topic: NonEmptyStr
    summary: NonEmptyStr
    reason_to_return: NonEmptyStr
    priority: Score
    status: FollowUpStatus
    source_memory_ids: list[NonEmptyStr]
    revisit_after: AwareDatetime | None


class ContinuityState(StrictMemoryModel):
    id: NonEmptyStr
    relationship_key: NonEmptyStr
    last_interaction_at: AwareDatetime | None
    affective_record_ids: list[NonEmptyStr]
    current_focus: list[NonEmptyStr]
    intended_follow_ups: list[ContinuityFollowUp]
    based_on_episode_ids: list[NonEmptyStr]
    updated_at: AwareDatetime

    @field_validator("intended_follow_ups")
    @classmethod
    def validate_follow_up_ids(cls, value: list[ContinuityFollowUp]):
        ids = [item.id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("intended_follow_ups must have unique ids")
        return value


class MemoryDocument(StrictMemoryModel):
    schema_version: Literal["0.4"]
    identity_version: NonEmptyStr
    projects: list[Project]
    facts: list[Fact]
    decisions: list[Decision]
    commitments: list[Commitment]
    episodes: list[Episode]
    memory_candidates: list[MemoryCandidate]
    reflections: list[MashaReflection]
    relationship_memories: list[RelationshipMemory]
    affective_records: list[AffectiveRecord]
    continuity_states: list[ContinuityState]

    @model_validator(mode="after")
    def validate_references(self):
        collections = {
            "project": self.projects,
            "fact": self.facts,
            "decision": self.decisions,
            "commitment": self.commitments,
            "episode": self.episodes,
            "candidate": self.memory_candidates,
            "reflection": self.reflections,
            "relationship": self.relationship_memories,
            "affective": self.affective_records,
            "continuity": self.continuity_states,
        }
        id_to_type: dict[str, str] = {}
        for item_type, items in collections.items():
            for item in items:
                if item.id in id_to_type:
                    raise ValueError(f"duplicate memory id: {item.id}")
                id_to_type[item.id] = item_type

        project_ids = {item.id for item in self.projects}
        episode_ids = {item.id for item in self.episodes}
        fact_ids = {item.id for item in self.facts}
        decision_ids = {item.id for item in self.decisions}
        commitment_ids = {item.id for item in self.commitments}
        reflection_ids = {item.id for item in self.reflections}
        relationship_ids = {item.id for item in self.relationship_memories}
        affective_ids = {item.id for item in self.affective_records}
        continuity_ids = {item.id for item in self.continuity_states}

        project_linked = [
            *self.facts,
            *self.decisions,
            *self.commitments,
            *self.episodes,
            *self.memory_candidates,
            *self.reflections,
            *self.relationship_memories,
            *self.affective_records,
        ]
        for item in project_linked:
            self._require_subset(item.project_ids, project_ids, "project")

        for fact in self.facts:
            self._require_subset(fact.source_episode_ids, episode_ids, "episode")
            if fact.superseded_by is not None:
                self._require_reference(fact.superseded_by, fact_ids, "fact")
        for decision in self.decisions:
            self._require_subset(decision.source_episode_ids, episode_ids, "episode")
            if decision.superseded_by is not None:
                self._require_reference(decision.superseded_by, decision_ids, "decision")
        for commitment in self.commitments:
            self._require_subset(commitment.source_episode_ids, episode_ids, "episode")
            if commitment.replaces_id is not None:
                self._require_reference(
                    commitment.replaces_id,
                    commitment_ids,
                    "commitment",
                )

        for episode in self.episodes:
            self._require_subset(episode.produced.facts, fact_ids, "fact")
            self._require_subset(episode.produced.decisions, decision_ids, "decision")
            self._require_subset(
                episode.produced.commitments,
                commitment_ids,
                "commitment",
            )
            self._require_subset(
                episode.produced.reflections,
                reflection_ids,
                "reflection",
            )
            self._require_subset(
                episode.produced.relationship_memories,
                relationship_ids,
                "relationship memory",
            )
            self._require_subset(
                episode.produced.affective_records,
                affective_ids,
                "affective record",
            )
            self._require_subset(
                episode.produced.project_changes,
                project_ids,
                "project",
            )
            self._require_subset(episode.updated.facts, fact_ids, "fact")
            self._require_subset(episode.updated.decisions, decision_ids, "decision")
            self._require_subset(
                episode.updated.commitments,
                commitment_ids,
                "commitment",
            )
            self._require_subset(
                episode.updated.continuity_states,
                continuity_ids,
                "continuity state",
            )
            self._require_subset(episode.updated.projects, project_ids, "project")
            self._require_subset(episode.superseded.facts, fact_ids, "fact")
            self._require_subset(
                episode.superseded.decisions,
                decision_ids,
                "decision",
            )
            self._require_subset(
                episode.superseded.commitments,
                commitment_ids,
                "commitment",
            )
            self._require_subset(
                episode.related_memory_ids,
                set(id_to_type),
                "memory",
            )

        for candidate in self.memory_candidates:
            self._require_subset(
                candidate.evidence_episode_ids,
                episode_ids,
                "episode",
            )
            if candidate.result_memory_id is not None:
                self._require_reference(
                    candidate.result_memory_id,
                    set(id_to_type),
                    "memory",
                )
                expected_type = {
                    CandidateType.FACT: "fact",
                    CandidateType.DECISION: "decision",
                    CandidateType.COMMITMENT: "commitment",
                    CandidateType.REFLECTION: "reflection",
                    CandidateType.RELATIONSHIP_MEMORY: "relationship",
                    CandidateType.AFFECTIVE_RECORD: "affective",
                }[candidate.candidate_type]
                if id_to_type[candidate.result_memory_id] != expected_type:
                    raise ValueError(
                        "candidate result type does not match candidate_type"
                    )
        for reflection in self.reflections:
            self._require_subset(
                reflection.source_episode_ids,
                episode_ids,
                "episode",
            )
            self._require_subset(
                reflection.related_memory_ids,
                set(id_to_type),
                "memory",
            )
            if reflection.reconsiders_reflection_id is not None:
                self._require_reference(
                    reflection.reconsiders_reflection_id,
                    reflection_ids,
                    "reflection",
                )
        for relationship in self.relationship_memories:
            self._require_subset(
                relationship.source_episode_ids,
                episode_ids,
                "episode",
            )
            if relationship.revises_id is not None:
                self._require_reference(
                    relationship.revises_id,
                    relationship_ids,
                    "relationship memory",
                )
        for affective in self.affective_records:
            self._require_subset(
                affective.cause_episode_ids,
                episode_ids,
                "episode",
            )
            self._require_subset(
                affective.related_memory_ids,
                set(id_to_type),
                "memory",
            )
            if affective.reflection_id is not None:
                self._require_reference(
                    affective.reflection_id,
                    reflection_ids,
                    "reflection",
                )
        for continuity in self.continuity_states:
            self._require_subset(
                continuity.affective_record_ids,
                affective_ids,
                "affective record",
            )
            self._require_subset(
                continuity.based_on_episode_ids,
                episode_ids,
                "episode",
            )
            for follow_up in continuity.intended_follow_ups:
                self._require_subset(
                    follow_up.source_memory_ids,
                    set(id_to_type),
                    "memory",
                )

        self._validate_acyclic_supersession(self.facts)
        self._validate_acyclic_supersession(self.decisions)
        self._validate_acyclic_links(self.commitments, "replaces_id")
        self._validate_acyclic_links(
            self.reflections,
            "reconsiders_reflection_id",
        )
        self._validate_acyclic_links(self.relationship_memories, "revises_id")
        return self

    @staticmethod
    def _require_reference(value: str, allowed: set[str], label: str):
        if value not in allowed:
            raise ValueError(f"unknown {label} reference: {value}")

    @classmethod
    def _require_subset(
        cls,
        values: list[str],
        allowed: set[str],
        label: str,
    ):
        for value in values:
            cls._require_reference(value, allowed, label)

    @staticmethod
    def _validate_acyclic_supersession(items):
        MemoryDocument._validate_acyclic_links(items, "superseded_by")

    @staticmethod
    def _validate_acyclic_links(items, field_name: str):
        next_by_id = {
            item.id: getattr(item, field_name)
            for item in items
            if getattr(item, field_name) is not None
        }
        for start in next_by_id:
            seen: set[str] = set()
            current = start
            while current in next_by_id:
                if current in seen:
                    raise ValueError(f"supersession cycle detected at {current}")
                seen.add(current)
                current = next_by_id[current]
