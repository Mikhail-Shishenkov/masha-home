# MEM-12.4 — Check-in Event Contract Design

## Scope and current boundary

This is a design-only document. It changes no production code, SQLite schema,
policy defaults, model profile, Identity, Memory, Commitment or conversation
history contract.

A check-in is an optional short human contact after an absence. It is not a
reminder, diagnosis, loyalty check, emotional inference or demand for a reply.
`absence_duration > threshold` means only that the local conversation history
has been inactive for that period.

The existing `temporal_events` / `proactive_interactions` path is keyed to a
Commitment. A CHECK_IN therefore needs its own event source before it can be
delivered; it must not use a fake Commitment or a Memory record.

## 1. Minimal event model

Proposed normalized event, held locally:

```text
event_type: check_in
source_type: conversation_absence
source_anchor_id: latest_history_message_id
absence_started_at: UTC timestamp of that message
detected_at: UTC timestamp
threshold_seconds: policy value used for detection
expires_at: UTC timestamp, if an approved expiry rule is selected
```

`latest_history_message_id` is the last stored message in the most recently
active conversation after Masha's previous response. It is a stable anchor for
one absence period. The runtime needs a read-only history helper that returns
that global latest message; it must not write history to inspect it.

The bounded context sent to a formulation model contains only: event type,
absence duration, current local time, whether a continuation marker is present,
and the already-authorised decision. It excludes raw history, audit details,
proposal IDs and the entire Memory document.

## 2. Detection rules

Initial source: **absence only**.

```text
last history message exists
AND now_utc - absence_started_at > policy.absence_threshold
AND no later stored user message exists
=> CHECK_IN event may be detected
```

The strict `>` boundary matches the requested absence semantics. No history
means no check-in event. Detection is deterministic and has no LLM dependency.

Conversation continuation is deliberately not inferred from arbitrary prose.
For a later source, the minimum safe criterion is a separately stored,
user-visible `continuation_pending` marker created only by an explicit action;
it is not part of this slice.

An open Commitment with a deadline remains a `REMIND` event. It may coexist
with a check-in, but it never becomes one.

## 3. Stable identity and deduplication

Use a deterministic identity, not a generated UUID:

```text
checkin_event_id = "chk1_" + SHA-256(
  "check-in:v1|conversation_absence|" + source_anchor_id
)
```

The same absence period therefore produces the same ID through restart and
repeated `proactive run`. A later user message changes the anchor; after that
new interaction, a new absence exceeding the threshold may produce a new
check-in event. Changing a policy threshold does not create a duplicate for an
already anchored absence period.

## 4. Lifecycle and conversation reset

Proposed lifecycle:

```text
detected → candidate → delivered → acknowledged | dismissed | resolved | expired
```

`candidate` exists only after deterministic detection and policy permission;
the LLM never creates it. `acknowledged` and `dismissed` retain their current
meaning and are terminal. `resolved` means that a delivered check-in was
followed by a normal new user message; no extra acknowledgement is demanded.
`expired` means that a pending candidate became invalid before delivery,
normally because the user returned.

Recommended rule: a new user message automatically resolves a delivered
check-in, or expires a pending candidate. This is an interaction-state change
only, not a Memory/Commitment/Identity mutation and not an assertion about why
the user returned. It should not be recorded in `audit_events`; its local row
and timestamp are sufficient diagnostics.

Alternative: leave a delivered item in `delivered` until the user explicitly
acknowledges it. This is simpler, but is more mechanical and contradicts the
preference not to require confirmation of ordinary human contact. The
recommended automatic `resolved` rule preserves explicit acknowledge/dismiss
without pretending that a normal reply is an acknowledgement.

## 5. Suppression and anti-spam

Before formulation, the existing deterministic policy must permit check-in:

- `enabled=true`, `proactive_level >= 2`, and `allow_checkins=true`;
- absence is strictly greater than `absence_threshold`;
- outside `quiet_hours`;
- total delivered proactive interactions are below `daily_message_limit`;
- the latest local delivery is outside `cooldown`;
- the stable event has no terminal interaction state.

Dismiss suppresses the same stable absence event permanently. It does not
disable future independent absence periods. Acknowledge and resolved likewise
prevent repeat delivery of that event. The delivery limit and cooldown are
shared with Commitment reminders, so the system never sends both simply
because two candidates exist.

Expiry needs a product decision. Two safe choices are:

1. **Return-only expiry (recommended initially):** retry a model-unavailable
   candidate only while the same absence continues; a user return invalidates
   it. This adds no new setting.
2. **Fixed/setting-based TTL:** expire after a bounded interval even without a
   return. This is more conservative for a delayed model, but introduces a
   user-visible policy decision and should not be silently chosen.

## 6. Formulation boundary

The required chain is:

```text
Conversation history + Temporal Engine
→ deterministic CHECK_IN detection
→ persistent ProactivePolicy
→ ProactiveDecisionEngine
→ authorised bounded candidate
→ active local ModelProfile / ModelRouter
→ local delivery state
```

The LLM may vary tone — short, warm, occasionally light — or return no message
when the candidate explicitly permits that. It must not infer distress, invent
absence reasons, claim it worried throughout the night, pressure for a reply,
change policy, create Memory, modify Commitment, or initiate an external
action. The deterministic decision is fixed before model formulation.

Acceptable intent: “Давно тебя не было. Просто заглянула — как ты там?”
Unacceptable intent: “Ты пропал, я знаю, что с тобой что-то случилось” or
“Ответь мне немедленно”.

## 7. Persistence and integration proposal

The existing schema cannot represent this cleanly: `temporal_events.source_id`
has a foreign key to `memory_records`, while a conversation-anchor ID is not a
memory record. The next implementation must choose one of these explicit
schema designs rather than bypass the foreign key:

1. Add a separate `proactive_events` table with stable event identity and a
   source discriminator; `proactive_interactions` would reference it.
2. Generalize the Event Store so event sources can be Commitment or
   conversation-history anchors, then preserve the current Commitment event
   uniqueness and interaction behaviour.

Option 1 is recommended: it avoids altering the already working
Commitment/temporal-event contract and keeps check-ins outside long-term
Memory. It is a future migration proposal, not a migration in MEM-12.4.

`TemporalRuntime` owns detection and recovery. A small read-only history
adapter supplies the anchor. `ProactiveDecisionEngine` owns permission.
`ProactiveInteractionService` owns formulation/delivery only after permission.
`ConversationService` owns normal user turns and reports a user return to the
future check-in interaction boundary. `IdentityKernel`, `MemoryManagementService`,
`ModelProfileStore` and `ModelRouter` retain their current responsibilities.

## 8. Examples

| Situation | Deterministic result |
| --- | --- |
| User has been absent longer than threshold | One stable CHECK_IN may be detected; policy can suppress it. |
| User left after an unfinished ordinary chat | Still absence only; no continuation claim is inferred. |
| Delivered check-in, then a normal user message | Interaction becomes `resolved`; no explicit acknowledgement required. |
| User dismisses it | Same event never redelivers; a later independent absence may qualify. |
| User talks again, then is absent again | New anchor, new eligible absence period after threshold. |
| Overdue Commitment also exists | It remains a REMIND candidate; shared limits/cooldown choose at most what policy permits. |

## 9. Decisions reserved for Misha

1. Should check-in delivery use return-only expiry or a finite TTL? If TTL,
   what duration is comfortable?
2. Is automatic `resolved` on a normal user reply acceptable, or should a
   delivered check-in remain visible until explicit acknowledgement?
3. At Level 2, should the default wording be purely neutral, warm, or allow
   occasional gentle humour?
4. Should an explicit “не тормоши меня” command suppress only the current
   event, check-ins until the next user return, or disable check-ins in policy?
5. When a reminder and check-in are both eligible, should the reminder always
   take priority, or should the user choose a different presentation rule?

## Intentionally not implemented

No production code, migrations, scheduler, daemon, background loop, external
delivery, external events, model/profile changes, automatic emotional state
detection, long-term Memory mutation or Identity mutation are included.
