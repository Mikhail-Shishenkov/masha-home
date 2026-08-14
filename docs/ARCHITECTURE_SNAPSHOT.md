# Architecture Snapshot — Masha Home

Дата фиксации: 2026-08-10. Это снимок фактического состояния рабочего дерева,
а не целевая схема. Он не означает, что незакоммиченные изменения уже образуют
релиз или что любая описанная возможность подключена к живому диалогу.

> **Historical architecture snapshot:** этот документ сохраняет состояние и
> контекст ранних этапов. Текущий roadmap и архитектурный канон находятся в
> [MASHA_HOME_CANON.md](MASHA_HOME_CANON.md).

> **Superseded runtime note (ID-02, 2026-08-11):** the historical audit below
> describes the pre-consolidation state. The section `CURRENT — ID-02 IDENTITY
> RUNTIME CONSOLIDATION` is authoritative for the active identity runtime.

> **Current memory/recall note (v0.3.1):** этот файл остаётся историческим
> снимком. Канонический текущий контракт human lifecycle, search, recall,
> restore, model-context privacy и Home timezone находится в
> [HUMAN_INFORMATION_MODEL_V0.3.1.md](HUMAN_INFORMATION_MODEL_V0.3.1.md).

## Рабочее дерево

Репозиторий **нечистый**: большая часть текущей реализации памяти, Identity
Kernel, SQLite-репозитория, LLM-контрактов, benchmark-а и документации ещё не
закоммичена. Есть также изменённые старые файлы и удаленный
`tests/validate_memory.py`. Этот snapshot добавлен поверх этого состояния и не
заменяет ревизию Git.

## IMPLEMENTED

### Основа проекта

- Python-пакет `backend`, Pydantic v2, pytest и конфигурация в `pyproject.toml`.
- Канонический JSON-файл памяти `memory/test_memory.json` версии схемы `0.4` и
  сгенерированная JSON Schema `memory/memory_schema.json`.
- Базовый JSON `MemoryStore`, специализированные `DecisionStore`,
  `CommitmentStore`, `EpisodeStore`, retrieval и bounded `WorkingMemory`.
- `ContextBuilder` собирает старый прикладной `MashaContext`: persona, project,
  facts, decisions, commitments, episodes, working memory и текущее локальное
  время. Это самостоятельная ветка кода; она пока не вызывает Identity Kernel
  и не обращается к LLM Router.

### Память и SQLite

- Строгая Pydantic-модель `MemoryDocument` v0.4 с межсущностной валидацией,
  уникальными ID, жизненными циклами и проверкой отсутствия циклов замещения.
- Реализована миграция `v03_to_v04`.
- `MemorySqliteRepository` умеет атомарно хранить и восстанавливать целый
  валидированный документ, применяет миграции, WAL, foreign keys, audit events,
  import/export JSON и backup/restore только в отдельный файл.
- SQLite **не включён как активный источник памяти приложения**: JSON остаётся
  текущим рабочим форматом, а SQLite — готовым, отдельно протестированным
  репозиторием.

### Identity и persona

- `identity/masha.identity.json` — утвержденный, версионированный manifest
  `masha-0.1`; `IdentityStore` только читает его и валидирует.
- `IdentityKernel` строит неизменяемый `IdentityContext`; модель не может
  записывать или менять manifest.
- Есть `identity/masha.regression.json` с тремя сценариями регрессии характера.
- Два утверждённых визуальных референса лежат в `identity/visual_assets/` и
  проверяются по SHA-256 через manifest.
- Отдельно существует legacy-представление persona: `persona/masha.json`,
  `PersonaStore` и `backend/persona/*`. Оно используется `ContextBuilder`, но
  не объединено с Identity Kernel.

### LLM-контракты и оценка моделей

- Есть нейтральные контракты `ModelRequest`, `ModelResponse`, `ModelCapabilities`,
  `PrivacyScope` и интерфейс `ModelProvider`.
- `ModelRouter` предпочитает доступные локальные providers; внешние допустимы
  только с `EXTERNAL_ALLOWED` и никогда не получают `private_context`.
- Единственный реализованный provider — `FakeProvider` для тестов. Реального
  `OllamaProvider`, подключённого к Router, нет.
- Есть независимый HTTP benchmark для локального Ollama и одинарный tone-case.
- Есть отдельный фиксированный набор `masha-home-v1` из 20 коротких тестов.
  Runner сохраняет сырые ответы в `local-data/model-benchmarks/`, исключённую
  из Git; он использует только синтетический контекст, не production memory.

## DECIDED

- Проект local-first и рассчитан на одного пользователя; память и личный
  контекст по умолчанию не покидают компьютер.
- Личность Маши живёт вне LLM: Identity Context + память + контекст + router +
  модель. Выбор модели не должен менять её утверждённое ядро.
- Утвержденные константы личности: честность, тепло, собственное мнение,
  верность без роли судьи, живость, внимательность к значению контекста и право
  оставаться собой. Визуальная преемственность также утверждена.
- Границы поддержки, «дружеских пинков», инициативы, quiet hours и проактивных
  обращений **не определены и не включены**.
- JSON остаётся активным и переносимым форматом; переход на SQLite не включать
  без отдельного решения пользователя.
- Для обычного диалога Ollama используется с `think: false`; thinking — только
  отдельный режим будущей сложности.
- Рабочий выбор моделей после локального benchmark-а: PRIMARY `qwen3.5:9b`;
  быстрый кандидат/резерв `qwen3.5:4b`, но не для строгих JSON-задач; vision
  кандидат `gemma4:e4b`; отдельная reasoning-модель пока не назначена.

## PLANNED

- Реальный Conversation Engine, история сообщений и первый офлайн-диалог.
- Реальный адаптер Ollama для `ModelProvider` и передача скомпилированного
  Identity Context в разговорную модель.
- Управляемое извлечение memory candidates, подтверждение, дедупликация и
  provenance из реального разговора.
- Temporal Engine, scheduler, дедлайны, восстановление после перезапуска.
- Локальный UI/API, голос, динамический визуальный образ, tools/agent gateway,
  n8n и любые внешние API.
- Правила эмоциональной поддержки и инициативы — только после отдельного
  совместного решения с пользователем.

## TEST STATUS

Полный запуск ` .\\.venv\\Scripts\\python.exe -m pytest ` в момент snapshot-а:
**59 passed in 0.64s**.

- Memory: schemas/models, stores, lifecycle/forget-restore, retriever,
  migration, SQLite repository.
- Identity: manifest, regression suite и hashes visual assets.
- LLM: router/privacy/capabilities, benchmark models и fixed suite.
- Legacy persona/context: store и сборка `MashaContext`.

Известна флакiness `tests/test_sqlite_repository.py::test_import_read_and_export_preserve_validated_document`: audit events сортируются по `occurred_at, id`; при одинаковой timestamp UUID может поменять ожидаемый порядок `import_json`/`export_json`. В предыдущем запуске он падал, в snapshot-запуске прошёл. Исправление не выполнялось.

## MEMORY ARCHITECTURE

```text
Project
 ├─ Fact / Decision / Commitment
 ├─ Episode ──produced/updated/superseded──> other memory IDs
 ├─ MemoryCandidate ──approved──> typed memory record
 ├─ MashaReflection / RelationshipMemory / AffectiveRecord
 └─ ContinuityState ──> FollowUp + Episode + AffectiveRecord links

MemoryDocument v0.4 validates all IDs, ownership and graph links
 ├─ JSON MemoryStore (active in ContextBuilder)
 └─ MemorySqliteRepository (implemented separately; not wired in)
```

`MemoryRetriever` accepts a typed query, project, record bound, context lens and
character budget. It filters visible active/open/current v0.4 records by the
selected lens, ranks meaningful user-facing fields with dominant deterministic
lexical relevance, and may return no records. `WorkingMemory` receives only the
bounded selection; ordinary conversation uses a six-record default.

## CONTEXT / IDENTITY / PERSONA

`IdentityKernel -> IdentityContext` is the protected personality boundary used
by LLM request contracts. It is loaded from the approved manifest.

`ContextBuilder -> MashaContext` is currently a separate, older aggregation
path based on `PersonaStore` and JSON stores. It adds real local time and
working memory but is not a conversation compiler and is not connected to
`ModelRouter`. Therefore no current code path yet combines identity, memory,
time and a real model into a single reply.

## LLM ARCHITECTURE

```text
ModelRequest(identity_context, private_context, capabilities, privacy)
                         |
                     ModelRouter
                 /                   \
        local providers first     external only if explicitly allowed
                 |
       currently: FakeProvider in production code tests

Separate: Ollama benchmark HTTP client -> local Ollama -> raw local results
```

The router’s privacy policy is implemented and tested. The physical Ollama
runtime and installed models are evaluated by benchmark scripts, but are not
registered in the router and cannot yet serve an application conversation.

## MODEL DECISION

Benchmark results are documented in `docs/MODEL_EVALUATION.md` and raw results
are local-only. `qwen3.5:9b` is PRIMARY because it gave the most stable tone,
honesty, disagreement and JSON behaviour in the single fixed Masha Home suite;
on this PC it ran at about 54 tok/s and used GPU fully at the tested 4096-token
context. It is a working choice, not an irreversible identity decision.

- `qwen3.5:4b`: fastest otherwise viable text candidate (~79 tok/s), but failed
  strict JSON in the fixed suite; reserve only for non-contract text.
- `gemma4:e4b`: viable separate vision candidate; good speed and JSON, but more
  likely to use therapeutic/corporate tone and made a contextual memory error.
- `ministral-3:8b`: can reason about memory and disagree, but is overly
  theatrical, violates strict JSON and sometimes invents details.
- `lfm2.5`: very fast, but emitted `<think>` despite `think: false`; unsuitable
  for ordinary companion dialogue now.
- `qwen3:8b`: technically viable baseline, but automatic agreement and the
  phrase equating itself with the user reject it as a Masha candidate.

No automatic multi-model routing is implemented or justified yet.

### CURRENT — MEM-12.1 TEMPORAL FOUNDATION (2026-08-11)

The existing local SQLite `temporal_events` table now stores deterministic,
idempotently recovered overdue Commitment events. `TemporalRuntime` uses the
MEM-11 clock and never changes a Commitment or MemoryDocument. A bounded
`TemporalEventContext` and pure `ProactiveDecisionEngine` exist; policy is
disabled by default. No scheduler, proactive delivery, LLM decision, CLI,
external event source, schema migration, or persistent policy settings exist.

### CURRENT — MEM-12.2 PROACTIVE INTERACTION (2026-08-11)

`ProactiveInteractionService` forms only deterministic-policy-authorised
reminders through ModelRouter and the active local profile. SQLite stores
candidate/delivery/acknowledgement/dismissal state separately from memory.
There is no scheduler, external delivery, external event source, automatic
mutation, fallback or model switching.

### CURRENT — LLM-03 LOCAL MODEL PROFILES (2026-08-11)

`local-data/config/models.json` is a local operating-configuration file, not
Identity, Memory, conversation history, or temporal state. It persists the
manually selected profile across a restart. The initial profiles are
`primary` (`qwen3.5:9b`), `fast` (`qwen3.5:4b`), and disabled
`experimental` / `vision-candidate` configuration entries.

`ConversationService` passes the active profile's model ID and `think=false`
through provider-neutral `ModelRequest`. `ModelRouter` still selects only the
provider; it neither selects a model nor falls back. `OllamaProvider` executes
exactly the selected target. `model list`, `model current`, and `model use
<profile>` are local CLI commands. A switch checks the enabled profile, local
Ollama, and the selected model before persistence; failure preserves the
previous profile. There is no automatic switching or fallback.

## KNOWN ISSUES

- SQLite audit-event test can be nondeterministic when timestamps match.
- `ContextBuilder` and Identity Kernel are parallel, unintegrated paths.
- No real Ollama provider exists; benchmark success is not application runtime
  integration.
- Planned and implemented documentation are partially out of sync: the plan
  still names LLM-02 as next work, but model runtime/benchmark work already
  exists.
- Ollama automatic update temporarily made the local API unavailable during
  evaluation; runtime/version pinning and restart handling are not implemented.
- Model benchmark currently uses a synthetic system context. It is not a proof
  of long-lived conversation, real memory retrieval, tool execution or
  thinking-on quality.

## TECHNICAL DEBT

- Commit and classify the large accumulated dirty working tree before treating
  it as a stable release baseline.
- Reconcile or retire the legacy persona/context path deliberately; do not let
  it diverge silently from Identity Kernel.
- Define a deterministic audit ordering (or distinct sequence) for SQLite.
- Add an actual local provider adapter, context compiler, configuration and
  controlled error/restart path only in the next approved layer.
- Extend benchmark assessment for thinking-on, actual tool calls, vision input,
  RAM measurement and long-context behaviour before promoting model roles.
- Keep benchmark raw output local and review retention/disk policy later.

## OPEN QUESTIONS

- What exact conversation history format and retention policy should exist?
- How will Identity Context, selected memory and time be budgeted into 4096
  active runtime context without losing continuity?
- Should JSON remain active through the first chat, or should a controlled
  SQLite activation happen first?
- What quality threshold and fallback behaviour are required before using the
  fast Qwen profile?
- What are the user-approved boundaries for support, correction, initiative and
  reminders? No answer is assumed here.
- Whether visual analysis needs a dedicated Gemma path, and what consent/data
  rules govern sending local images to it.

## NEXT ARCHITECTURAL LAYER

**CHAT-01 — minimal offline conversation vertical slice.** It should define a
small conversation service that receives a user message, loads the approved
Identity Context, compiles bounded local context, calls a real local provider,
persists message history and returns a response after restart/offline failure.
It must not silently create memories, activate proactive behaviour, define
support boundaries, or switch the active memory store. This section is a
description only; no implementation was started for this snapshot.

## CURRENT STATE

### Natural Language Capability Router

Ordinary Home conversation now reaches the existing Memory, Commitment,
Continuity and Temporal contracts through a fixed allowlist router. It applies
local normalization and deterministic composable aliases first; an optional
selected local model may classify only ambiguous capability-like utterances
above a confidence threshold. The classifier receives the current utterance
only and cannot read storage, reconstruct records from conversation history or
perform a mutation.

Queries and reference resolution operate on current backend records. Every
write still produces the existing proposal and requires human confirmation.
Relative minute reminders are parsed by TemporalEngine into Commitment
`due_at`; after confirmation the existing TemporalRuntime and proactive policy
are the delivery path. No scheduler, UI capability or storage schema was added.

Shared Continuity read projections exclude migrated developer backlog such as
memory-schema/Python-model implementation tasks without deleting stored rows.

Production-smoke hardening keeps generic `что с X` in ordinary conversation
unless `X` resolves to a real open Commitment. Explicit continuity markers
(`нить`, `тема`, `не потеряй`, `вернёмся`) take deterministic priority over
semantic task classification. Russian record references use bounded
morphology/fuzzy scoring and request clarification when top candidates remain
ambiguous.

RelationshipMemory participates in the same proposal/confirmation-based
forget operation as other managed records: confirmation changes visibility to
hidden and records audit history; it never physically deletes the record.
Natural shared-history queries read visible RelationshipMemory and open
Continuity threads only through SharedContinuityService.

An open production Home has a two-second read-only proactive projection
heartbeat. In background policy mode it invokes the existing DailyRuntime via
the application boundary, then projects newly delivered stable event IDs into
the existing proactive surface. No renderer storage access, new surface,
delivery channel or schema was added; repeated observations do not redeliver
the same interaction.

Validated building blocks for memory, identity, router policy, SQLite and local
model evaluation exist. There is no end-to-end Masha conversation yet.

## DO NOT CHANGE

Do not treat a model as the identity; do not activate SQLite, external APIs,
memory extraction, proactivity, emotional-support rules or agent actions
without a dedicated approved task.

## NEXT STEP

Agree the precise scope and acceptance tests for CHAT-01, then implement only
that vertical slice.

## UPDATE — CHAT-01, CHAT-02, AND LOCAL RUNNABLE SLICE

This update supersedes the earlier statements in this snapshot that CHAT-01
and the local Ollama adapter were only planned. The implemented path is:

`terminal CLI -> ConversationService -> IdentityKernel + MemoryRetriever +
WorkingMemory -> ConversationContextCompiler -> ModelRouter -> OllamaProvider
-> active local ModelProfile -> JSON conversation history`.

The command `python -m backend.conversation.cli` starts the local terminal
conversation. It opens the most recently created conversation by default, or a
specific one passed with `--conversation-id`. The CLI is deliberately a thin
entry point; it does not bypass the service or router.

Conversation history is stored locally at
`local-data/conversations/history.json`. It is a temporary, portable JSON
transport for chat continuity, **not** the Memory Store and not a source of
new Fact, Decision, Commitment, or Episode records. The active long-term
memory source remains `memory/test_memory.json`; SQLite remains implemented
but inactive.

CHAT-02 supplies the provider-neutral bounded context compiler and behavioral
regression cases. It does not validate or revise model responses. Known model
behavioral failures therefore remain reported evidence rather than automatic
post-processing.

## UPDATE — MEM-09.1 EXPLICIT MEMORY WRITES

The active JSON `MemoryStore` now exposes the same minimal document boundary
as the prepared SQLite repository: `read_document()` and
`replace_document(validated_document)`. `ConfirmedMemoryService` accepts this
boundary and can add one already-valid Fact, Decision, Commitment, or Episode
only through `ExplicitMemoryConfirmation` by Misha with
`explicit_user_input` provenance. It does not inspect conversation history,
call an LLM, infer a record, or change the active storage implementation.

## UPDATE — MEM-09.2 EXPLICIT MEMORY THROUGH CONVERSATION

`ConversationService` now has an optional deterministic memory-intent handler.
Only an explicit Russian "запомни" request enters this path. It creates a
locally persisted `MemoryProposal` with an ID in
`local-data/memory-proposals.json`, outside both production memory and
conversation history. A proposal is not retrievable memory. A bare
confirmation is accepted only when exactly one proposal is pending in that
conversation; otherwise its proposal ID is required. Rejection cancels the
proposal. Successful confirmation is the sole path that calls
`ConfirmedMemoryService` and changes the active JSON MemoryStore.

Normal conversation messages still use the model router and do not mutate
memory. SQLite remains inactive.

## UPDATE — SQLITE ACTIVE LONG-TERM MEMORY

SQLite is now the only active production source of truth for long-term memory:
`local-data/memory/masha.sqlite3`. The CLI creates `MemorySqliteRepository`,
so `MemoryRetriever` reads its compatibility `data` view and
`ConfirmedMemoryService` writes through the same repository. JSON at
`memory/test_memory.json` is no longer read by the active CLI path; it is a
validated import/export and backup format.

`python -m backend.memory.sqlite_activation` performs the explicit, safe
activation from JSON. It first creates a JSON backup, imports only into an
empty database, verifies the result, and is idempotent when the database
already equals the source. It refuses to overwrite a divergent populated
database. Existing SQLite audit events record `import_json` and every
`confirmed_memory` mutation with who/what/when/operation metadata.

Conversation history and pending memory proposals remain separate local JSON
layers and are not part of the SQLite long-term memory database.

## CURRENT — ID-02 IDENTITY RUNTIME CONSOLIDATION

The only production identity path is `CLI -> ConversationService ->
IdentityKernel -> IdentityContext -> ConversationContextCompiler ->
ModelRequest -> ModelRouter -> OllamaProvider`. The only canonical source is
`identity/masha.identity.json`.

Legacy `PersonaStore`, `MashaPersona`, `persona/masha.json`, and
`ContextBuilder` were removed after repository search established that they
had no production callers. The active CLI does not import them.

At CLI assembly, `IdentityKernel.validate_memory_identity()` compares the
approved manifest version with active SQLite memory. Mismatch is a controlled
startup error and never mutates either source. The local-only
`backend.identity.run_identity_regression` runs approved scenarios through the
production-style compiler/router using fixture memory, stores raw output under
`local-data/identity-regressions/`, and never rewrites responses.

## HISTORICAL — MEM-10 MANAGED LONG-TERM MEMORY

`MemoryManagementService` is a local inspection and mutation boundary over the
same active `MemorySqliteRepository`. It lists/gets/searches records with
identity version and available audit metadata, supports project filtering and
reports deterministic Fact conflicts without resolving them. All mutations are
pending JSON proposals first; only an explicit confirmation applies one SQLite
transaction and audit event. Archive and forget both use existing
`visibility=hidden`, preserving the record and excluding it from normal
retrieval. Fact/Decision supersession retains the old record, marks it
superseded, and stores reciprocal `supersedes_id` on the new record.

`MemoryRetriever` emitted deterministic reasons and scores. Since v0.3.1 those
internal details remain inspectable application trace, while the compiler sends
only allow-listed humanized context without storage IDs. Chat history remains
separate and no ordinary turn creates or mutates long-term memory.

## HISTORICAL — MEM-11 TEMPORAL ENGINE

UTC is canonical internal time. The active runtime uses the configured Home
timezone provider (`Europe/Saratov` is the repository default), independent
from OS timezone settings. Temporal
context is compiled before the model request, so LLM never determines time,
durations, deadlines or overdue status. `due_at` is stored in UTC; overdue is
computed only (`due_at == now` remains open) and completed never becomes overdue.
Commitment creation and completion are explicit proposal/confirmation mutations;
ordinary conversational statements do not mutate them.

## CURRENT — MEM-12.3 CONTROLLED PROACTIVITY

Proactive policy is persisted as local operating configuration in
`local-data/config/proactive-policy.json`, separate from Identity, Memory,
history, Commitments and model profiles. A manual `proactive run` is the only
delivery entry point: deterministic recovery and policy authorise a candidate
before the active local profile can formulate it through `ModelRouter`. There
is no scheduler, daemon, external channel, fallback or autonomous mutation.

## CURRENT — MEM-12.5 PROACTIVE EVENT STORE

`proactive_events` is a separate SQLite runtime/event table, not long-term
Memory. It stores deterministic CHECK_IN and Commitment-reminder event identity
and lifecycle independently from their sources. No runtime detection, scheduler
or check-in delivery is connected in this storage-only slice.

## CURRENT — MEM-12.6 CHECK-IN DETECTION

`ConversationStore.latest_message()` is a read-only global history anchor; it
does not rely on the last created conversation. `CheckInDetector` uses that
anchor, deterministic TemporalEngine absence duration and the policy threshold
to create one stable CHECK_IN event in `ProactiveEventStore`. It does not make
a policy decision, deliver a message, call an LLM or modify source subsystems.

## CURRENT — MEM-12.7 CHECK-IN LIFECYCLE

`CheckInLifecycleRuntime` deterministically turns an authorised detected event
into `candidate`, or returns `SUPPRESS` with a reason. A later user message
resolves only check-ins delivered before that message; reminders remain intact.

## CURRENT — MEM-12.8 CONTROLLED PROACTIVE RUNTIME

Migration v5 preserves REMIND interactions through `temporal_event_id` and
adds CHECK_IN interactions through mutually exclusive `proactive_event_id`.
An authorised bounded candidate is formulated by the active local profile.
Manual cycles and an opt-in local daemon use the same deterministic pipeline;
the daemon has no decision authority.

## CURRENT — MEM-12.9 PROACTIVE UX AND SAFETY BOUNDARIES

The CLI exposes human-readable `proactive status`, `settings`, `pending` and
`history`; internal event IDs remain available only in `--raw` output.
Deterministic runtime reasons are stored in the existing audit log and cannot
be produced or changed by the LLM. `proactive off` blocks delivery. The local
daemon detects a live duplicate process, recovers stale locks, records cycle
errors and continues with later cycles. Only `LOCAL_TEMPORAL_EVENT` is within
the runtime trust boundary; `EXTERNAL_EVENT` is explicitly suppressed as not
implemented. No external source or delivery channel exists.

## CURRENT — STAGE 13 DAILY RUNTIME

`backend.runtime.daily_runtime.DailyRuntime` is the single manual/background
orchestration path over the existing temporal and proactive subsystems. It
processes REMIND before CHECK_IN, permits at most one new contact per heartbeat
and suppresses new contact while a delivered interaction awaits the user.
Deterministic bounded receipts are stored outside Memory and conversation
history. `RuntimeHealthService` performs read-only Identity, SQLite, history,
model, policy, backup and daemon checks. `masha.ps1` is the Windows-local human
entry point; it does not install autostart or an external channel.

Current regression: `169 passed`.

## CURRENT — STAGE 14 SHARED CONTINUITY

`RelationshipMemory` now represents explicitly confirmed shared meaning with
provenance. `ContinuityState` exposes bounded open threads that survive restart
and can be resolved only through an explicit proposal/confirmation mutation.
Both use the existing SQLite document repository and audit log. Existing
`MemoryRetriever` and `ConversationContextCompiler` preserve their distinct
semantics in provider-neutral context; they do not become Facts, Episodes or
Commitments. Human CLI output hides internal IDs. Obvious legacy mojibake is
quarantined from normal retrieval without rewriting production data.

## CURRENT — STAGE 15 MASHA PERSPECTIVE & HONEST HELP

`ReflectionService` and `ReflectionIntentHandler` connect the already existing
`MashaReflection` and reflection `MemoryCandidate` contracts to explicit local
conversation flows. A reflection carries bounded conversation/memory evidence,
scope, confidence and audit provenance. Self-reflections above the deterministic
confidence gate can become Masha's subjective perspective; shared reflections
remain pending until Misha adopts or rejects them. Reconsideration appends a
new linked immutable record. No SQLite migration was required.

`MemoryRetriever` can retrieve adopted reflections, but `ConversationService`
excludes them from general context and exposes a bounded reflection-only lens
only for explicit perspective questions. This prevents accumulated
interpretations from silently colouring every answer.

An adopted reflection may contain one `conversation`-capability Help Offer.
Only explicit acceptance calls the active local ModelProfile through the
existing ModelRouter; rejection and delivered state use existing audit events.
No tools, mutations, background reflection, automatic affective inference,
external provider, fallback or proactive authority is introduced.

Current regression after Stage 15: `183 passed`.

## CURRENT — STAGE 16.1 SKILL CONTRACT & REGISTRY

`backend.skills` provides strict Skill Manifest v1 validation, local package
discovery, whole-package SHA-256 pinning and persistent registration state at
`local-data/config/skills.json`. This is operating configuration, not Identity,
Memory, conversation history, proactive policy or model configuration.

The registry does not import or execute an entrypoint. Registration grants no
capability or autonomy. Package tampering, disappearance, invalid manifests,
unsafe instruction paths and understated risk are deterministic failures.
Human CLI is available through `masha.ps1 skills ...`; hashes and technical
payloads remain `--raw` diagnostics.

Stage 16.1 itself added no permission or execution. Stage 16.2 below adds the
separate deterministic permission decision layer; tools, planning and execution
remain not implemented.

Current regression after Stage 16.1: `198 passed`.

## CURRENT — STAGE 16.2 ACTION AUTONOMY POLICY

`ActionAutonomyPolicyStore` persists a separate local master switch, global
level and exact standing grants. `ActionAutonomyEngine` evaluates an
application-owned ActionRequest against registered package integrity, manifest
capabilities/scopes/risk/ceiling and the user's grant. It returns only `ALLOW`,
`REQUIRE_CONFIRMATION` or `DENY` with a deterministic reason.

Policy has no ModelRouter, tool adapter or execution method. Identity write is
denied; Memory write retains its confirmation flow; destructive actions and
external communication cannot receive silent grants. Human CLI exposes policy,
numbered permissions, grant/revoke and read-only checks without internal IDs.

Current regression after Stage 16.2: `217 passed`.

## CURRENT — STAGE 16.3 BOUNDED AGENT LOOP

`BoundedAgentLoop` executes immutable application-owned plans through injected
Tool Adapters. Every step rechecks registered package integrity and the current
Action Autonomy Policy, pauses on confirmation, persists `executing` before the
call and requires deterministic verification afterward. Fake Tool is the only
implemented adapter and performs no real I/O.

`AgentRunStore` keeps a bounded local operating receipt without raw inputs or
outputs. Completed/failed/denied/budget-exhausted runs are idempotent. Restart
never replays an ambiguous `executing` step. The read-only `agent runs/show` CLI
hides technical plan identity in normal UX.

No filesystem/process/network tool, LLM planner, background agent or automatic
domain mutation is connected.

Current regression after Stage 16.3: `236 passed`.

## CURRENT — STAGE 16.4 FIRST LOCAL SKILL

`ProjectObserverTool` is the first real application-wired adapter. It exposes
only bounded `list_tree`, `read_text` and `inspect_path` operations inside one
resolved workspace. Protected/private paths, path traversal, symlinks, writes,
subprocesses and network access are blocked.

The shipped `skills/project_observer` package remains declarative and inert;
the registry never imports it. Explicit registration, enabled action autonomy
and an exact `local_read` standing grant are all required before observation.
The Agent Loop also binds injected `tool_id` to the authorized `skill_id`.

Observed content is returned only after deterministic repeat-read verification
and is never persisted in agent receipts, Memory or conversation history.
Human local access is available through `masha.ps1 observe tree|read|inspect`.
Identity, Memory, Commitment, Temporal, Model Profiles, Router and SQLite schema
are unchanged.

Current regression after Stage 16.4: `249 passed`.

## CURRENT — STAGE 16.5 SAFE SKILL INSTALLATION / UPGRADE

`SkillInstallerService` is the single backend boundary for current CLI and a
future UI. It accepts only a local folder or ZIP, creates a bounded inert staged
snapshot and persists a `SkillInstallProposal` separately from Identity,
Memory, conversation history, proactive policy and SQLite.

Confirmation revalidates exact staged bytes, performs a guarded local package
swap under ignored `local-data/skills/` and uses the existing Registry to replace
the integrity pin. Bundled packages under repository `skills/` are read-only
fallbacks and are not overwritten by UI/CLI installation. Upgrade
requires a newer semantic version and revokes all standing grants for the skill;
permissions never carry over. Reject is non-mutating for the installed package
and removes staging. Completed confirmation is restart-safe and idempotent.

Archive traversal, links, duplicate paths, compiled artifacts, oversized files
and unsupported runtime adapters are blocked. No network or entrypoint import
exists. The UI itself remains planned; its picker/preview/buttons will call this
same service rather than write project code directly.

Current regression after Stage 16.5: `270 passed`.

## CURRENT — STAGE 16.6 PERMISSIONS UX / EMERGENCY STOP

`PermissionControlService` provides one local read model for a future UI and
the human `permissions` CLI. It aggregates existing skill integrity, action
policy, effective grants, installation proposals, Agent Run receipts and
proactive runtime state; it is not a second policy or persistence subsystem.

`AutonomySafetyStore` is ignored local operating configuration at
`local-data/config/autonomy-safety.json`. Its persistent emergency latch has
priority over both Action Autonomy grants and Proactive Policy. The Agent Loop
checks it before work, before every tool call and between verified steps. Daily
Runtime suppresses the complete cycle without calling the LLM, and the
Proactive Daemon exits deterministically.

Releasing the latch changes no policy/grant/domain state and starts nothing.
Ordinary conversation, explicit memory controls and configuration inspection
remain available. No Identity, Memory, Commitment, Temporal, Conversation,
ModelProfile, Router, provider or SQLite schema contract changed. No UI was
implemented.

Current regression after Stage 16.6: `279 passed`.

## CURRENT — UI-01 LOCAL APPLICATION BOUNDARY

`backend.application` is the public in-process boundary for a future local UI.
`build_masha_application(project_root=...)` is the CLI-independent composition
root and returns `MashaApplication`; existing CLI construction delegates to the
same conversation wiring instead of owning a second production assembly.

The facade exposes UI-safe conversation, status, visual-asset and model-profile
contracts. `ConversationTurnResult` distinguishes completed, unavailable,
timeout and failed turns while retaining the persisted user message on a model
failure. `MashaStatusView` keeps runtime health, model availability, proactive
policy, runtime mode and the emergency-stop latch as separate machine-readable
fields. It contains counts rather than internal proposal/event rows.

`VisualIdentityResolver` reads the approved manifest internally, verifies the
canonical asset hash and returns bytes plus display metadata; the UI receives
no filesystem path. `ModelSettingsService` verifies enabled profile, provider
and exact local model before persisting a new active profile. Failure preserves
the previous profile and never triggers fallback.

The boundary exposes no repository, SQLite path, JSON path, raw proposal/audit
payload, daemon lock file, Ollama endpoint or Identity manifest structure.
Identity, Memory, Commitment, Temporal, Proactive, ModelRouter, Skills,
permissions, Agent Loop and SQLite schema semantics are unchanged. UI-01 adds
no frontend, HTTP, streaming, scheduler or agent capability.

Current regression after UI-01: `290 passed`.

## DESIGN ONLY — UI-02 / UI-02.5 INTERACTION AND PRESENTATION CONTRACT

`docs/UI-02_INTERACTION_PRESENCE_DESIGN.md` defines Masha-centred interaction,
deterministic presentation states, independent safety/proactive/model/runtime
overlays and the Shared Room direction. `docs/UI-02_5_PRESENTATION_MODEL.md`
refines that direction into a framework-independent `HomePresentationModel`,
composable `MashaPresence`, declarative `InteractionSurface`, observable
`ActivityPresentation` and presentation-preference contract.

The UI-02/UI-02.5 documents themselves add no runtime or domain authority. UI-03
implements the framework-independent foundation described below, but no
production frontend, event stream, rich asset pack, preference store or
HTTP/WebSocket boundary exists. UI-01 remains the application boundary;
Identity, Memory, Commitment, Temporal, Proactive, Agent Loop, Permissions,
Safety, model routing and SQLite semantics remain unchanged.

## CURRENT — UI-03 PRESENTATION RUNTIME FOUNDATION

`backend.presentation` now implements immutable compositional Home/Presence,
overlay, `InteractionSurface` and `ActivityPresentation` models plus a pure
deterministic reducer. A read-only adapter projects UI-01 status, active model
and opaque canonical visual asset IDs into the presentation model. The layer has
no repository, provider, LLM, persistence or frontend callback dependency.

The disposable Tier 0 Tk adapter renders one Shared Room scene and drives local
scenario events for conversation, Activity, proactive attention, emergency
stop, model/runtime state and privacy masking without Ollama. Tk is not a
production-framework decision. No domain or SQLite schema semantics changed.

Current regression after UI-03: `307 passed`.

## DESIGN ONLY — UI-04A HOME COMPOSITION CONTRACT

`docs/UI-04_HOME_COMPOSITION_CONTRACT.md` audits the disposable Tier 0 visual
metaphor and defines the target spatial semantics of one presence-first Home.
The room and Masha are persistent; Conversation, Activity, Confirmation,
Proactive and future capability Surfaces are bounded contextual objects that
appear around a shared attention anchor rather than permanent dashboard panels.

The existing UI-03 Surface contract is sufficient for semantic lifecycle but
does not yet carry renderer-neutral spatial intent. UI-04A therefore specifies,
without implementing, `SurfaceCompositionIntent` (anchor, allowed placement,
size, priority, interaction mode and relation to Presence) and a future pure
`CompositionResolver` producing a `CompositionPlan` from composable state and
viewport/privacy/accessibility constraints.

The recommended first real visual tier is layered/composited Tier 1: a warm
realistic or semi-realistic room with a restrained cinematic near-future layer.
Tk layout, permanent status header/panels, abstract Masha figure, palette and
prototype controls remain disposable. No production code, framework, renderer,
domain contract or SQLite schema was changed by UI-04A.

## CURRENT — UI-04B COMPOSITION RUNTIME FOUNDATION

`backend.presentation.composition` now turns `HomePresentationModel`, viewport
characteristics and one selected semantic variant into an immutable
`CompositionPlan`. `SurfaceCompositionIntent` adds renderer-neutral anchor,
placement, size, priority, interaction, transform, Presence-relation and
occlusion constraints to an `InteractionSurface` without changing its lifecycle.

The pure `CompositionResolver` produces the ambient room, Masha composition,
bounded primary/supporting/decision regions, privacy/safety/model/runtime
overlays, focus ownership and suppressed Surface IDs. It has no pixel
coordinates, framework callbacks, LLM, application service, repository or
persistence dependency.

Layout stability is deterministic: an explicitly supplied previous plan may
retain a still-allowed placement; text, progress and expression-only changes do
not force spatial recomposition. Privacy and viewport changes override
hysteresis. Implemented variants are `presence_first`, `conversation_first` and
`adaptive_cinematic`; they are plans from one resolver, not separate frontends.

Current regression after UI-04B: `334 passed`.

## CURRENT — UI-06B PRODUCTION HOME

The production visual renderer is owned by root `frontend/` and is served only
through the hardened offline `masha://home/` origin. `backend.ui` remains the
PySide6/WebEngine host and a closed typed WebChannel bridge; it does not own
frontend assets and the renderer has no direct persistence, domain, Ollama or
filesystem access. Packaging installs the same renderer under
`share/masha-home/frontend` without changing this boundary.

The implemented production slice contains one room-first composition with
Masha as the persistent visual anchor, real Conversation, New conversation, a
temporary spatial conversation shelf, a bounded read-only Home Attention view,
Emergency Stop/Resume, honest model-unavailable presentation and deterministic
presence transitions. Stop leaves Conversation and drafts usable; Resume does
not resume stopped autonomous work.

Only application-owned UI-safe projections cross the bridge. Memory,
Commitments, Activities, Proactive/Check-in, Skills, Permissions, model
switching, Voice, Media, Devices and automatic privacy have no production UI in
this stage. No domain semantics or SQLite schema changed.

## CURRENT — UI-06D TYPED COMMITMENT CONFIRMATION

Commitment creation and completion proposals can now appear as a focused,
typed production Home surface. The application exposes only a bounded
`PendingConfirmationView`; proposal IDs are opaque bridge tokens and are
removed from normal transcript content. Confirm/reject call the existing
proposal flow and the short persistence operation is represented by the
deterministic Activity lifecycle before its truthful result.

No second proposal store, Commitment state machine, date parser, persistence
layer or frontend mutation logic was introduced. A pending confirmation is
restored after restart from the existing local proposal store.

## CURRENT — UI-06E COMMITMENTS AS WORK OBJECTS

Existing Commitments are now projected through `CommitmentApplicationService`
as bounded immutable UI contracts. The service reads the active SQLite-backed
Memory document and delegates deadline semantics to the existing Temporal
Engine; it does not own a clock, repository or status state machine.

The production renderer opens the projection from the small spatial `Дела`
object. An explicitly selected actionable Commitment enters the existing
completion proposal, confirmation, persistence and audit flow. Listing and
selection do not invoke the LLM, and no Commitment changes before explicit
confirmation. Technical record and proposal IDs remain opaque bridge values.

## CURRENT — UI-06F MOTION AND CAPABILITY REVIEW GATE

The production renderer applies presentation-driven scene changes with a
deterministic settle delay, minimum frame hold and sequential exit/enter. At no
point should two Masha scene layers be visible together. Conversation geometry
is stable across empty/history states, preventing text-driven layout reflow.

The disconnected UI-06C workshop now demonstrates all ten agreed capability
moments through one lifecycle grammar: `appeared`, `focused`, `waiting`, then
`resolved` or `dismissed`. It remains offline and has no WebChannel, backend,
SQLite, Ollama or local-data access.

The visual grammar was accepted. Production now has bounded
`AgentRunListView`/`AgentStepView` receipt projections and a
`ProactiveInteractionListView` for already-delivered Reminder/Check-in
interactions. The bridge exposes three explicit operations: load Agent Runs,
load proactive interactions and acknowledge/dismiss one currently visible
delivered interaction.

The renderer receives no tool IDs, policy reasons, plan hashes, event payloads,
repository handles or SQLite details. Agent runs are read-only. Proactive actions
reuse the existing lifecycle and do not mutate Memory, Identity, Commitment or
Conversation history. Contextual triggers remain hidden when there is no real
object to show.

## CURRENT — UI-06G SLICE B

The production application boundary now projects Shared Continuity through a
bounded `SharedContinuityView`: confirmed Fact/Decision/Episode records,
relationship moments and open follow-up threads. Reading it is side-effect free;
returning to a thread only prefills the conversation composer.

`ReflectionWorkspaceView` keeps adopted Masha reflections separate from pending
interpretations and Honest Help offers. Adoption/rejection and help
acceptance/dismissal delegate to the existing Stage 15 service. Honest Help
uses the selected local model only after explicit acceptance and writes the
result to the source conversation. Emergency Stop blocks these actions.

The frontend receives neither raw MemoryDocument nor evidence/audit/proposal
internals. This slice changes no SQLite schema, Identity, Commitment, Temporal,
model-profile or proactive-policy contract.

## CURRENT — UI-06H SLICE C

The production Home contains a contextual `Режим` workbench backed by a bounded
`WorkbenchView`. It projects existing local Model Profiles, Skill Registry,
effective permissions and pending controls without exposing package details,
grant/proposal identifiers, local paths or persistence handles.

The bridge allows only two operations: read this projection and manually select
an existing available Model Profile. Selection delegates to LLM-03, has no
fallback and leaves Identity, Memory, Commitments, Temporal state, conversation
history, policy and grants untouched. Emergency Stop still governs autonomous
work, but does not prevent selecting a local execution profile.
