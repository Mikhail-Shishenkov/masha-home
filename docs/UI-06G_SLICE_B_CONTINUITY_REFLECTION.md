# UI-06G — Slice B: Continuity, Reflection and Honest Help

Status: **IMPLEMENTED**

## Purpose

Slice B brings the already implemented Memory, Shared Continuity, Masha
Reflection and Honest Help capabilities into the production Home without
turning them into a dashboard or giving the renderer domain access.

## Production path

```text
SQLite-backed domain services
→ UI-safe application projections
→ allowlisted desktop bridge
→ contextual Home object
→ explicit user action, where one is required
```

Two contextual objects are available only when real local data exists:

- `Наша история` opens a bounded, read-only view of confirmed Facts,
  Decisions and Episodes, relationship moments and open follow-up threads;
- `Мысли` opens adopted Masha reflections, pending reflection candidates and
  pending Honest Help offers.

Neither object exposes raw `MemoryDocument`, evidence message IDs, audit rows,
proposal payloads, repository handles or SQLite details to the visible UI.

## Mutation boundary

Reading continuity never mutates Memory. Returning to an open thread only
prefills the conversation composer; it does not send a message automatically.

A proposed reflection remains an interpretation until Misha explicitly adopts
it. Rejecting it does not create a reflection. An Honest Help offer invokes the
active local model only after explicit acceptance. Dismissal does not invoke a
model. Both actions reuse the existing Stage 15 services and audit lifecycle.

Emergency Stop and an in-flight operation block reflection and Honest Help
actions. No action in this slice may change Identity, Commitment, Temporal
state, model profiles or proactive policy.

## Presentation grammar

Continuity is a warm shared-history surface. Reflection is a separate opinion
surface so that a Masha interpretation cannot visually masquerade as a known
fact. Pending items provide only their existing typed actions; adopted
reflections are read-only.

The renderer chooses no facts, dates, confidence values or model. It only
renders the bounded application contract and sends an opaque candidate ID back
through a specific allowlisted action.

## Deliberate limitations

- there is no generic memory editor in the Home;
- there is no automatic reflection adoption;
- Honest Help is not proactive autonomous execution;
- the LLM does not choose layout, lifecycle or whether an offer may run;
- empty categories do not become permanent navigation.

## Next

Slice C: Skills, Permissions, Agent Runs and Model Profiles as one coherent
work-corner grammar, while preserving Emergency Stop and explicit permission
boundaries.
