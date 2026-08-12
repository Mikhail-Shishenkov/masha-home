# UI-06E — Commitments as Work Objects

UI-06E makes existing Commitments visible in the production Home without
turning Masha Home into a dashboard or creating a second task subsystem.

## Implemented path

```text
MemorySqliteRepository
→ existing MemoryDocument
→ existing TemporalEngine.commitment_status
→ bounded CommitmentListView
→ allowlisted LocalConversationBridge
→ spatial "Дела" surface
```

Completion remains explicit:

```text
user selects an open Commitment
→ existing MemoryIntentHandler proposal
→ PendingConfirmationView
→ explicit confirm/reject
→ existing ConfirmedMemoryService / SQLite audit
→ deterministic Activity result
```

## Human behaviour

- The small `Дела` object opens a temporary spatial shelf, not a permanent
  navigation panel.
- Items show human text, deterministic status and optional local deadline.
- Open, upcoming and overdue items can enter the existing completion proposal.
- Completed and cancelled items are read-only.
- Exact boundary remains unchanged: `due_at == now` is `open`; only
  `due_at < now` is `overdue`.

## Boundaries

- Frontend does not read SQLite, calculate time or mutate a Commitment.
- The LLM is not called to list, select, confirm or reject a Commitment.
- No UUID, payload, audit record or storage path is visible in normal UI.
- No scheduler, automatic completion, model fallback or new autonomous
  capability was added.

## Next slice

UI-06F should expose the existing activity/agent-run truth as a calm work
surface: current and recent execution, progress, pause/cancel where already
supported, and truthful stopped/failed states. It must not create a new agent
runtime or frontend-owned lifecycle.
