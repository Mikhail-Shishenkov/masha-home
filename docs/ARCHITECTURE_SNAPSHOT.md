# Architecture Snapshot — Masha Home

Дата фиксации: 2026-08-10. Это снимок фактического состояния рабочего дерева,
а не целевая схема. Он не означает, что незакоммиченные изменения уже образуют
релиз или что любая описанная возможность подключена к живому диалогу.

> **Superseded runtime note (ID-02, 2026-08-11):** the historical audit below
> describes the pre-consolidation state. The section `CURRENT — ID-02 IDENTITY
> RUNTIME CONSOLIDATION` is authoritative for the active identity runtime.

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

`MemoryRetriever` currently retrieves visible active/open/current facts,
decisions, commitments and episodes by project, scoring importance, recency and
type bonus. It does not retrieve all v0.4 record types. `WorkingMemory` limits
the in-process selection to ten items.

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

## CURRENT — MEM-10 MANAGED LONG-TERM MEMORY

`MemoryManagementService` is a local inspection and mutation boundary over the
same active `MemorySqliteRepository`. It lists/gets/searches records with
identity version and available audit metadata, supports project filtering and
reports deterministic Fact conflicts without resolving them. All mutations are
pending JSON proposals first; only an explicit confirmation applies one SQLite
transaction and audit event. Archive and forget both use existing
`visibility=hidden`, preserving the record and excluding it from normal
retrieval. Fact/Decision supersession retains the old record, marks it
superseded, and stores reciprocal `supersedes_id` on the new record.

`MemoryRetriever` now emits deterministic reasons and scores; the compiler
passes a bounded runtime-generated `[record_id=...][type=...]` memory reference
to the local model context. Chat history remains separate and no ordinary turn
creates or mutates long-term memory.

## CURRENT — MEM-11 TEMPORAL ENGINE

UTC is canonical internal time; the offline MVP local presentation is fixed
`Europe/Moscow` UTC+03:00, independent from OS timezone settings. Temporal
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
