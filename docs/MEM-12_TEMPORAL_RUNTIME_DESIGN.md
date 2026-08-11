# MEM-12 — Temporal Runtime, Event Recovery & Proactive Behaviour Foundation

Status: **MEM-12.1–MEM-12.9 IMPLEMENTED. External events and external delivery remain out of scope.**

This document updates MEM-12 on the LLM-03 baseline (`267041b`). Masha is
intended to become a local companion that can initiate appropriate contact over
time. That capability is controlled by a separate local policy — it is neither
an LLM permission nor part of Masha's identity.

MEM-12.1 authorises only deterministic local event recovery and pure proactive
permission evaluation. It does not authorise a SQLite migration, scheduler,
delivery subsystem, LLM call, external source, network callback, or autonomous
external action.

## 1. Architectural boundaries

```text
Clock
  -> Temporal Engine
  -> Temporal Runtime
  -> Event Detection + Event Store / Recovery State
  -> Proactive Decision Engine
       -> suppress
       -> local user-facing message
       -> action proposal -> existing explicit confirmation flow
```

The four responsibilities are independent:

| Layer | Owns | Must not own |
| --- | --- | --- |
| Temporal Runtime | Time and temporal state observation | Wording, delivery, memory mutation |
| Event Detection | Whether a normalized event exists | Initiative permission |
| Proactive Decision | Whether a message is appropriate now | Time calculation, event creation, mutation |
| User-facing Interaction | Human wording and local delivery | Authority to silently change state |

`ConversationService` remains the user-interaction boundary. A future local
delivery runtime may call the same interaction surface for a message already
authorised by `ProactiveDecision`; it must not bypass policy or memory
confirmation rules.

Identity answers “who Masha is”. Memory answers “what Masha knows”. Temporal
Runtime answers “what changed over time”. Proactive Policy answers “whether
Masha may begin contact now”. None replaces another.

## 2. Current factual baseline and constraints

MEM-11 owns time. UTC is canonical, Moscow UTC+03:00 is the offline display
configuration, and `TemporalEngine` deterministically calculates commitment
status. `due_at == now` remains `open`; only `due_at < now` is `overdue`.
Completed and cancelled Commitments are never overdue.

The repository already contains an unconnected foundation from `3085fde`:

- migration v2 created the local `temporal_events` table with uniqueness over
  `(event_type, source_type, source_id, due_at)`;
- `TemporalRuntime` can create and advance rows, but is not connected to CLI
  or `ConversationService`, has no tests, and its random UUID is not a stable
  event identity;
- its `scheduled/due/missed` vocabulary is not yet this design contract.

Future work evolves this existing local path; it must not introduce a second
memory subsystem. Existing Identity runtime/manifest, SQLite memory schema,
MemoryRetriever, memory proposal-confirmation flow, Temporal Engine MEM-11,
conversation history, ModelProfileStore, ModelRouter and OllamaProvider remain
unchanged unless separately approved.

## 3. Event detection and recovery

At a defined local runtime invocation, detection reads the existing Memory
document and `TemporalEngine`; it never asks an LLM whether an event exists.

Current deterministic event sources:

1. `commitment_due` for every visible open Commitment with `due_at`;
2. `user_return` derived from existing last interaction and absence duration,
   but only after a future policy has supplied a meaningful threshold;
3. source termination when an event's Commitment becomes completed/cancelled.

There is no generic “new temporal fact” source today. A new typed source can
be added only after a separate data-contract decision; normal chat never
creates a temporal event.

On restart, recovery detects the same events that would have been detected
while the process was offline. It records deterministic recovery provenance and
returns the same event identity. It does not mutate MemoryDocument, create a
memory proposal, complete a Commitment, or automatically send a message.

## 4. Event identity, state, and idempotence

The canonical event key for a deadline is the canonical UTF-8 tuple:

```text
temporal-event:v1 | commitment_due | commitment | <commitment_id> | <due_at_utc_iso8601>
```

`event_id` is `tev1_` plus a SHA-256 digest of that tuple. The existing SQLite
unique constraint remains a second guard. Repeated detection/restart therefore
does an idempotent lookup/upsert in one local transaction and cannot create a
new event or a second proactive decision for the same occurrence.

Event state is distinct from Commitment state:

| State | Meaning |
| --- | --- |
| `pending` | Future source deadline was registered. |
| `due` | Detected at its exact deadline. |
| `overdue` | Detected after the deadline while source is open. |
| `acknowledged` | User saw it; Commitment is still independent. |
| `ignored` | User suppressed it; this does not mutate Memory. |
| `completed` | Source Commitment is terminally completed. |
| `cancelled` | Source Commitment is terminally cancelled. |

`recovered` is detection provenance (`recovery_at`, later `detection_origin`),
not a competing state: an event remains semantically `due` or `overdue`.
“Missed” is not needed; a missed deadline is an overdue event found during
recovery.

| Boundary | Commitment status | Event result |
| --- | --- | --- |
| `due_at > now` | `open` | `pending`; no alert decision is implied. |
| `due_at == now` | `open` | No MEM-12.1 event; exact boundary remains MEM-11 `open`. |
| `due_at < now` | `overdue` | `overdue`. |
| restart after deadline | `overdue` | same event, with recovery provenance. |
| completed/cancelled after deadline | terminal | no overdue notification. |
| several deadlines | independently computed | stable order by due time and event key. |

## 5. Proactivity is operating policy, not personality

Proactivity does not belong in the approved Identity manifest. It is a local,
human-controlled operating policy. Its levels describe permitted *initiation*,
not model capability:

| Level | Permission |
| --- | --- |
| 0 — Reactive | Reply only to an explicit user interaction. |
| 1 — Helpful reminder | Initiate a local reminder for an eligible commitment/deadline. |
| 2 — Continuity | Reopen an eligible unfinished shared topic. |
| 3 — Support/check-in | Send a cautious local check-in when sufficient existing context exists. |
| 4 — Safety/urgent alert | Deliver a validated high-severity informational alert. |
| 5 — External action | Forbidden in MEM-12; requires a separate permission and confirmation architecture. |

Levels 1–4 permit at most a user-facing local message that passed policy. They
do not permit marking a report complete, changing a Commitment, writing memory,
sending a message to another person, invoking a service, changing a model, or
performing any outside-world action.

The default and chosen level are deliberately not set by this document. They
are Misha's explicit operating settings, separate from identity.

## 6. Proactive Decision Engine

`ProactiveDecisionEngine` is deterministic and auditable. It consumes a
normalized event, local user context, prior event/delivery state and the active
policy; it returns exactly one decision:

```text
SUPPRESS | REMIND | CHECK_IN | URGENT_ALERT | REQUIRE_CONFIRMATION
```

It must evaluate, without an LLM:

```text
event + priority + confidence + current policy + recent interaction
+ cooldown + quiet-hours + past handling -> decision
```

Required anti-spam controls are policy fields, not prompt advice:

- proactive enabled/disabled and maximum initiative level;
- minimum interval and cooldown per event type;
- maximum messages per defined period;
- quiet hours and timezone;
- event priority/urgency/confidence threshold;
- user dismissal/ignore suppression;
- explicit “не надо” suppression;
- deduplication by stable event ID and recorded delivery/acknowledgement;
- escalation only where configured severity and validated evidence warrant it.

The engine must never implement “event exists → send message”. If policy is
absent/disabled, the event is acknowledged/ignored/terminal, quiet hours apply,
cooldown applies, or budget is exhausted, the result is `SUPPRESS`.

## 7. Absence, continuity, and support

Absence is a cautious trigger, never a diagnosis. The current system knows
`last_interaction_at` and `absence_duration_seconds`; it does not know why a
person was absent. A future `user_return`/`SUPPORT_CHECK_IN` candidate requires
configured duration plus concrete existing context, such as an unfinished
important commitment or an explicitly recorded return intention.

It must not infer medical, psychological or personal causes. Its permitted
wording is gentle and conditional: “Миша, тебя давно не было. Надеюсь, всё
нормально. Если что — я здесь.” It must not claim that something is wrong.

## 8. LLM and interaction contract

LLM may receive bounded, already-normalized `TemporalEventContext`,
IdentityContext, selected memory and TemporalContext. It may formulate a warm,
natural local message and choose wording; it is not the source of temporal
truth or initiative authority.

LLM must not create events, parse/compute due dates, classify overdue, decide
to initiate contact, run recovery, mutate temporal state, write memory without
confirmation, or perform external action. A deterministic policy decision is
required before any proactive message is composed or delivered.

Human-first future local UX may include:

```text
events list | events overdue | events acknowledge <number> | events ignore <number>
proactive status | proactive on | proactive off | proactive level <0-4>
proactive quiet <HH:MM-HH:MM>
```

Ordinary output contains commitment text, local deadline and current status;
IDs, hashes and internal state appear only through `--raw`/debug/audit. These
commands are design only.

## 9. Delivery, confirmation, and external boundaries

| Operation | Can happen automatically if policy permits? | Confirmation required? |
| --- | --- | --- |
| Detect/recover local temporal event | yes | no |
| Suppress a candidate | yes | no |
| Compose/deliver local proactive message | only after policy decision | no extra confirmation, but policy must be user-configured |
| Acknowledge/ignore event from explicit command | no | explicit user command |
| Complete/cancel/edit Commitment or mutate memory | no | existing proposal-confirmation flow |
| Any action outside Masha Home | no | separate future authority model |

External information is a separate future branch, never part of Temporal
Engine:

```text
External source -> validation -> normalization -> relevance/geography
-> confidence/freshness -> safety/information event -> ProactiveDecision
```

No external source is connected in MEM-12. A local system cannot know an
external event without a defined source. A future `SAFETY_ALERT` requires a
named source, timestamp, freshness, geography/relevance, confidence, severity,
and user-visible attribution. Missing or stale evidence is suppressed; no
unverified statement may be presented as fact.

## 10. Storage and potential schema changes

`temporal_events` is the proposed local Event Store, adjacent to SQLite memory
but not a second Memory subsystem. Its v2 columns can support the first narrow
path if `id` becomes deterministic and timestamps are used carefully.
`audit_events` can record transitions diagnostically.

Potential migration — proposal only, not approved or implemented:

- `event_key TEXT UNIQUE` separate from opaque ID;
- `detected_at`, `acknowledged_at`, `ignored_at`, `terminal_at`;
- `detection_origin` (`live` / `recovery`), `last_action`, `last_action_at`;
- priority, confidence and compact normalized details;
- delivery-attempt/delivery state needed for anti-spam guarantees;
- indexes by `(source_id, status)` and pending decision time.

Whether these fields are needed must be decided after a minimal implementation
proves the v2 table insufficient. No migration is performed by this design.

## 11. Deterministic future test plan

1. Future, exact-due and overdue commitment events; `due_at == now` remains
   Commitment `open`.
2. Restart recovery and repeated restart: same stable event, no duplicate
   event, decision or message.
3. Completed/cancelled and multiple commitments.
4. Persistence of event handling/delivery suppression across restart.
5. Absence threshold and cautious support candidate, without diagnosis.
6. Disabled policy, levels, cooldown, quiet hours, message budget and explicit
   dismissal all suppress correctly.
7. No MemoryDocument/proposal/audit-memory mutation and no history mutation
   during detection.
8. FixedClock-only detection/decision tests: no LLM, Ollama or network.
9. LLM receives only normalized eligible context; it cannot override a
   `SUPPRESS` decision.
10. External safety event without source/freshness/relevance is rejected;
    stale or irrelevant event is suppressed.
11. Event and proactive CLI presentation are human-readable; technical IDs are
    available only through `--raw`.

## 12. Minimal safe implementation slice: MEM-12.1

Implement only the foundation necessary to prove deterministic control:

1. Refactor the existing unconnected `TemporalRuntime` into a tested local
   inspection/recovery operation using deterministic event IDs.
2. Return a bounded `TemporalEventContext` from the local Event Store.
3. Add a pure `ProactiveDecisionEngine` with injected policy and a test-only
   default of Level 0 / `SUPPRESS`.
4. Persist no memory changes and deliver no message. No scheduler, CLI command,
   ConversationService integration, LLM invocation, external source or schema
   migration is included.

This creates a safe foundation for a later separately approved delivery slice,
where Misha chooses actual policy values and permitted initiative level.

## 13. Decisions that remain Misha's

1. Default proactive on/off and level.
2. Absence threshold and whether support check-ins are enabled.
3. Quiet hours, cooldowns and maximum message budget.
4. What counts as a sufficiently important reminder or continuity topic.
5. Whether ignored/acknowledged events appear in normal history.
6. Whether and when a later local delivery runtime may run autonomously.
7. Whether to add any external information source; none is implied here.

## 14. MEM-12.1 implementation record

Implemented locally:

- stable SHA-256 `commitment_due` event IDs over Commitment ID and UTC due time;
- idempotent overdue recovery through the existing `temporal_events` table;
- bounded `TemporalEventContext` and bounded non-delivered `ProactiveCandidate`;
- immutable injected `ProactivePolicy` and a pure `ProactiveDecisionEngine`;
- conservative default policy: disabled at level 0, therefore no delivery.

Not implemented: scheduler/background daemon, CLI, ConversationService or LLM
integration, message delivery, persistent user policy settings, external event
sources, schema migration, or changes to Identity/Memory/Commitment/history.

## 15. MEM-12.2 implementation record

The local interaction state is persisted in `proactive_interactions`: one row
per stable event, with candidate/delivered/acknowledged/dismissed timestamps and
the delivered text. An LLM can formulate only a `REMIND` candidate authorised
by the deterministic engine. Explicit acknowledge/dismiss never complete a
Commitment. There is still no scheduler, daemon, external event, external
action, automatic memory mutation, fallback, or automatic model switching.

## 16. MEM-12.3 persistent policy and controlled local delivery

`ProactivePolicyStore` persists local operating configuration in
`local-data/config/proactive-policy.json`, separately from Identity, long-term
Memory, conversation history, Commitments and model profiles. Its conservative
initial state is disabled at level 0.

The human-facing CLI provides `proactive status`, `proactive settings`,
`proactive on`, `proactive off`, `proactive level <0-5>` and `proactive run`.
`proactive run` is a manually invoked local entry point, not a scheduler. It
recovers deterministic events, applies policy (level, quiet hours, cooldown
and daily limit), then may formulate an already authorised reminder through
the active local model profile and `ModelRouter`.

Interaction delivery, acknowledgement and dismissal remain the only persistent
effects; they never mutate MemoryDocument, Identity, Commitment or history.
Level 2 exposes deterministic check-in permission from an absence threshold,
but no check-in event/delivery is implemented: the current interaction schema
is deliberately keyed to Commitment events. Absence is a signal, never a
diagnosis.

## 17. MEM-12.5 storage foundation

Migration v4 adds a separate `proactive_events` event store. It persists stable
event identity, source, UTC timestamps, bounded JSON payload and the lifecycle
`detected/candidate/delivered/acknowledged/dismissed/resolved/expired`.
`ProactiveEventStore` has no LLM, policy or delivery logic. It does not change
the existing `temporal_events` foreign-key contract or turn events into Memory.

## 18. MEM-12.6 deterministic check-in detection

The global read-only `ConversationStore.latest_message()` is the anchor for an
absence period. `CheckInDetector` creates a stable CHECK_IN event only when
`absence_duration_seconds > policy.absence_threshold_seconds`. Repeated runs
and restart retain the same event identity. The detector does not decide
permission, formulate or deliver a message.

## 19. MEM-12.7 check-in lifecycle

Existing policy produces `CHECK_IN` or `SUPPRESS`; only the former moves a
detected event to candidate. Reminder priority suppresses check-in without
deleting it. User return resolves only a check-in whose `delivered_at` precedes
the new message. Delivery itself remains out of scope.

## 20. MEM-12.8 controlled local delivery

Migration v5 makes `proactive_interactions` dual-source with an XOR constraint:
REMIND references `temporal_events`; CHECK_IN references `proactive_events`.
The active local ModelProfile formulates only an authorised bounded candidate.
Manual and background modes invoke the same cycle. The daemon is a
single-instance polling executor, not a decision-maker or external channel.

## 21. MEM-12.9 daily-use UX and safety boundary

Human CLI views expose policy/daemon state, waiting interactions and a
deterministic decision trace without UUIDs. Audit payloads contain the decision,
runtime reason and execution profile; the LLM cannot authorise or explain its
own delivery. Check-in formulation remains short, warm and neutral: absence is
only a duration signal, never evidence of illness, danger or distress.

The event-origin boundary is explicit: `LOCAL_TEMPORAL_EVENT` may proceed to
the existing policy engine, while `EXTERNAL_EVENT` always returns
`SUPPRESS / external_event_not_implemented`. There is no web lookup, trusted
external source, OS autostart or external notification channel in MEM-12.9.

## 22. Stage 13 unified Daily Runtime

Stage 13 adds orchestration, not a new temporal domain. `DailyRuntime` invokes
the existing Commitment recovery, deterministic policy, interaction service
and check-in lifecycle in one order: REMIND before CHECK_IN. One cycle may
reserve only one new contact, and a delivered interaction awaiting the user
blocks another contact. The same path is used by manual execution and the local
daemon.

The bounded runtime receipt is operational evidence only. It contains no
generated message text and cannot mutate or become Identity, Memory,
Commitment, conversation history or Temporal truth.
