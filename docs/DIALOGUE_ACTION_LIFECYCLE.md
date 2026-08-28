# Masha Home — Dialogue and Action Ownership

Статус: текущий архитектурный контракт Slice 2E.  Этот документ не даёт новых
capability и не заменяет provider-specific safety contracts.

## Канонический путь запроса

```text
UserTurn
  -> strict application ownership (existing confirmation, protected content)
  -> DialogueCore
       -> untrusted semantic meaning proposal
       -> Home validation against Capability Catalog
       -> one persisted FlowFrame and ActiveQuestion
  -> ResolvedCapabilityHandoff (meaning only)
  -> domain ActionProposal
  -> policy / Human Confirmation
  -> durable Operation
  -> verified or truthful unverified Receipt
  -> application ResponseProjection
```

`InterpretationFrame` and `ResolvedCapabilityHandoff` are never authorization.
No model sentence is a receipt.  A plain `да` answers the currently owned
application confirmation only; it cannot promote a DialogueCore clarification
to a mutation.

## Ownership table

| Object | Creates | May modify | Source of truth / persistence | Terminal state |
|---|---|---|---|---|
| Semantic meaning proposal | local `semantic_resolver` role | nobody; immutable and untrusted | transient model response | accepted or rejected by Home validation |
| `InterpretationFrame` | Home semantic/deterministic validator | pure follow-up transition creates a replacement | stored only inside active Dialogue state | resolved handoff, cancellation, expiry or supersession |
| `DialogueState` / `FlowFrame` | `DialogueCore` | `DialogueCore` only, through validated transitions | `PendingResolutionStore`, atomic versioned runtime JSON | resolved, cancelled, expired or superseded; immutable afterward |
| `ActiveQuestion` | clarification renderer under `DialogueCore` direction | `DialogueCore` only | same Dialogue runtime JSON | replaced when its dimension resolves or flow terminates |
| `ActionProposal` | domain application service/adapter | its existing proposal lifecycle only | domain proposal store | confirmed, rejected/cancelled or failed |
| Confirmation | application confirmation boundary | user decision through application API | domain proposal state | confirmed or rejected; never stored in Dialogue state |
| Operation | provider/domain writer after confirmation | provider-specific recovery/idempotency service | provider-specific operation/receipt journal | provider-specific verified, unverified, conflict or failed state |
| Receipt | operation/application layer | only its recovery state machine | durable receipt store | provider-specific terminal truth |
| Response projection | application boundary | nobody after emission | conversation transcript is presentation history, not domain truth | emitted |
| `PresentedReadSet` | application-owned read result projection | connector/application registry | bounded runtime reference registry | replaced by newer presented set or discarded |
| Memory proposal | Memory application boundary | existing Memory proposal lifecycle | Memory proposal store | confirmed, cancelled or expired |
| Proactive interaction | proactive application runtime | proactive acknowledge/dismiss lifecycle | proactive interaction store | acknowledged, dismissed or policy terminal state |

## Dialogue state contract

The current bounded stack has a maximum depth of one.  An ordinary
conversation turn suspends/preserves that frame.  A proven new supported action
explicitly supersedes it.  Nested mutation flows are intentionally deferred:
Home must not corrupt either flow merely to simulate a deeper stack.

The runtime document is schema `2.0`.  It migrates schema `1.0` flat
clarification fields into first-class `active_question` on read.  The existing
atomic temp-file, fsync, replace, TTL, bounded retention and corruption behavior
remain the persistence boundary.  Confirmation is deliberately absent.

## Production interpretation ownership

All non-confirmation user text reaches `DialogueCore` before broad legacy
capability routing.  The following narrow exceptions remain before it:

- existing confirmation responses, because authorization is application-owned;
- explicit Google Docs Create structural syntax, because material after `:` is
  protected user content and cannot be reparsed as another command;
- document receipts supplied by the application.

Calendar Create and timed commitments are adopted DialogueCore operations.
Their old raw Calendar Create gate runs only in compatibility compositions
where no DialogueCore is installed.  It is not a second production owner.

Calendar Update, connector reads, Web observation, Memory management and
retrospective Recall retain their mature services after a DialogueCore
`PASS_THROUGH`.  They are compatibility routes, not competing owners for the
two adopted operations.  Exit condition for each is a tested catalog
specification plus resolved application adapter preserving its existing policy,
confirmation, receipt and recovery boundary.

## Component treatment matrix

| Component | Treatment in Slice 2E | Exit condition / invariant |
|---|---|---|
| Router V1 capability services | compatibility implementation/read routes | remove raw interpretation only after that operation is adopted and regression-covered |
| Router V2 / `DialogueCore` | evolve into the one production dialogue authority | no second persisted dialogue state machine |
| `InterpretationFrame` | keep as validated meaning | contains no authority or execution result |
| Semantic Resolver | keep as untrusted language-to-command proposal | full descriptive catalog; only adopted allowlist may hand off |
| `PendingResolutionStore` | evolve into Dialogue state repository schema 2.0 | later storage replacement must preserve repository semantics |
| `FollowUpResolutionEngine` | keep as pure transition component inside core | never persists, routes globally, confirms or executes |
| old `NaturalLanguageResolutionCoordinator` name | compatibility import alias only | delete after downstream imports migrate; it owns no separate object/state |
| `ConversationService` | thin orchestration boundary for strict owners, core, handoff and ordinary model | must not run Calendar Create V1 when DialogueCore exists |
| clarification renderer | keep wording-only | asks the current genuinely unresolved dimension |
| truthfulness guard | defense in depth | never used as the primary success UX |
| resolved capability adapters | keep application validation handoff | proposal/confirmation remains domain-owned |

## Read-only diagnostics

`MashaApplication.dialogue_diagnostics(conversation_id)` returns a bounded
immutable snapshot: active flow/question, candidates, validated and missing
slots, last accepted/rejected semantic proposal trace, DialogueCore outcome,
application handoff type and response projection state.  It exposes no store
mutation method, proposal UUID, provider payload, Memory content, credential or
conversation transcript, and is not rendered in the normal Home UI.

