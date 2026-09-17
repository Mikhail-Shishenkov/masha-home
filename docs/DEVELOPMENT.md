# Masha Home — локальная разработка

Этот файл описывает **текущий** способ работать с репозиторием. История реализации и старые stage-by-stage инструкции не являются developer guide; для них используются Git history и исторические документы.

Актуальная карта документации: [`README.md`](README.md).

## 1. Поддерживаемая среда

`pyproject.toml` поддерживает Python **3.10–3.12**. Репозиторий фиксирует baseline через `.python-version`.

Windows / PowerShell:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,ui]"
```

Для backend-only разработки UI extra не обязателен:

```powershell
python -m pip install -e ".[dev]"
```

Editable install связывает окружение с рабочим деревом; обычные изменения Python-файлов не требуют повторной установки пакета.

## 2. Основные entry points

Человеческие entry points определены `masha.ps1`:

```powershell
.\masha.ps1 chat
.\masha.ps1 home
.\masha.ps1 status
.\masha.ps1 run
.\masha.ps1 receipts
.\masha.ps1 background
.\masha.ps1 stop
```

Также доступны bounded operating surfaces:

```powershell
.\masha.ps1 skills <args>
.\masha.ps1 agent <args>
.\masha.ps1 observe <args>
.\masha.ps1 permissions <args>
```

Фактические модули под ними:

- chat → `python -m backend.conversation.cli`;
- desktop Home → `python -m backend.ui.desktop_host`;
- daily runtime → `python -m backend.runtime.cli ...`;
- background proactive runtime → `backend.temporal.proactive_daemon`.

`python -m backend.main` **не является production entry point Masha Home** и не должен использоваться как инструкция запуска Дома.

## 3. Current data ownership

Production long-term Memory принадлежит SQLite repository. JSON memory files используются только там, где их конкретный контракт определяет import/export/fixture/backup роль; они не являются параллельным production source of truth.

Ключевые ownership-границы:

- Identity → approved Identity manifest + `IdentityKernel`;
- long-term Memory → application-owned SQLite repository;
- conversation history → отдельный conversation store;
- time → `TemporalEngine` / application-owned Home clock;
- actions → domain/application proposal, policy, confirmation, operation and receipt;
- LLM output → untrusted language/meaning proposal, никогда не execution truth.

Текущий Home timezone: `Europe/Saratov` с application-owned fallback, а не `Europe/Moscow`.

## 4. Model profiles

Активный model profile хранится локально в `local-data/config/models.json`; файл не является частью Git source of truth.

Смена модели не меняет Identity, Memory, conversation history, permissions или temporal state.

Текущий coherence-checkpoint измерял semantic behavior на настроенном FAST profile (`masha-fast:4b`). Это evidence конкретного checkpoint-а, а не требование архитектуры навсегда.

Не менять модель как способ "починить" архитектурную ошибку до того, как измерен реальный payload/trace и исключены проблемы контекста, schema presentation, grounding и application state.

## 5. Tests vs evals

Основной deterministic gate без opt-in live providers:

```powershell
python -m pytest -q -m "not live_smoke"
```

Полный обычный pytest:

```powershell
python -m pytest
```

Маркер `live_smoke` зарезервирован для тестов, требующих живой модели, сети, connector/provider или другого внешнего runtime. Такие проверки не должны незаметно выполняться как обычный deterministic gate.

Дополнительные маркеры из `pyproject.toml`:

- `release` — критические deterministic product journeys;
- `contract` — authority/storage/safety/privacy/adapter invariants;
- `live_smoke` — opt-in live behavior.

Не фиксировать в этом файле "текущий" абсолютный test count: он быстро устаревает. Последнее измеренное evidence конкретной рабочей ветки хранится в её checkpoint-документе.

Разделение качества:

- deterministic invariant → `tests/`;
- variable model/language quality → `evals/`;
- финальная разговорная/UX приёмка → Human Review.

Подробнее: [`../evals/README.md`](../evals/README.md).

## 6. Active coherence work

Ветка `new/agent-coherence-continuation` является **незавершённым engineering checkpoint**, не релизом.

Продолжать работу нужно с [`AGENT_COHERENCE_PLAN.md`](AGENT_COHERENCE_PLAN.md), а не с ранних Router V2 / Slice roadmap-ов.

Сейчас доказаны архитектурные границы unified context / meaning-first resolution, но остаются открыты:

- relative-time field extraction;
- complete multi-turn dialogue journeys;
- live/manual conversational acceptance.

Не объявлять работу законченной только по зелёному deterministic gate.

## 7. Local data, secrets and safety

`local-data/` содержит operating/runtime state и не должен превращаться в тестовую площадку для случайных destructive probes.

Правила разработки:

- не коммитить secrets, tokens, credentials и private runtime payloads;
- не использовать реальный mailbox/calendar mutation для engineering probes, если сценарий можно проверить synthetic/fake adapter-ом;
- не считать model sentence receipt-ом;
- не выдавать старую conversation/application history за authority;
- не создавать второй state owner рядом с существующим application contract;
- не менять Identity/Memory schema в рамках языковой полировки.

Whole-Home backup/recovery contracts описаны отдельно:

- [`W5_1_WHOLE_HOME_BACKUP.md`](W5_1_WHOLE_HOME_BACKUP.md)
- [`W5_2_WHOLE_HOME_RECOVERY.md`](W5_2_WHOLE_HOME_RECOVERY.md)

## 8. Где искать истину

Для нового изменения читать минимально необходимый контекст в таком порядке:

1. текущий код владельца проблемы;
2. active checkpoint / newest verified evidence;
3. normative domain/security contract;
4. [`MASHA_HOME_CANON.md`](MASHA_HOME_CANON.md);
5. [`DECISIONS.md`](DECISIONS.md);
6. historical stage/snapshot documents — только для provenance.

Не начинать архитектурное расследование со старого implementation plan, если код и новые checkpoint-ы уже зафиксировали другое состояние.
