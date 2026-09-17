# Masha Home — Dialogue and Action Ownership

Статус: **текущий архитектурный контракт рабочего coherence checkpoint**.  
Этот документ не выдаёт новые capability, не заменяет provider-specific safety contracts и не означает, что natural-language acceptance завершена.

## 1. Главный принцип

В Masha Home понимание языка и право что-либо сделать — разные вещи.

```text
meaning != authority
model promise != receipt
conversation history != permission
```

LLM может предложить смысл реплики и bounded evidence. Application остаётся владельцем реальных объектов, разрешений, state transitions, mutation и факта выполнения.

## 2. Канонический путь запроса

Текущий рабочий путь:

```text
UserTurn
  -> strict application-owned preconditions
       confirmation / protected content / existing domain owners
  -> TurnContextEnvelope
       bounded conversation context
       current Home time
       application-owned presented/focused real objects
       verified recent action results
  -> DialogueCore
       -> meaning-first semantic proposal
            speech act: ordinary | create | update | read | unclear
       -> if action-like:
            semantic mapping against compatible application-owned specs
       -> deterministic/application validation
       -> FlowFrame / ActiveQuestion when clarification is needed
  -> ResolvedCapabilityHandoff (meaning only)
  -> domain ActionProposal
  -> policy / Human Confirmation
  -> Operation
  -> verified or explicitly unverified Receipt
  -> application ResponseProjection
```

Ни `SpeechActProposal`, ни semantic mapping, ни `InterpretationFrame`, ни `ResolvedCapabilityHandoff` не являются authorization.

## 3. Meaning-first semantic resolution

Первый semantic step отвечает только на вопрос **«что это за речевой акт?»**.

Он не должен выбирать capability ID и не получает полный capability catalog как список команд.

Допустимые speech-act kinds текущего checkpoint-а:

```text
ordinary
create
update
read
unclear
```

Если реплика является ordinary conversation, второй capability-mapping вызов не нужен.

Если распознан action request, второй bounded step получает:

- **исходную пользовательскую реплику**, а не сгенерированный paraphrase;
- bounded turn context;
- только совместимые application-owned capability specifications.

Semantic result остаётся предложением. Home проверяет candidate membership, literal evidence, slots, referents, provider ownership, grounding и доступность operation.

Model failure или malformed mapping не открывает legacy unrestricted mutation route. Action-like request должен fail-closed в контролируемый unsupported/clarification outcome.

## 4. Ownership table

| Object | Creates | Authority | Source of truth / persistence |
|---|---|---|---|
| Speech-act proposal | local semantic model role | none | transient model output |
| Semantic action mapping | local semantic model role | none | transient untrusted proposal |
| `InterpretationFrame` | Home validator | meaning only | active Dialogue state |
| `DialogueState` / `FlowFrame` | `DialogueCore` | conversation-scoped task state only | `PendingResolutionStore` |
| `ActiveQuestion` | Dialogue clarification owner | asks for unresolved meaning/state | same dialogue runtime state |
| Presented/focused real object | application read/result projection | reference truth only within its bounded context | application-owned presented registry |
| `ResolvedCapabilityHandoff` | application semantic boundary | no mutation authority | transient validated handoff |
| `ActionProposal` | domain/application owner | proposal only | domain proposal lifecycle |
| Confirmation | application confirmation boundary | user authorization decision within existing proposal | domain proposal state |
| Operation | provider/domain writer | executes only within validated contract | provider/domain operation state |
| Receipt | operation/application layer | factual execution truth | durable receipt/recovery owner |
| Response projection | application boundary | presentation only | conversation transcript/history |

## 5. Context continuity is descriptive, not authoritative

Conversation history must retain enough bounded prior user/model context to preserve topic and ordinary dialogue continuity.

Application messages and prior results may also be included as **dated descriptive history**. They do not grant new permission.

A previous sentence such as «я создала событие» cannot authorize a new action and cannot prove that an operation happened. Factual success requires application-owned result/receipt evidence.

The coherence checkpoint removed the former rule that truncated all user/model history after the latest APPLICATION message. That truncation destroyed conversational continuity and was not itself a safety boundary.

Safety is preserved by explicit ownership of proposals, confirmations, operations and receipts — not by conversational amnesia.

## 6. Application-owned reference truth

Real entity identity remains outside the model.

The model may understand phrases such as:

- «это»;
- «тот второй»;
- «перенеси его»;
- «напомни об этом».

But application state decides whether a real unambiguous object is currently referencable.

Examples of application-owned truth:

- selected/focused Calendar event;
- displayed mail/file result set;
- saved reminder identity and its actual time;
- existing Commitment ID;
- verified operation result.

A calendar event cannot silently become a saved-reminder anchor merely because the wording looks convenient. Missing or ambiguous ownership must lead to clarification/fail-closed behavior.

## 7. Provider ownership

Provider mentions are semantic evidence, not generic keywords.

If an explicit request targets Google Drive, a conflicting Yandex Disk mapping must be rejected. The application may **veto** a conflicting provider candidate; it must not invent a replacement capability solely to make the turn succeed.

Likewise, a provider name mentioned as the **topic** of mail or ordinary conversation is not automatically the destination capability.

Provider conflict resolution must therefore fail closed rather than silently executing against another provider.

## 8. Dialogue state contract

The current bounded dialogue stack has maximum depth one.

An ordinary conversation turn may preserve/suspend the active flow. A proven new supported action may supersede it according to `DialogueCore` rules. Nested mutation flows are intentionally not simulated by introducing hidden parallel state owners.

The existing runtime repository remains responsible for atomic persistence, TTL, bounded retention and corruption handling. Confirmation is not stored as semantic dialogue state.

## 9. Confirmation boundary

A plain `да` belongs to the application owner that currently holds a real confirmation request.

Semantic clarification and mutation confirmation are different states:

```text
clarification answer != confirmation
selected capability != approved operation
```

The semantic model cannot promote a clarification response into mutation authority.

## 10. Operation and receipt truth

Only the domain/provider operation owner can execute a mutation.

Only the receipt/recovery owner can establish whether the mutation is:

- verified complete;
- failed;
- conflicted;
- uncertain/unverified;
- otherwise terminal according to its provider contract.

The conversation model may phrase a verified result, but cannot create that truth itself.

## 11. Relative time

Relative-time interpretation is split into two responsibilities:

1. language layer extracts grounded evidence/field intent;
2. application-owned temporal logic performs actual arithmetic using real typed anchors.

For example, «за час до начала» may be calculated from the selected event's actual start time only after the application has proven that event reference.

The current checkpoint still has open language-quality failures where the model selects the correct reminder capability but emits date/time rather than `relative_time`. Application rejection is correct behavior; do not weaken grounding or add phrase-specific routing to hide the failure.

## 12. Compatibility routes

Some mature domain/read capabilities may still retain compatibility services around `DialogueCore` while adoption continues capability-by-capability.

Compatibility code must not become a second global dialogue-state authority.

Exit condition for a legacy interpretation route is not «new code exists», but:

- bounded semantic specification exists;
- application adapter preserves existing safety/policy/receipt rules;
- deterministic invariants pass;
- relevant language evals pass;
- live/manual acceptance covers the user journey when language quality matters.

## 13. Diagnostics

Read-only diagnostics may expose bounded internal state needed to investigate failed journeys: active flow/question, candidates, accepted/rejected semantic trace, handoff type and response projection state.

Diagnostics must not expose a mutation handle or turn into a second control plane.

## 14. Acceptance rule

Architecture can be correct while conversation quality is still poor.

Use the split:

```text
authority/state invariant -> deterministic test
semantic/language robustness -> eval
complete conversational experience -> Human Review
```

The current coherence branch is still under acceptance. Green deterministic gates do not convert this document into proof that all natural-language journeys work.
