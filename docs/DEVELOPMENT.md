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

## Конфигурация

`.env.example` содержит только безопасные локальные значения и зарезервированные ключи. Текущий прототип ещё не загружает `.env` автоматически.

Настоящие секреты не должны попадать в репозиторий. Локальный `.env` исключён через `.gitignore`.
