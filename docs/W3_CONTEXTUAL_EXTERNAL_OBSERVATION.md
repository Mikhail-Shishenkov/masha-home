# W3 — Contextual External Observation

W3 makes an already explicit web request easier to phrase. It does not grant
internet authority: Memory and Recall resolve a local reference; the current
explicit user request is the only authorization.

## Boundary

The search provider receives only the final normalized public query and its
existing provider parameters. It never receives Memory, conversation history,
Identity, project or entity IDs, continuity records, commitments, reflections,
or hint provenance. Observation receipts store the final public query only.

W3 context is represented inside Home as at most five typed human-readable
hints (`memory`, `decision`, `episode`, `shared_moment`, `task`, `thread`, one
selected `active_thread`, or one `masha_reflection`). A hint is at most 400
characters and all hint text is at most 1,500 characters. The local planner
remains `LOCAL_ONLY` with `tools=False` and returns one public query or
`CLARIFY`.

## Selection rules

- Self-contained named requests remain W1 deterministic planning and do not
  run W3 Recall.
- Recent conversation stays bounded and local-only.
- A selected open active thread may contribute one strong hint.
- Existing Human Information/Recall supplies at most three current hints.
- Archived information is considered only by existing explicit retrospective
  Recall semantics.
- Forgotten records and pending memory candidates never contribute.
- A reflection is considered only for an explicit reference to Masha's own
  prior idea or thought; it identifies a topic, not factual truth.
- Competing candidates without an active selected thread fail closed with a
  clarification and no provider call.

## Manual acceptance

1. Discuss a named public project, then ask: «Маш, проверь, вышло ли у него
   что-нибудь новое».
2. In a fresh conversation, use a current saved memory in an explicit
   referential search request.
3. Select an open continuity thread and ask: «Маш, посмотри, что нового по
   этой теме».
4. Explicitly mention Masha's prior OpenHands thought and ask what is new.
5. Create two plausible model candidates; «обновилась ли та модель» must ask
   which one and make no network request.
