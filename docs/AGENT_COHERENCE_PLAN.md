# Masha Home — coherent agent recovery plan

Status: active. Owner: Masha / engineering assistant.
This plan supersedes the incremental language-polish sequence; its completed
checkpoints remain in LIVING_HOME_LANGUAGE_CORE_PLAN.md for provenance.

## Baseline and authority

- Start: HEAD 40af080 plus the existing uncommitted working tree. Preserve it.
- Last deterministic gate: 696 passed, 2 Windows symlink skips; 23 Node tests.
  This did NOT establish real conversational acceptance: the subsequent user
  transcript demonstrates failures. Do not confuse contract tests with quality.
- User now permits commits/push/merge. Use reviewed, bounded stages; never merge
  an unverified redesign or include credentials/runtime/private transcripts.
- Actual local profile is FAST (masha-fast:4b); never assume PRIMARY.
- No live mailbox/calendar mutation during engineering probes. Use synthetic
  fixtures and real local-model calls where they measure language quality.

## Ordered stages and exit gates

1. [IN PROGRESS] Evidence / Staff AI engineer
   Trace selected failures end to end, not all historical tasks:
   - hour-of-day: "в час дня" must be 13:00, not 01:00;
   - existing event -> pronoun update -> verified result;
   - event -> reminder one hour earlier -> update SAME reminder;
   - recipe topic -> Web follow-up -> "о чём мы говорим?";
   - compare ordinary/evening final model payloads on identical synthetic history.
   Record message count/roles, context sizes, model proposal, rejection,
   pending state, handoff and receipt truth. Never retain private live payloads.
   Distinguish absent context, conflicting instructions, wrong application state
   and model limitation. Read primary engineering sources; no framework migration
   merely because a tutorial uses one.
2. [PENDING] Cleanup / Staff maintainer + test architect
   Before new architecture, inventory ONLY involved paths: owner / callers /
   invariant / replacement. Remove proven duplicates and superseded tests.
   Keep unique safety/grounding/receipt tests. Unreplaced live routes are removed
   alongside their replacement, not beforehand. No numerical deletion target.
3. [PENDING] Unified turn context / AI architect
   Reuse one state owner for topic, recent messages, selected real entities,
   active question, Saratov time and recent action results. Supply consistent
   projections to understanding AND response generation. Load relevant memory
   and tool evidence on demand, with provenance/time and bounded context.
4. [PENDING] Coherent action loop / application engineer
   Meaning -> state -> adapter -> proposal -> confirmation -> operation -> receipt.
   Model chooses meaning, not execution truth. Create/update/read are distinct;
   never substitute creation for an unavailable update. Existing objects stay
   bound to real application IDs; relative reminders use actual event time.
   Read-only lookup may follow an information need under existing policy;
   external text cannot authorize writes. No sentence-regex vocabulary expansion.
5. [PENDING] Continuity / memory engineer
   Separate short-term task state from dated long-term memory. Reuse existing
   memory layers. Cross-chat relevant recall is not indiscriminate transcript
   mixing; special evening stays separately scoped. No automatic conversion of
   unverified model assertions into memory.
6. [PENDING] Release / test architect
   A small multi-turn FAST evaluation with unseen paraphrases, followed by
   affected tests and ONE full gate. Compare another available local model only
   if actual payload evidence suggests capacity limits. Record remaining failures.
   Human acceptance is required before declaring conversational quality solved.

## Research decisions (2026-09-15)

- Curate context, concise instructions, minimally overlapping tools; avoid
  encoding every language edge case in the prompt. Preserve essential evidence
  during compaction. Source:
  https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Thread-scoped short-term state should be refreshed after each step, including
  tool results; it is distinct from cross-session memory. Source:
  https://docs.langchain.com/oss/python/langchain/short-term-memory
- These principles inform the investigation; they do not establish that this
  repository needs LangGraph, new embeddings, multiple agents or a new database.

## Resume protocol

Read this plan and the newest checkpoint only, inspect git status/diff, continue
the next incomplete gate. Do not repeat full forensic/research or discard work.
After each stage record files, tests, evidence and the exact next action here.

## Checkpoint 1 — confirmed context loss

- Read-only synthetic ConversationService.send probe (no Ollama/external calls):
  user discusses trout -> assistant discusses trout -> Web follow-up ->
  application clarification -> user asks current topic.
- Stored history: 6 messages including the final response. Final ModelRequest:
  exactly ONE message, the current topic question. The preceding topic is absent.
- Cause: ConversationService._model_history slices after the last APPLICATION
  message, discarding ALL prior user/model messages, not merely unsafe action
  claims. This is shared by ordinary/evening; the latter may encounter fewer
  application boundaries. That explanation is a hypothesis, not yet measured.
- The function's rationale is avoiding unreceipted action claims. Preserve that
  invariant via explicit result provenance, not blanket conversational amnesia.
- Next concrete step: inspect tests that require application readouts to stay
  outside prose history; map their unique safety invariant. Remove this lossy
  history rule only together with bounded history/result projection and a
  regression proving topic continuity AND no mutation-authority replay.
- Other observed failures (spoken clock, existing-reminder update, relative
  event reminder) remain unproven at code/trace level. Do not mark them fixed.
- Changes in this checkpoint: documentation only. Existing local code untouched.
  No new full regression, commit, push or merge.

## Checkpoint 2 — remove destructive history truncation

- Cleanup inventory: _model_history alone erased all preceding dialogue at
  each application message. No discovered test owned that exact truncation;
  confirmation/write tests own the legitimate no-unreceipted-action invariant.
  Removed the truncation and its stale rationale, not those safety tests.
- Existing 16-message window is preserved, including application messages as
  dated home_application_history JSON. This is descriptive history, not a new
  operation/receipt. No new state store, router, model role or transcript copy.
- Replaced the contradictory memory-only instruction in the existing behavioral
  contract: current conversation messages supply topic continuity; long-term
  records supply remembered facts. Old promises/history grant no new action.
- Regression reproduces the lost topic in ordinary AND evening; injected false
  Calendar success is still blocked; no pending proposal or memory mutation.
- Real local FAST masha-fast:4b probe: final request now contains 5 messages
  instead of 1; response correctly identifies salting red fish/trout. System
  context measured 8396 characters. Topic recovery works; the extra generic
  chatter in the answer is not evidence of full agent quality acceptance.
- Next: inspect spoken-time normalization and create/update discrimination
  with result/target continuity. No broad prompt tuning or model replacement.
  Validation: 121 affected tests passed; compileall and git diff --check passed.
  Previous uncommitted changes preserved; no commit/push or full-suite rerun.

## Checkpoint 3 — shared entity context for understanding and response

- General-layer inspection: TurnConversationHint dropped persisted message
  origin, merging model prose and application history into assistant text.
  Preserve origin and timestamp in semantic context; neither is new authority.
- The response compiler received no structured presented-entity context while
  semantic understanding did. Extracted the existing allow-list into
  TurnContextEnvelopeBuilder.project_presented_entities; both now use it.
  Response samples the existing registry after this turn's execution, not the
  pre-action semantic snapshot. No second registry, persistence or routing path.
- Keep history, memory and external body evidence in their existing separate
  fields: do not duplicate the entire semantic envelope into the answer prompt.
  Titles/focus help references but do not imply the body was read or a mutation
  succeeded. Provider IDs remain outside the projection.
- Two invariant tests: origin survives without inventing result/entity truth;
  semantic/answer entity projections agree, empty selection clears old focus,
  no IDs/memory mutation/proposal, fabricated success still blocked.
- Validation: 184 affected deterministic tests passed (semantic, turn context,
  compiler, human references, confirmation, calendar drafts, external context,
  release dialogue). No live provider calls, full-suite rerun or commit/push.
- Remaining architectural gap: confirmed operation results/targets are not yet
  one coherent source for subsequent meaning. Existing application action cache
  is transient and mostly a continuity-resolve response helper; it cannot be
  relabelled verified execution truth. Inspect receipt-backed target projection
  next. Existing-reminder update capability availability and relative-time
  grounding remain unverified. Do not compensate with phrase routing rules.

## Checkpoint 4 — results join the existing entity context

- Found: Calendar create/update owners returned human result text but never
  published the verified event to PresentedReadSetRegistry. The registry already
  projects actual connector entities; extend that owner, not a new state store.
- Create/update now publish a single focused CalendarEventEvidence only from a
  verified receipt with confirmed_at/verified_at. Provider ID stays in Home;
  semantic/response projections contain the label and time only. Both button
  and conversational confirmation use the same owner.resolve boundary.
- Calendar read replaces the context, including empty results. Failed reads,
  uncertain/conflicting updates/deletes and verified deletion clear Calendar
  focus; never clear another connector's newer set. No extra network calls.
- General referent contract: referenced_text may carry content across families
  (letter -> reminder); referenced_entity requires one focused object from the
  same catalog family (event -> update/delete). Calendar subject metadata opts
  into the latter. Reuse the same validator for fresh/follow-up turns, leaving
  actual provider lookup and confirmation to existing adapters. No new regex.
- Invariant tests cover create/update before/after confirmation, uncertain
  results, private IDs, another conversation, repeat confirmation, empty read,
  and same-family versus foreign/unknown referents. 196 affected tests passed;
  focused receipt tests additionally cover invalidating a prior event after an
  uncertain update. compileall and git diff --check passed. No full-suite rerun.
- Limitations: this is human-reference context, not binding a semantic proposal
  directly to a receipt ID. Adapter lookup still revalidates against the provider.
  The registry is session-scoped; restart hydration, relative reminder offsets,
  and existing-reminder update remain open. No live E2E claim or full gate yet.

## Checkpoint 5 — remove competing operation invention and evidence templates

- Deterministic reproduction: inject a model timed-commitment proposal for
  "Измени напоминание завтра в 11". Hybrid's slot-overlap/update heuristic
  invented google_calendar.event.update, labelled it SEMANTIC, and resolved it.
  Removed this alternative-operation generator. Existing rejection-only update
  guard remains defense-in-depth, not language understanding or routing authority.
- Six old test cases explicitly required this substitution. Changed those
  assertions to no invented candidate (not a dropped safety case); a new narrow
  invariant covers Home not manufacturing update authority plus honest diagnostic
  attribution for a model-declared unsupported request.
- Catalog had timed commitments as MANAGE although its adapter only creates.
  Label/kind now describe create accurately; semantic spec already said create.
  No existing-reminder UPDATE adapter exists in this path. Do not imply otherwise.
- Local FAST masha-fast:4b measured on synthetic natural requests, no connector
  calls. Polite reminder request initially copied "не дай мне забыть" from
  prompt templates although user said "Не дашь мне забыть...". Removed duplicated
  rule/template blocks and examples/lexical controls from both model prompt
  vocabulary projections. Descriptions stay; Home's grounding checks unchanged.
- Post-cleanup: same polite request selects the right candidate and correct
  subject/date/time, but still omits operation-selection evidence. Home correctly
  keeps ambiguity; NOT a successful live gate. Existing-reminder update is still
  misclassified by FAST as create or schema_error. A diagnostic harness initially
  passed a missing temporal engine; rerun with TemporalEngine verified the
  remaining ambiguity. One extra wording tweak did not improve it and was removed.
- Stop prompt tuning. Next: simplify duplicated action/selection evidence wire
  while preserving genuine destination ambiguity; explicitly model existing
  reminder modification using the existing confirmed-memory lifecycle. Test
  unseen polite requests and action-kind discrimination before calling it solved.
  No new phrase routing, external mutations or full-suite rerun.
  Validation: 197 affected deterministic tests passed; compileall and
  git diff --check passed. Changes remain local and uncommitted.

## Checkpoint 6 — one literal request, not duplicate selection proof

- Fresh meaning may reuse its already grounded action quote for selection.
  This applies only to one model-proposed operation and a unique match of its
  existing catalog selection contract within the group. No candidate invention,
  slot/history evidence, new lexical list or phrase-routing branch. A generic
  quote keeps ambiguity. Explicit invented selection evidence is rejected, never
  rescued by falling back to the action quote. Trace: shared_action_evidence.
- Explicit operation_id with null selection quote also reuses the action quote;
  prompt/schema explain this instead of demanding the same quotation twice.
  Follow-up already carries one selection quote; its validation is unchanged.
- Real local masha-fast:4b, synthetic read-only resolver probes:
  "Не дашь мне забыть завтра в 9 позвонить маме?" -> home.timed_commitments,
  subject/date/09:00 resolved. Previously it unnecessarily asked Calendar/Home.
  "Давай запишем занятие завтра в 11" -> Calendar/Home ambiguity preserved,
  despite the model proposing Calendar alone. No external transport/mutation.
- Invariant cases: shared explicit quote accepted; generic quote insufficient;
  absent separate selection can reuse valid quote; invented selection rejected.
  Existing mail->reminder->time->proposal->confirmation integration now uses the
  shared quote path. 201 affected tests passed. No full suite repeated.
- This is not full natural-language acceptance. Existing reminder update,
  relative event offsets and broader FAST action-kind quality remain next.
  Keep action adapters/confirmation intact; add the missing reminder update
  contract using existing memory mutation rather than pretending CREATE updates.

## Checkpoint 7 — saved reminder update uses the existing memory lifecycle

- Found an existing owner: MemoryIntentHandler.propose_due_change_by_id already
  proposes an EDIT of the same commitment, and confirmation applies/verifies it
  through MemoryManagementService. No new reminder store or scheduler needed.
- Registered home.timed_commitments.update in catalog/spec/adoption/adapter.
  Descriptive update semantics; required subject/time, optional new date and
  previous time. Omitted date preserves the saved local due day. Candidate
  resolution reuses existing record ranking over open, visible, project-scoped
  explicit reminders. Unknown/ambiguous targets never produce a create.
- New adapter enters the existing due-edit owner. Old-time constraint, past
  deadlines, existing pending confirmation and no-op changes fail without write.
  IDs, text, status and delivery mode stay unchanged; wakeup callback is reused.
- Application preview previously labelled every non-create commitment proposal
  as completion. Open-record edits now use the already-existing reschedule/clear
  due UI contract with Saratov local time. No renderer redesign/new action type.
- Real local FAST recognizes the unseen indirect request "Можешь сделать так,
  чтобы существующее напоминание про маму сработало завтра в 14 вместо 13?"
  as home.timed_commitments.update, with subject/date/14:00. It omitted old_time:
  this is a remaining extraction-quality limitation, not a full E2E pass.
- Tests: proposal leaves memory unchanged; confirmation edits same ID; reject
  leaves memory unchanged; repeated yes does not duplicate; descriptive target
  matches real label; multiple matches/wrong old time do not write; omitted date
  preserved; preview says reschedule not complete. 215 affected tests passed,
  then 62 affected reminder/reference tests passed after the preview correction.
- Remaining: relative event offsets, durable focus/restart and live multi-turn
  checks. Ambiguous target currently asks for a more specific description; no
  new selection state machine was added. Full suite reserved for stage gate.

## Checkpoint 8 — relative reminder arithmetic; FAST acceptance still blocked

- Presented entities now carry an optional typed, timezone-aware starts_at from
  the real event. Display text and mail received_at are not time anchors.
- Reminder-create vocabulary describes optional relative_time evidence. Home
  validates the quote and one focused event matching the resolved subject, then
  computes date/time in the Home timezone. Fresh and pending follow-up use the
  same arithmetic. No model-generated absolute timestamp or provider ID used.
- Missing/ambiguous anchor, invented quote, conflicting absolute time, ambiguous
  duration, past deadline and subminute timestamps do not produce a deadline.
  Strict duration parsing is opt-in here; existing embedded-duration behavior
  remains unchanged. Calendar/confirmation/provider execution is untouched.
- 193 affected deterministic tests passed (semantic, context, references,
  duration/time, reminder confirmation, Calendar drafts, dialogue contracts).
- Real local masha-fast:4b probe with a synthetic focused event at 14:00:
  "Можешь напомнить мне об этом за час до начала?" incorrectly proposed
  home.timed_commitments.update with time 01:00; Home rejected unresolved subject
  and returned clarification. No connector calls or mutation. NOT a live pass.
- NEXT: general action-kind + clock-versus-duration evidence discrimination.
  Inspect the actual semantic wire before changing prompts; do not compensate
  with a phrase-specific route. Relative arithmetic is verified, but natural
  language selection/extraction still blocks this end-to-end scenario.

## Checkpoint 9 — one clock normalizer and catalog-bounded generation

- Confirmed actual FAST wire: update with time evidence "за час до начала".
  Semantic time normalization previously searched arbitrary numbers/words inside
  evidence; clarification had a separate numeric-only clock parser. Replaced
  both with clock_evidence: whole clock expressions, period-aware (час дня=13:00),
  rejecting durations and evidence cropped out of a duration or day period.
- Kept prior work intact. Current checkout was main at 40af080 with the same
  local diff; created new/agent-coherence-continuation without reset/staging.
- Generic semantic instruction distinguishes the object being changed from a
  new related object. No operation-specific routing or execution permission.
- Live probe then invented home.timed_commitments.create. Fresh JSON generation
  did not constrain operation IDs to vocabulary; pending generation already did.
  Added vocabulary-derived enums to fresh candidate/nearby/selection fields.
  Failing schema regression observed before implementation; now green.
- 195 affected tests green. Added an invariant for cropped duration evidence;
  watched "Продли на два часа" / quote "два" incorrectly become 02:00, then
  fixed it. No full suite repeated; no external provider mutation.
- Full-catalog FAST probe remains NOT accepted: indirect relative reminder
  selects update; another selects create but labels relative evidence as time.
  Both now clarify instead of inventing a deadline. Explicit reminder update
  still resolves to update with date/13:00.
- Diagnostic-only comparison: same indirect phrase, same FAST, context and
  validation, vocabulary reduced to both reminder create/update -> correct
  create + relative_time -> real event 14:00 minus one hour = 13:00. This is
  NOT production acceptance and does not justify lexical capability prefiltering.
- NEXT: investigate compact full-catalog presentation / generic staged selection
  rather than further phrase/prompt patches. The controlled comparison suggests
  catalog interference; one sample does not prove model size is the sole cause.
  Keep all capabilities understandable, one dialogue owner, confirmation intact.

## Checkpoint 10 — compact-catalog experiment, no production change

- Runtime inspection: 25 operations, catalog 14,693 characters, base semantic
  prompt 19,705 characters before turn context. Loaded masha-fast:4b reports
  context_length=32768; this does not establish prompt truncation as the cause.
- Throwaway in-process experiment removed repeated required_slots/display_name
  and null/empty metadata, retained every operation and slot meaning. Same
  relative reminder probes still failed: first chose update, second chose
  create but put the interval in time. Explicit reminder update stayed correct.
  No experimental serializer was written into production or retained as code.
- Simple JSON compression does not resolve the observed semantic confusion.
  Proposed next design (awaiting agreement): first choose descriptive candidates
  from the COMPLETE compact operation catalog, then extract grounded fields only
  against the chosen specifications. Preserve ambiguity, original request and
  common turn context; both passes propose, Home validates. Same DialogueCore,
  adapters and confirmation; bounded combined time/calls, no lexical shortlist.
- Tradeoff: at most one additional local model call, so measure total latency
  and cross-capability unseen cases before adopting. Model replacement remains
  an alternative, not a conclusion established by these few probes.

## Approved implementation — staged meaning inside the existing resolver

User approved 2026-09-16. Execute inline, preserve current working tree.
No separate dialogue store, capability router, provider permissions or writes.

- [x] Tests first in tests/test_semantic_resolver.py: complete-catalog selection,
  selected-specification detail extraction, immutable candidate/action evidence,
  ordinary one call, malformed details retain meaning, shared 15-second budget.
- [x] backend/conversation/semantic_resolver.py: compact selection prompt/schema;
  second request exposes only grounded slots/referents of selected operations.
  Return the existing combined SemanticInterpretationProposal for Home validation.
  At most two local requests, no repair loop; failed detail extraction becomes
  missing fields, never an unrestricted ordinary-model retry. Read-only phase
  diagnostics store stage/failure, not another state owner.
- [x] Adapt existing test doubles to the two real response shapes, not production
  fallback behavior. Run semantic/dialogue/reference/time affected tests.
- [x] Run synthetic real FAST cross-capability and relative-reminder probes;
  record exact results/latency. No real connector execution or full suite yet.
- [ ] compileall + diff check, update checkpoint; preserve local changes.

## Checkpoint 11 — two-stage candidate implemented, live gate NOT passed

- Compact whole-catalog selection -> detailed extraction for selected candidates.
  One existing resolver returns the same SemanticInterpretationProposal. The
  detail wire contains only slots/referents, cannot rewrite candidates/evidence.
  Ordinary/unsupported/no-detail operations take one call; otherwise max two
  under one 15-second budget. Removed the old schema-repair retry loop.
- Malformed/late/duplicate-slot detail response retains selected meaning with
  missing fields. Diagnostic semantic_detail_failure is available through the
  existing DialogueCore diagnostic; not a second state or user-visible metadata.
- Real Ollama ignored nested allOf shape refinements: produced unsupported_action
  with supported candidates. Selection grammar now uses complete direct anyOf
  branches (as pending grammar already does); invalid kind combinations stopped.
- 211 affected tests passed, including stage budget, immutable action choice,
  shared context, detail failures, grounding, dialogue and reminder confirmation.
  Test fixtures project complete meaning onto the actual two wire shapes. No
  production compatibility branch or provider/confirmation behavior changed.
- Real FAST, full catalog, after grammar correction: both relative-reminder
  requests wrongly selected home.proactive_reminders (read); reminder update,
  Drive recent and ordinary AI plan were incorrectly treated as unsupported.
  Mail-new request selected yandex_mail.read; its later transport was NOT run.
  Local resolver latency ~2.5–4.6 seconds. Thus this is NOT an accepted release.
- Diagnostic-only reasoning=True on same masha-fast:4b: relative-reminder and
  ordinary probes each timed out at ~15 seconds. No production profile change.
- STOP prompt patching: compare a stronger installed local semantic profile on
  the same fixed cases before claiming this architecture/model pair sufficient.
  Keep chat FAST unless separately approved. Do not merge/push this unaccepted
  candidate or infer success from deterministic tests alone.

## Checkpoint 12 — model comparison and proposed meaning-first correction

- Diagnostic override only: qwen3.5:9b, same two-stage resolver, no configuration
  changes. First two relative-reminder probes timed out at 15s during the run
  that loaded 9B; cause of each timeout not proven. Reminder update resolved
  correctly (~7.6s), Drive recent correctly (~6.2s), Mail read selected (~5.6s,
  no view extracted). Ordinary personal AI plan wrongly selected memory remember
  (~6.1s). No provider operation, proposal confirmation or memory write executed.
- A temporary generic instruction distinguishing personal plans from requests
  did not fix ordinary/create distinction. A reduced selection wire also failed.
  Neither experiment was retained in production. Warm relative reminder still
  selected reminder update, so cold-loading alone does not explain quality.
- Control task: ask only whether the SAME utterance is a personal statement or
  a request, and whether the request creates/updates/reads. Both installed FAST
  and 9B correctly returned statement for the AI plan, create reminder for the
  relative-reminder request. No tools/catalog or full turn context in this control.
  This changes multiple prompt factors; it suggests task presentation matters,
  NOT proof that catalog size alone is the cause or that 4B can pass all cases.
- Approved design correction: first understand the
  speech act and requested change without operation names; then map that meaning
  to compatible catalog descriptions and extract details. Still two local calls,
  same context/DialogueCore/confirmation. Second stage cannot turn statement into
  action or change create into update. No lexical routing or new state owner.
- Do not switch production model or promote the current unaccepted candidate.
  Only this diagnostic checkpoint changed in this turn; no full suite rerun.

## Checkpoint 13 — catalog-free speech-act preflight (not integrated)

- User approved meaning-first work. Keep one resolver and at most two calls;
  do not restart the larger coherence refactor or alter confirmation adapters.
- Actual configured semantic profile masha-fast:4b, think=False, temperature=0.
  Six synthetic local requests with the same small prior-event context: personal
  AI plan; two relative reminder creates; existing reminder update; Drive recent;
  Mail new. No connector transport or real user data was used.
- Catalog-free ordinary/create/update/read/unclear classification: 6/6 kinds
  correct, 0.69–1.09s. This is a small diagnostic, NOT an end-to-end gate.
  Three action quotes were null; one free meaning paraphrase incorrectly changed
  the reminder target into the related calendar event. Therefore a generated
  paraphrase must never replace the original utterance or resolve a real target.
- Direct union schema and removal of paraphrase: still 6/6 kinds correct,
  0.58–0.80s, but two relative-reminder quotes were not literal. Do not weaken
  grounding or keep tuning phrases to disguise this failure.
- Minimal next implementation: first stage proposes ONLY the speech-act kind
  (no catalog IDs, slots, synthesized target or redundant action quote).
  It can restrict the second-stage catalog by its existing operation_kind,
  never grant authority. Ordinary terminates without capability mapping.
  Second stage uses ORIGINAL utterance + bounded context + compatible specs;
  existing Home action/selection/slot grounding remains mandatory there.
  Unknown/mixed kind keeps ambiguity; no arbitrary operation choice.
- Existing catalog uses update for delete/forget/complete as well as edits.
  Reuse that descriptive contract; do not introduce a conflicting delete kind.
- Before switching production resolve(): failing invariant tests for ordinary
  no-second-call, no create/update crossover, shared deadline, malformed mapping
  fail-closed, original source preservation; then adapt existing fixture helper
  and remove superseded selection/details helpers (not two runtime alternatives).
  Prove mapping failures cannot fall through to unrestricted action claims.
- Current production candidate unchanged in this checkpoint, still NOT accepted.
  No full suite, commit, push, model configuration change or external mutation.

## Checkpoint 14 — meaning-first implemented; pause handoff

Current branch new/agent-coherence-continuation, HEAD 40af080. All accumulated
local changes preserved. User expects a pause until the 22nd: resume here,
not from the older operation-first design. No commit/push of this candidate.

Implemented in semantic_resolver.py, resolution_coordinator.py and the existing
test_semantic_resolver.py (plus this plan):
- First request returns only SpeechActProposal.act: ordinary/create/update/read/
  unclear. It sees the same bounded human context, not the capability catalog,
  capability availability or operation IDs in presented/application metadata.
- Ordinary takes one call and cannot receive a second legacy action chance.
  Protected confirmations/document material retain their existing earlier owner.
- Second request uses original utterance, compatible registry specifications and
  the same bounded context. At most two local calls within the shared 15s budget.
- SemanticActionMapping returns candidates, literal slots/referents and existing
  action/selection evidence. Removed duplicate kind/nearby/ambiguity generation:
  Home derives supported vs unsupported from candidate presence and computes
  ambiguity as before. No generated paraphrase substitutes for the source turn.
  Old selection/details prompts/schema/helpers and unused parser removed.
- Mapping failures after recognized action fail closed to the existing controlled
  unsupported flow, not unrestricted conversation or a legacy mutation route.
  Partial slot validation, grounding, normalizers, adapters and confirmations
  are unchanged. Diagnostic semantic_speech_act replaces semantic_detail_failure.
- Live probe exposed Google request mapped to Yandex. Home now reuses existing
  explicit_file_provider_id as a candidate VETO for conflicting file providers,
  not an invented replacement candidate or new command grammar. Both directions
  covered by deterministic tests. No provider transport executed in probes.

Measured evidence (configured FAST masha-fast:4b, think=False, temperature=0):
- All 6 speech acts correct. Ordinary personal AI plan stays ordinary (~0.52s).
- "Можешь напомнить мне об этом за час до начала?" resolves Home reminder,
  subject "Разговор с мамой", 2026-08-29 13:00 for focused event at 14:00 Saratov
  (~4.38s). This is a resolver probe, NOT live scheduling/delivery acceptance.
- "Не дай мне забыть об этом, напомни за полчаса до события." selects reminder
  correctly but emits date/time instead of relative_time; Home rejects fields
  and asks for date/time. STILL FAILS complete natural-language acceptance.
- Saved reminder update correctly remains update; relative new time unsupported
  without a saved reminder time anchor. Clarification, never duplicate create.
- Drive recent incorrectly proposed yandex_disk.read for explicit Google Drive.
  The new ownership test/validator blocks this; correct Google fulfillment still
  needs improvement. Mail-new selected yandex_mail.read and extracted view.
- Diagnostic qwen3.5:9b override, unchanged production config: ordinary correct;
  relative cases still lost fields/one gained Calendar ambiguity; reminder update
  lacked fields; Google Drive selected correctly; Mail selected with no view.
  ~3.8–4.8s warm, first ordinary ~8.6s including loading. NOT a proven model fix.
- Root-cause experiment: old wire's redundant kind choice kept saying unsupported
  despite correct candidate in a flat-schema control. Direct union enforced that
  wrong label and erased fields. Removed the duplicate choice instead of accepting
  contradictory wire or adding phrase-specific routing. This improved the first
  relative-reminder case but does not prove all language quality solved.

Verification so far: initial new invariant tests failed before implementation;
81 semantic tests pass, previous affected gate 211 passed before two added
provider-ownership cases. compileall and diff check pass. One final deterministic
full suite was started for the pause checkpoint; result recorded below.

Final checkpoint gate: `pytest -q -m "not live_smoke"` -> **736 passed,
2 skipped in 51.28s** (Windows symlink availability only). No full rerun needed
until the next meaningful stage gate. `compileall` and `git diff --check` clean.
The global dirty diff includes earlier work; this checkpoint changed only the
semantic resolver, its DialogueCore diagnostic, existing semantic tests and this
plan. No commit, push, profile edit or external provider mutation.

Resume priorities (do NOT restart broad architecture work):
1. Inspect remaining real mapping failures by proposed fields and selection
   evidence. No extra phrase router, no silent invalid-evidence acceptance.
   Compare schema/registry field presentation on a small fixed/unseen set.
2. Add reminder focus only using a real saved reminder's identity/time when
   needed for "на час позже"; a calendar anchor must never stand in for it.
3. Prove end-to-end preview/confirmation with synthetic adapters after meaning
   quality passes; then manual live acceptance. No real writes during diagnostics.
4. Do not promote/merge/push as a finished release on deterministic tests alone.
   Full natural-language acceptance remains open; no production model change.

## Checkpoint 15 — Google Drive human name, narrow measured fix

- Scoped to the remaining file-provider confusion, not another resolver redesign.
  Before: configured FAST mapped "Посмотри, пожалуйста, что у меня последнее
  на Гугл Диске" to Yandex; the existing veto correctly blocked it. The same
  wording with English Google Drive selected Google correctly.
- Hypothesis/control: semantic registry described Google Drive only by its
  English name, while Yandex's description used Russian. Adding "(Гугл Диск)"
  ONLY to google_drive.read purpose changed the failed Russian request to the
  correct Google candidate. No routing rule, alias regex, model/config or schema
  change was needed. This is measured for this local model/set, not a guarantee
  of universal language quality.
- Rejected experiment: passing normalized provider_scope into mapping helped
  file requests but caused "Найди письмо про Google Drive" to become ambiguous
  between Mail and Drive. Relabeling it as a mere mention did not solve that.
  Removed the experimental prompt argument/hint and its test; do NOT restore
  it. Mentioned provider is not necessarily the requested destination.
- Final production delta in this checkpoint: one descriptive registry line in
  interpretation_v2.py, plus this plan. Earlier resolver/ownership work preserved.
  No added test framework, command variants or permanent test functions.
- Real FAST, same synthetic focused-calendar context: 7/7 correct routing:
  Russian/English Google recent; Yandex recent; polite Google recent;
  Mail about Google Drive in both languages; ordinary comparison of disks.
  Read probes ~3.2–3.6s, ordinary ~0.47s. No connector/provider read or mutation
  executed. This proves ROUTING only: English Mail-topic probe omitted its topic
  slot, so it does not prove end-to-end mail search quality.
- 122 focused/affected tests passed; compileall and diff check clean. Full suite
  intentionally not repeated (previous checkpoint: 736 passed, 2 skipped).
- Next bounded item remains relative-time field extraction ("за полчаса"):
  don't change time arithmetic or loosen grounding to hide missing model fields.
  All work remains local; no commit/push.

## Checkpoint publication — explicitly approved by user

User approved saving and pushing the accumulated working branch as a checkpoint,
NOT merging to main and NOT declaring natural-language acceptance complete.
The earlier no-push notes describe development gates, not a ban on this approved
backup checkpoint. Preserve the known limitations recorded in checkpoints 14–15.
Packaging verification: all 23 Node test entries pass; diff check clean. Latest
Python evidence remains 736 passed / 2 skipped for the prior full gate and 122
affected tests after the one-line registry description correction. No redundant
full rerun. Production model configuration and private runtime data are excluded.

Overall: unified context and action boundaries implemented; replacement semantic
path in evaluation; relative-time field quality and multi-turn live acceptance
still incomplete. This branch is a recoverable work checkpoint, not a release.
