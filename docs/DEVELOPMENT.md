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
- основной `ContextBuilder` работает на Memory v0.4.

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

Утверждённый manifest находится в `identity/masha.identity.json`, регрессионные сценарии образа — в `identity/masha.regression.json`, а канонические визуальные assets — в `identity/visual_assets/`. Их назначение и правила изменения описаны в `docs/IDENTITY_GUIDE.md`.

## Model Router

Модельный слой находится в `backend.llm`. Для тестов используется только локальный `FakeProvider`; реальный runtime, модель и внешний API не настраиваются автоматически. `ModelRequest` содержит Immutable Identity Context, а `private_context` допускается только для локального маршрута. Подключение или установка реального провайдера — отдельный подтверждаемый этап `LLM-02`.

## Конфигурация

`.env.example` содержит только безопасные локальные значения и зарезервированные ключи. Текущий прототип ещё не загружает `.env` автоматически.

Настоящие секреты не должны попадать в репозиторий. Локальный `.env` исключён через `.gitignore`.
