# UI-06D — Typed Commitment Confirmation and Activity

UI-06D connects the first real non-chat capability to the production Home.
It does not introduce a second commitment, proposal, or activity subsystem.

## Implemented path

```text
explicit conversation intent
→ existing MemoryIntentHandler
→ existing pending MemoryProposal
→ PendingConfirmationView
→ LocalConversationBridge.resolveConfirmation
→ existing proposal confirmation/rejection
→ ConfirmedMemoryService / SQLite audit
→ deterministic Activity presentation
→ human-readable result
```

The renderer receives a bounded projection containing the operation type,
human text, optional due time and allowed actions. Proposal IDs remain opaque
bridge tokens and are not shown in the normal conversation transcript.

## Behaviour

- A Commitment proposal opens a focused decision surface near the table.
- `Подтверждаю` calls the existing explicit confirmation path.
- `Не сейчас` cancels the existing proposal and performs no memory mutation.
- The short local operation uses the existing Activity lifecycle and reports
  only deterministic states: applying, completed, or failed.
- A pending Commitment confirmation survives application restart.
- Ordinary conversation remains separate from long-term Memory.

## Boundaries

- The frontend does not parse due dates or decide proposal type.
- The LLM cannot confirm, reject, or mutate a Commitment.
- No proposal payload, SQLite field, audit detail, or path reaches the renderer.
- No scheduler, proactive delivery, agent execution, model fallback or new
  autonomous capability was added.

## Next slice

Expose a calm read-only list of existing Commitments and their deterministic
temporal status, then let an explicitly selected Commitment enter the already
implemented completion proposal/confirmation flow.
