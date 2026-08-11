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

## Конфигурация

`.env.example` содержит только безопасные локальные значения и зарезервированные ключи. Текущий прототип ещё не загружает `.env` автоматически.

Настоящие секреты не должны попадать в репозиторий. Локальный `.env` исключён через `.gitignore`.
