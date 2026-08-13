# Passive Memory v0.3

## Candidate is not memory

An ordinary conversation turn may produce a `MemoryCandidate`, but a pending
candidate is not a fact about Misha and is never included in
`MemoryRetriever`.  Only Misha's typed approval can create a confirmed record.
There is no automatic-confirmation path in v0.3.

The implementation reuses `MemoryCandidate`, `CandidateType`,
`CandidateStatus`, `MemoryDocument.memory_candidates`, the SQLite candidate
collection, and the existing audit log.  `MemoryDocument` remains schema
version `0.4`; existing databases and reflection candidates require no
migration.  Passive-specific metadata is a validated
`passive_candidate_v1` envelope inside the existing `proposed_payload`.

## Evidence and provenance

Detection runs only after temporal reads, reflection intents, explicit memory
and capability routes have declined a turn and the ordinary model response has
completed.  The current persisted USER message is authoritative evidence.
The recent window is bounded to eight messages; assistant messages can be
present as context but never become evidence about Misha.

The envelope records the conversation ID, actual USER message IDs, detector
version, reason, confidence, detection/expiry timestamps, project scope,
normalized novelty signature, and any relation to existing memory.  Audit
lineage uses these content-free events:

- `candidate_detected`;
- `candidate_approved` and `memory_created_from_candidate` in the same
  repository transaction;
- `candidate_rejected`;
- `candidate_expired`.

`memory_provenance(record_id)` reconstructs the source, candidate,
conversation evidence, reason, confidence and Misha's review from the
candidate plus the durable audit lineage.  Whole transcripts and candidate
text are not copied into audit payloads.

## Detection policy

v0.3 supports only:

- durable Misha-owned `Fact`/preference statements;
- explicit settled `Decision` statements;
- strict Misha-owned `Commitment` statements with a deterministically
  resolvable due date;
- `RelationshipMemory` when the USER explicitly calls a shared experience
  meaningful.

The deterministic eligibility gate rejects greetings, acknowledgements,
questions, quotes and other-person claims, general knowledge, transient
states/desires, uncertainty, hypotheticals, explicit capability commands and
obvious secrets or sensitive personal data.  Passwords, tokens, financial
credentials, identity-document numbers, diagnoses, intimate data and
political/religious identity never become passive candidates.

The v0.3 production extractor is a strict deterministic local fast path.  It
does not invoke Qwen or any remote provider and therefore does not add a second
model wait to ordinary conversation.  Ambiguous language safely produces no
candidate.  The typed request/result boundary leaves room for a later bounded
LOCAL_ONLY structured extractor, but such an extractor is deliberately not
wired until post-response scheduling can be introduced without unsafe
background SQLite writes.

Confidence thresholds are:

- Fact: `0.82`;
- Decision: `0.82`;
- Commitment: `0.90`;
- RelationshipMemory: `0.90`.

Extracted proposals still need to meet their threshold after deterministic
safety and novelty checks.  Clear deterministic matches currently carry
confidence between `0.88` and `0.97`.

## Novelty and conflicts

Normalized meaning tokens are compared with active confirmed records and live
pending candidates.  Same-meaning confirmed memory produces no candidate;
repeated pending meaning reuses the existing pending candidate.  Rejected or
expired candidates are not recreated from the same old evidence message.

A likely update is stored as pending with `relation=possible_update` and the
related record ID.  Ordinary approval refuses it.  The typed reviewer must
explicitly request supersession, after which reciprocal Fact/Decision
supersession is validated atomically.  No conflict silently overwrites memory.

## Lifecycle and source semantics

Pending candidates expire after seven days.  Approval atomically adds the
prepared record, marks the candidate `APPROVED`, stores `result_memory_id`, and
writes lineage events.  The record ID is prepared at detection time, making
approval retry idempotent.  Rejection and expiration create no confirmed
record.

Approved passive records preserve `source=conversation`; clicking Approve does
not falsify their origin as `explicit_user_input`.  The existing explicit
memory proposal/confirmation flow remains unchanged and continues to require
`explicit_user_input`.

Commitment dates are resolved by the same application-owned `TemporalEngine`
and Home timezone used by conversation and reminders.

## Deferred

v0.3 does not add the Home review surface, automatic memory, passive Episodes,
MashaReflection or AffectiveRecord, embeddings, whole-history summaries,
remote extraction, scenes, connectors, agents, or the v0.3.1/v0.3.2 work.
