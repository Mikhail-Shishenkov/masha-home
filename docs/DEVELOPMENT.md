# Masha Home — локальная разработка

## Поддерживаемая версия Python

Проект поддерживает Python 3.10–3.12. Текущий baseline разработки — Python 3.10, зафиксированный в `.python-version`.

## Создание окружения

PowerShell:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Установка `-e` связывает окружение с рабочим деревом проекта. После изменения Python-файлов повторная установка пакета обычно не требуется.

## Запуск прототипа

Из корня репозитория:

```powershell
python -m backend.main
```

Текущий `backend.main` является только ранним прототипом приветствия и ещё не запускает Companion Core.

## Запуск тестов

```powershell
python -m pytest
```

## Состояние тестов после LLM-01

Экспериментальные исполняемые скрипты преобразованы в изолированный pytest suite:

- проверки выполняются внутри pytest-функций;
- изменяемые данные копируются в `tmp_path`;
- постоянные fixtures не изменяются;
- WorkingMemory проверяется через production-класс;
- ошибочный отдельный validator заменён pytest-тестами схемы;
- формат памяти проверяется Pydantic-моделью при загрузке и сохранении;
- JSON Schema воспроизводимо генерируется из Pydantic-модели;
- миграция v0.3 → v0.4 проверяется на сохранение сущностей и повторный безопасный запуск.
- SQLite-репозиторий использует WAL, foreign keys, миграции и короткие транзакции `BEGIN IMMEDIATE`;
- backup восстанавливается только в отдельный файл БД и проверяется тестом.
- Identity Manifest загружается read-only, имеет явную версию и не может стать утверждённым без заданных черт и метаданных утверждения;
- визуальные assets проверяются по SHA-256, а сценарии образа версионированы отдельно от LLM.
- Model Router проверяет capabilities, предпочитает local provider и не передаёт private context внешнему провайдеру;
- FakeProvider позволяет проверять диалоговый слой без модели, сети или платного API.

Проверка 2026-08-10:

- editable-установка `python -m pip install -e ".[dev]"` — успешно;
- `python -m pip check` — успешно;
- `python -m backend.main` — успешно;
- компиляция backend — успешно;
- `python -m pytest` — `54 passed`;
- SHA-256 постоянных fixtures до и после тестов совпадает.

Прежние четыре `xfail` закрыты:

- Project и Fact синхронизированы с каноническим документом;
- корневой memory document описан JSON Schema;
- `importance` Episode ограничен диапазоном `0..1`;
- исторический `ContextBuilder` удалён; production-разговор использует
  `ConversationContextCompiler` и активную SQLite memory.

## Генерация схемы и миграция памяти

JSON Schema не редактируется вручную:

```powershell
python -m backend.memory.generate_schema memory/memory_schema.json
```

Версионированная миграция создаёт валидный Memory v0.4 и может писать в отдельный файл или безопасно заменить исходный после полной загрузки и проверки:

```powershell
python -m backend.memory.migrations.v03_to_v04 input-v03.json output-v04.json
```

## SQLite-память (подготовлена, но не активирована)

`MemorySqliteRepository` в `backend.memory.sqlite_repository` импортирует и экспортирует только валидный Memory v0.4, хранит audit events и работает с локальным SQLite без внешних сервисов.

Создать отдельную БД из JSON можно так:

```powershell
python -c "from backend.memory.sqlite_repository import MemorySqliteRepository as R; R('memory/masha.sqlite3').import_json('memory/test_memory.json')"
```

Этот пример создаёт новую БД и **не** переключает текущий JSON-прототип. Backup также создаётся отдельно, а `restore_to` отказывается перезаписывать существующий файл. Перед переключением рабочего приложения на SQLite для реальных данных потребуется отдельное подтверждение пользователя и проверенная резервная копия.

## Identity Kernel

> **Current runtime status (2026-08-11):** SQLite at
> `local-data/memory/masha.sqlite3` is production long-term memory; JSON is
> import/export/backup only. The CLI uses `IdentityKernel` and validates its
> identity version against active SQLite before startup. Legacy PersonaStore
> and ContextBuilder are not runtime components.

> **MEM-10 status (2026-08-11):** `MemoryManagementService` operates on the
> same SQLite repository as conversation retrieval. Its inspection, trace and
> explicit mutation proposals do not create an alternative memory store.

> **MEM-11 status:** time is deterministic and application-owned: UTC is
> canonical, Moscow is offline UTC+03:00, and due dates are stored in UTC.
> Overdue is computed at runtime. A Commitment is created or completed only by
> explicit proposal and confirmation; ordinary conversation never changes it.

> **MEM-10.1 status (2026-08-11):** user-facing memory CLI output is
> human-readable by default; JSON identifiers, audit payloads and retrieval
> details remain available only through `--raw`/diagnostic output. Preview and
> explicit confirmation still precede every mutation.

Утверждённый manifest находится в `identity/masha.identity.json`, регрессионные сценарии образа — в `identity/masha.regression.json`, а канонические визуальные assets — в `identity/visual_assets/`. Их назначение и правила изменения описаны в `docs/IDENTITY_GUIDE.md`.

## Model Router

Модельный слой находится в `backend.llm`. `ModelRequest` содержит Immutable
Identity Context, а `private_context` допускается только для локального
маршрута. Production CLI uses `OllamaProvider` through `ModelRouter`; tests may
use `FakeProvider`.

The local file `local-data/config/models.json` persists only the active
execution profile. Use `model list`, `model current`, and `model use fast` in
the conversation CLI. `primary` is `qwen3.5:9b`, `fast` is `qwen3.5:4b`; both
use `think=false`. The command verifies local Ollama and the target model
before changing the file. It never downloads models and never falls back.
Profiles do not change Masha's identity, SQLite memory, conversation history,
or temporal state.

## MEM-12.1 temporal foundation

`backend.temporal.temporal_runtime` deterministically recovers only overdue
Commitment events into the existing local `temporal_events` table. Event IDs
are stable across restart. `backend.temporal.proactive` is a pure policy
decision layer; it has no scheduler, delivery, LLM call, CLI or persistent user
settings. It never mutates MemoryDocument, Commitment, Identity or history.

## MEM-12.2 proactive interaction

`ProactiveInteractionService` routes only an authorised `REMIND` candidate
through the existing ModelRouter and active local profile. The local SQLite
interaction state prevents repeat delivery after acknowledgement/dismiss.
There is no scheduler, background process, external delivery or fallback.

## MEM-12.3 persistent proactive policy

`local-data/config/proactive-policy.json` is local operating configuration
separate from `models.json`. Use `proactive status`, `proactive on`,
`proactive off`, `proactive level <0-5>` and `proactive run` in the CLI. The
default policy is disabled / level 0. The run is manual and local: it can only
deliver a deterministically authorised Commitment reminder and never changes
Memory, Identity, Commitment or conversation history.

## MEM-12.5 proactive event store

Migration v4 adds `proactive_events`, a standalone lifecycle table for
`commitment_reminder` and `check_in`. Use it through
`backend.temporal.proactive_events.ProactiveEventStore`; it has no LLM,
scheduler, detection or delivery responsibility.

## MEM-12.6 check-in detection

`ConversationStore.latest_message()` returns the globally newest stored
message. `CheckInDetector` combines it with `TemporalEngine` and a policy
threshold to persist an idempotent CHECK_IN event. It has no CLI, scheduler,
LLM call or delivery path.

## MEM-12.7 check-in lifecycle

`CheckInLifecycleRuntime` applies existing proactive policy and persists only
`detected → candidate` when authorised. It has no delivery or LLM dependency.

## MEM-12.8 controlled proactive runtime

Use `proactive mode manual|background`, `proactive run`, and `proactive daemon
start|stop|status`. Background mode is opt-in and persists in the existing
policy file. Runtime lock/status/stop files live under `local-data/runtime`.
There is no OS autostart or external channel.

## MEM-12.9 proactive UX and safety boundaries

Use `proactive status`, `proactive settings`, `proactive pending` and
`proactive history` for human-readable operation. Add `--raw` only for local
diagnostics. Decision reasons come from deterministic runtime rules and are
recorded in the existing audit log. `proactive off` is the complete delivery
switch. The daemon recovers stale locks and records cycle failures without
gaining decision authority. External events are not implemented and are always
suppressed at the explicit origin boundary.

## Stage 13 Daily Runtime

Use one of the human entry points:

```powershell
.\masha.ps1 chat
.\masha.ps1 status
.\masha.ps1 run
.\masha.ps1 receipts
.\masha.ps1 background
.\masha.ps1 stop
```

The equivalent technical commands are `python -m backend.runtime.cli
status|run|receipts`. Both daemon and manual execution use `DailyRuntime`.
Receipts live in ignored `local-data/runtime/daily-runtime-receipts.json`, are
bounded to 100 entries and contain no generated message text. Health checks are
read-only. Missing backups and a stopped daemon are warnings; the runtime does
not silently repair or mutate persistent domain state.

## Stage 14 Shared Continuity

Use the conversation CLI or the same commands through `masha.ps1 chat`:

```text
continuity
continuity open <тема>
continuity resolve <тема>
continuity confirm
continuity reject
```

In normal conversation use explicit phrases such as `Маша, сохрани как наш
момент: ...` or `Маша, оставь открытой нитью: ...`, then confirm the preview.
Normal chat never creates shared memory automatically. Add `--raw` only for
local diagnostics; it may include internal IDs and quarantined legacy payloads.

## Stage 15 Masha Perspective & Honest Help

Use explicit conversation phrases:

```text
Маша, подумай о себе: <тема>
Маша, подумай о нас: <тема>
прими рефлексию
отклони рефлексию
Маша, пересмотри рефлексию о <тема>: <новый контекст>
Маша, это помогло: <что именно>
Маша, это не помогло: <что именно>
давай, помоги
не надо помогать
```

Inspection commands are `reflections list|pending|show|adopt|reject|reconsider`
and `help pending|accept|reject`. Normal output hides internal IDs; use `--raw`
only for local diagnostics. Reflection generation requires the active local
profile to declare `structured_output`; `primary` supports it and no fallback
to another profile occurs. Ordinary chat neither creates reflections nor
injects them into general context.

## UI-06G Slice B

The production Home has contextual `Наша история` and `Мысли` objects. They are
hidden when their bounded application projections are empty.

- Continuity is read-only and shows only confirmed Fact/Decision/Episode
  summaries, shared moments and open threads.
- A thread action only prefills the composer; sending stays manual.
- Reflection candidates require explicit adopt/reject.
- Honest Help requires explicit accept/dismiss; only accept invokes the active
  local model.
- Emergency Stop blocks all Slice B decision actions.

Run the focused regression with:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_application_boundary.py tests/test_desktop_host.py -q
node --check frontend/renderer/app.js
```

## UI-06H Slice C

`Режим` opens the local workbench: available profiles, installed skills,
effective standing permissions and pending controls. It does not expose raw
configuration or package data.

The only action in this slice is manually choosing an already configured and
available local model. The provider/model availability check occurs before the
active profile changes; no fallback is attempted. Emergency Stop does not block
this operating preference, but it continues to block autonomous work.

Skill installation, upgrades and permission grants remain CLI-only until their
separate proposal/confirmation UI exists.

## Stage 16.1 Skill Registry

Developers may place a bundled package under `skills/<skill_id>/` with
`skill.json` and the declared instructions file. User/UI installations go to
ignored `local-data/skills/`. Then use:

```powershell
.\masha.ps1 skills list
.\masha.ps1 skills show <skill_id>
.\masha.ps1 skills verify <skill_id>
.\masha.ps1 skills register <skill_id>
```

Add `--raw` only for the package digest and full technical descriptor. Listing
and verification are read-only. Registration writes only
`local-data/config/skills.json`; it does not import code or grant execution.
Changed registered packages are reported as `modified` and must remain blocked.

Run targeted tests with:

```powershell
python -m pytest tests/test_skill_registry.py -q
```

### Stage 16.2 action permissions

```powershell
.\masha.ps1 skills policy status
.\masha.ps1 skills policy on
.\masha.ps1 skills policy level 2
.\masha.ps1 skills permissions
.\masha.ps1 skills grant <skill> <capability> <scope> <level> [risk]
.\masha.ps1 skills revoke <номер>
.\masha.ps1 skills check <skill> <capability> <scope> <level> [risk]
```

Policy state lives at ignored `local-data/config/action-autonomy.json`. `check`
does not execute anything. Run the combined targeted regression with:

```powershell
python -m pytest tests/test_skill_registry.py tests/test_action_autonomy.py -q
```

## Stage 16.3 Bounded Agent Loop

Read local operating receipts:

```powershell
.\masha.ps1 agent runs
.\masha.ps1 agent show <номер>
```

The agent journal CLI is read-only. Stage 16.4 additionally provides one real,
strictly read-only ProjectObserver adapter; there is still no LLM planner or
general plan-authoring flow.

```powershell
python -m pytest tests/test_agent_loop.py tests/test_action_autonomy.py tests/test_skill_registry.py -q
```

Receipts are stored only after an explicit application run at
`local-data/runtime/agent-runs.json`. Listing an empty journal does not create
the file.

## Stage 16.4 Project Observer

The first real skill is shipped as a discovered but unregistered package. To
enable its exact read-only boundary deliberately:

```powershell
.\masha.ps1 skills register project_observer
.\masha.ps1 skills policy on
.\masha.ps1 skills policy level 1
.\masha.ps1 skills grant project_observer local_read workspace:masha-home 1 observe
```

Then use the human-readable observer:

```powershell
.\masha.ps1 observe tree
.\masha.ps1 observe tree backend --max-depth 2 --max-entries 100
.\masha.ps1 observe read README.md --max-chars 8000
.\masha.ps1 observe inspect pyproject.toml
```

`--raw` exposes diagnostic payloads. Normal output hides plan IDs and internal
policy identifiers. The observer cannot read `local-data`, `.git`, `.venv`,
environment/credential/key files or symlinks, and has no write, process or
network capability. Read contents are not stored in agent receipts.

Targeted verification:

```powershell
python -m pytest tests/test_project_observer.py tests/test_agent_loop.py tests/test_action_autonomy.py tests/test_skill_registry.py -q
```

## Stage 16.5 Local Skill Installation / Upgrade

Select a package directory or ZIP. The first command creates only a preview:

```powershell
.\masha.ps1 skills install C:\path\to\skill-package
.\masha.ps1 skills install pending
.\masha.ps1 skills install confirm
.\masha.ps1 skills install reject
.\masha.ps1 skills installs
```

Normal output shows versions, capabilities, scopes, risk, file-change counts
and permission revocation. It hides proposal IDs, SHA-256 and staging paths;
`--raw` exposes the UI/debug contract.

The future UI should use a local folder/ZIP picker and call
`SkillInstallerService.propose()`, render `SkillInstallProposal`, then call
`confirm()` or `reject()` with the proposal ID. UI code must not copy files or
edit Registry state itself.

Staging and proposal state live in ignored local operating storage:

- `local-data/skills/` — confirmed local packages and overrides;
- `local-data/config/skill-installs.json`;
- `local-data/skill-install/staging/`;
- temporary recovery backups under `local-data/skill-install/backups/`.

No remote URL is accepted. A package with no application-wired safe adapter is
visible in preview but cannot be confirmed. Installing declarative files is not
arbitrary plugin-code execution.

Targeted verification:

```powershell
python -m pytest tests/test_skill_installer.py tests/test_skill_registry.py tests/test_action_autonomy.py -q
```

## Stage 16.6 Permissions and local emergency stop

Use the unified human view:

```powershell
.\masha.ps1 permissions status
.\masha.ps1 permissions skills
.\masha.ps1 permissions grants
.\masha.ps1 permissions pending
```

Engage or release the persistent local safety latch:

```powershell
.\masha.ps1 permissions stop
.\masha.ps1 permissions stop "reason for the local stop"
.\masha.ps1 permissions resume
```

`permissions stop` blocks new Agent Loop steps and proactive cycles. It does
not remove grants, disable/edit policies, mutate domain data or stop ordinary
chat. `permissions resume` only releases the latch; it does not restart the
daemon, resume denied work or send queued messages. The narrower
`.\masha.ps1 stop` command still requests only proactive-daemon termination.

The future UI should consume `PermissionControlService.snapshot()` and call
`AutonomySafetyService.engage()/release()`. UI code must not edit JSON policy
files directly. Technical IDs remain in `--raw`; normal CLI uses numbered and
human-readable views.

Targeted verification:

```powershell
python -m pytest tests/test_permissions_control.py tests/test_agent_loop.py tests/test_daily_runtime.py tests/test_proactive_daemon.py -q
```

Stage 16.6 baseline: `279 passed` full regression.

## UI-01 local application boundary

Future local interfaces must use the public in-process composition root:

```python
from pathlib import Path

from backend.application import build_masha_application

application = build_masha_application(project_root=Path.cwd())
status = application.status()
profiles = application.model_profiles()
assets = application.canonical_visual_assets()
```

Public operations currently cover:

- `send_message()` and `conversation()`;
- `status()`, `emergency_stop()` and `resume_autonomy()`;
- `canonical_visual_assets()` and `resolve_visual_asset()`;
- `model_profiles()`, `current_model()` and `use_model()`.

The returned contracts deliberately contain no SQLite/JSON paths, repository
objects, raw proposal/audit payloads, daemon files, Ollama endpoint or Identity
manifest internals. Expected conversation/model errors use stable codes and
separate human labels. The boundary remains synchronous and in-process; it is
not an HTTP API and does not implement streaming.

Targeted verification:

```powershell
python -m pytest tests/test_application_boundary.py -q
```

UI-01 baseline: `290 passed` full regression.

## UI-03 Presentation Runtime and Tier 0 prototype

The historical Tier 0 renderer remains available directly for structural
presentation experiments:

```powershell
.\.venv\Scripts\python.exe -m backend.presentation.prototype
```

It uses only `backend.presentation` and standard-library Tk. Keys `1` through
`6` cycle conversation, Activity, proactive, safety, model and runtime
presentation scenarios. Clicking the corresponding room areas performs the same
local transitions. No Ollama or domain persistence is used.

Targeted verification:

```powershell
python -m pytest tests/test_presentation_runtime.py tests/test_tier0_prototype.py tests/test_application_boundary.py -q
```

UI-03 baseline: `307 passed` full regression.

## UI-06B production Home

Run the current offline desktop Home from the repository root:

```powershell
.\masha.ps1 home
```

The production renderer lives in root `frontend/`; `backend.ui` owns only the
PySide6/WebEngine host, the closed typed WebChannel bridge and the hardened
`masha://home/` local origin. The renderer has no external network access and
cannot execute arbitrary backend commands.

The current UI slice exposes only Conversation, New conversation, the temporary
conversation shelf, bounded Home Attention and Emergency Stop/Resume. Missing
UI-safe projections are intentionally not rendered. Stop pauses autonomous
activity but keeps Conversation and its draft available; Resume only clears the
latch and does not restart work.

Shortcuts: `Ctrl+H` opens Home Attention, `Ctrl+L` focuses Conversation,
`Ctrl+Shift+S` engages Stop, and `Escape` closes temporary surfaces.

Targeted verification:

```powershell
python -m pytest tests/test_application_boundary.py tests/test_desktop_host.py tests/test_presentation_runtime.py tests/test_composition_runtime.py -q
node --check frontend/renderer/app.js
node frontend/scenes/scene-map.test.cjs
```

## UI-04A Home Composition audit

UI-04A is documentation-only. The formal contract is:

```text
HomePresentationModel
+ SurfaceCompositionIntent
+ viewport/privacy/accessibility constraints
→ pure CompositionResolver
→ CompositionPlan
→ replaceable renderer
```

See `docs/UI-04_HOME_COMPOSITION_CONTRACT.md`.

Do not implement a production renderer directly from the current Tk geometry.
The persistent target scene is the room plus Masha; Conversation, Activity,
Confirmation and Proactive Surfaces are adaptive contextual objects. The status
header, fixed left/right/bottom panels, abstract figure and prototype controls
are disposable.

UI-04A itself added no executable code. UI-04B implements the spatial contracts
and resolver below. A disposable visual comparison and user review still precede
the production frontend decision.

## UI-04B Composition Runtime Foundation

Resolve a renderer-neutral room plan without UI-01, Ollama or persistence:

```python
from backend.presentation import (
    CompositionResolver,
    CompositionVariant,
    ViewportCharacteristics,
    ViewportClass,
)

plan = CompositionResolver().resolve(
    presentation_model,
    viewport=ViewportCharacteristics(size_class=ViewportClass.WIDE),
    variant=CompositionVariant.PRESENCE_FIRST,
    previous_plan=None,
)
```

`previous_plan` is optional and explicit. Passing it enables deterministic
placement hysteresis; the resolver stores no state. The plan contains semantic
placements and priorities, never pixels, filesystem paths or renderer commands.

Targeted verification:

```powershell
python -m pytest tests/test_composition_runtime.py tests/test_presentation_runtime.py tests/test_tier0_prototype.py tests/test_application_boundary.py -q
```

UI-04B baseline: `55 passed` targeted; `334 passed` full regression.

## UI-06D typed commitment confirmation

Start the normal desktop Home and write an explicit Commitment request, for
example:

```text
Маша, запомни, что завтра в 18:00 нужно отправить отчёт
```

The production Home presents a human confirmation surface with
`Подтверждаю` and `Не сейчас`. Both operations use the existing deterministic
proposal path. The UI never needs a proposal UUID and no LLM call is made to
resolve the choice.

Targeted verification:

```powershell
python -m pytest tests/test_application_boundary.py tests/test_desktop_host.py tests/test_conversation_service.py tests/test_memory_intent.py tests/test_commitment_completion.py -q
node --test frontend/scenes/scene-map.test.cjs
```

## UI-06E Commitment work objects

Use the small `Дела` object at the bottom of the production Home. The list is
read-only until an open item is explicitly selected with `Готово`. Selection
creates a proposal; `Подтверждаю` or `Не сейчас` then use the same UI-06D
confirmation and Activity flow.

The displayed statuses are deterministic Temporal Engine projections. In
particular, `due_at == now` is still open. Listing does not invoke Ollama or
write Memory.

Targeted verification:

```powershell
python -m pytest tests/test_application_boundary.py tests/test_desktop_host.py -q
node --test frontend/scenes/scene-map.test.cjs
```

## UI-06F motion and capability workshop

Open the disposable workshop directly:

```powershell
start docs\prototypes\ui-06c\index.html
```

For each of the ten scenes, use `Посмотреть`, then `Оставить рядом`, then choose
the primary or secondary resolution. Check that the spatial object reads as
`appeared → focused → waiting → resolved/dismissed` while the canonical room and
Masha remain unchanged.

The production Home has only motion stabilization in this step: minimum scene
hold, settle delay, sequential fade and stable Conversation geometry. The
workshop is deliberately disconnected from the production WebChannel.

Targeted verification:

```powershell
node --test frontend\scenes\scene-map.test.cjs docs\prototypes\ui-06c\workshop.test.cjs
python -m pytest tests\test_desktop_host.py tests\test_presentation_runtime.py tests\test_composition_runtime.py -q
```

After visual acceptance, production Slice A is also active. Start the desktop
Home normally. `Работа` appears only if
`local-data/runtime/agent-runs.json` contains real receipts. `Рядом` appears only
if SQLite contains an existing delivered Reminder or Check-in interaction.
Closing a surface is presentation-only; `Понял` and `Не сейчас` call the existing
acknowledge/dismiss lifecycle.

Do not create fixture data in production `local-data` for visual testing. The
application and bridge tests build isolated roots and databases.

## Natural-language capability verification

The production conversation route accepts natural variants for querying and
managing Memory, Commitments and Shared Continuity. Writes always stop at a
human-readable preview until explicitly confirmed. Useful deterministic checks:

```powershell
python -m pytest tests/test_capability_router.py tests/test_chat_capability_integration.py -q
```

Minute reminders become normal confirmed Commitments with UTC `due_at` and are
then detected by the existing TemporalRuntime. Starting proactive delivery
still depends on the existing user policy/runtime mode; the router does not
start or bypass it.

## Конфигурация

`.env.example` содержит только безопасные локальные значения и зарезервированные ключи. Текущий прототип ещё не загружает `.env` автоматически.

Настоящие секреты не должны попадать в репозиторий. Локальный `.env` исключён через `.gitignore`.
