# Masha Home Memory Specification v0.3

## Core entities

### Identity
An actor known to the system. v0.3 uses string codes: `misha`, `masha`, `system`.
A full Identity Registry with UUIDs is postponed.

### Fact
Relatively stable knowledge about the user, world, or project.
A Fact is not a Decision.

Fields:
- id
- subject
- key
- value
- status
- importance
- confidence
- source
- owner
- known_by (`string[]`)
- created_at
- updated_at

Status: `active`, `superseded`, `archived`.

A Fact may be global or linked to 1..N Projects.

### Decision
A conscious choice together with its reason.

Fields:
- id
- title
- decision
- reason
- status
- created_at
- updated_at

A Decision may be global or linked to 0..N Projects.
Status: `active`, `superseded`, `cancelled`.

### Commitment
An obligation or promise.

Fields:
- id
- text
- owner
- status
- created_at
- updated_at
- due_at (optional)
- completed_at (optional)
- importance (optional)
- source_episode (optional)

Every Commitment has exactly one owner.
It may be global or linked to 0..N Projects.

Status: `open`, `completed`, `cancelled`, `expired`.

When a Project is archived, only project-bound Commitments become `expired`. History is never deleted.

### Episode
A meaningful event or fragment of history.

Fields:
- id
- title
- summary
- occurred_at
- source
- importance
- context
- produced
- updated
- created_at

Context may include Projects, participants, and topics.

An Episode records explicit relationships to objects it produces, updates, or supersedes.

### Project
The main working context.

Fields:
- id
- name
- description (optional)
- status
- created_at
- updated_at
- archived_at (optional)
- working_memory

Status: `active`, `paused`, `completed`, `archived`.

A Project may link to 0..N Facts, 1..N Episodes, 0..N Decisions, and 0..N Commitments.

## Working Memory

Working Memory belongs to a Project and contains:
- current_blockers
- open_questions
- architecture_notes
- next_actions

It represents current state, not history.

Rule:

> A significant change to Working Memory must have a historical basis: normally an Episode, Decision, or Fact update.

Working Memory should be reconstructable from historical memory.

## Supersession

`Fact A -> superseded_by -> Fact B` changes current interpretation without deleting history.

Historical Project references to A are not automatically rewritten.

Current-state resolution happens at the application/memory-service layer.

Conceptual operations:
- `resolve_current(id)`
- `get_historical(id)`

Supersession chains must be acyclic.

## Episode relationships

```json
{
  "produced": {
    "facts": [],
    "decisions": [],
    "commitments": [],
    "project_changes": []
  },
  "updated": {
    "facts": [],
    "projects": [],
    "commitments": []
  },
  "superseded": {
    "facts": [],
    "decisions": [],
    "commitments": []
  }
}
```

## Source and confidence

Source types:
- `explicit_user_input`
- `conversation`
- `system`
- `inference`

Inferred information must not silently become a high-confidence Fact.

Importance and confidence use the range `0.0..1.0`.

## Time

Current time is runtime state, not a permanent memory value.

Store:
- timezone/configuration
- last_interaction

Calculate at runtime:
- current datetime
- elapsed time
- temporal relevance

## Architectural principles

1. Fact = knowledge.
2. Decision = conscious choice + reason.
3. Commitment = obligation + owner.
4. Episode = history.
5. Project = working context.
6. Working Memory = current state, not history.
7. Significant Working Memory changes require historical grounding.
8. Historical references are immutable.
9. Supersession is resolved at application level.
10. Supersession must never create cycles.
11. Inference must not silently become trusted fact.
12. Time-sensitive state is calculated at runtime.
13. v0.3 uses string identity codes, not UUIDs.
14. Prefer reconstructable state over destructive updates.
