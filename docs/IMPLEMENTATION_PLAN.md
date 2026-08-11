# Masha Home — план реализации

Статус документа: рабочая версия 0.1  
Дата фиксации: 2026-08-10

> **Runtime update (ID-02, 2026-08-11):** Stage 5 is implemented for the
> single production identity path: `IdentityKernel` reads the approved manifest,
> and CLI startup validates its `identity_version` against active SQLite memory.
> Legacy PersonaStore/ContextBuilder work is no longer a planned runtime path.

## 1. Порядок работы

Этапы выполняются последовательно. Каждый этап должен оставлять проект в рабочем и проверяемом состоянии.

Стандартная формулировка задачи:

> Выполни задачу `<ID>` из `docs/IMPLEMENTATION_PLAN.md`. Работай только в указанном объёме. Не удаляй существующие изменения. Если потребуется новое архитектурное решение, изменение личных границ или существенное расширение задачи — остановись и запроси решение. Реализуй изменения, запусти релевантные проверки, обнови документацию и дай короткий итог.

После каждой задачи должны быть указаны:

- изменённые файлы;
- выполненные проверки;
- известные ограничения;
- решения, требующие пользователя;
- рекомендуемая следующая задача.

## 2. Этапы до MVP

### DOC-01. Зафиксировать контекст и план

Статус: завершено 2026-08-10.

Цель: перенести устойчивый контекст из переписки в репозиторий.

Результаты:

- `docs/PROJECT_CONTEXT.md`;
- `docs/IMPLEMENTATION_PLAN.md`;
- `docs/DECISIONS.md`.

Критерий готовности: документы не определяют за пользователя границы поддержки и не изменяют исходный код.

### FND-01. Создать воспроизводимое Python-окружение

Статус: завершено 2026-08-10. Текущее доменное падение pytest зафиксировано как baseline для `FND-02` и `MEM-01`.

Цель: обеспечить одинаковый запуск и тестирование проекта.

В объёме задачи:

- определить поддерживаемую версию Python;
- создать `pyproject.toml`;
- объявить runtime и development dependencies;
- настроить pytest;
- сделать импорты пакетов воспроизводимыми;
- добавить `.env.example` без секретов;
- задокументировать команды установки, запуска и тестирования;
- получить baseline текущих тестов.

Не входит: исправление всей доменной модели памяти и подключение LLM.

Критерий готовности: тесты запускаются одной документированной командой в чистом окружении; известные падения зафиксированы отдельно.

### FND-02. Превратить тестовые скрипты в настоящие тесты

Статус: завершено 2026-08-10. Результат проверки: `25 passed, 4 xfailed`; постоянные fixtures не изменяются.

Цель: получить надёжную защиту дальнейшего рефакторинга.

В объёме задачи:

- перенести проверки из import-time скриптов в pytest-функции;
- исключить изменение постоянных fixtures;
- использовать временные каталоги и данные;
- удалить копии production-реализаций из тестов;
- добавить негативные сценарии;
- сохранить тесты текущего ожидаемого поведения там, где оно не противоречит спецификации.

Критерий готовности: тестовый запуск детерминирован и не меняет рабочее дерево.

### MEM-01. Утвердить единый контракт памяти

Статус: завершено 2026-08-10. Нормативный контракт зафиксирован в `docs/MEMORY_SPEC.md` как Memory v0.4.

Цель: синхронизировать документацию, Python-модели, JSON Schema и данные.

В объёме задачи:

- определить точные поля и статусы Project, Fact, Decision, Commitment, Episode и Memory Candidate;
- определить обязательность `project_ids` и временных полей;
- согласовать семантику source, confidence и importance;
- отдельно описать доменный статус и видимость записи;
- определить правила forget, restore, archive и supersession;
- определить поведение глобальной и проектной памяти.

Точка решения пользователя: изменения смыслов сущностей и правил забывания подтверждаются до реализации.

Критерий готовности: в `DECISIONS.md` нет нерешённых противоречий, блокирующих кодирование моделей.

### MEM-02. Реализовать валидируемые модели и схему

Статус: завершено 2026-08-10. Pydantic-модели являются исполняемым источником истины Memory v0.4; JSON Schema генерируется из них; канонические данные и тестовая копия мигрированы с v0.3 без потери сущностей и старого Working Memory.

Цель: создать один исполняемый источник истины для формата данных.

В объёме задачи:

- реализовать Pydantic-модели;
- генерировать либо проверять JSON Schema из тех же контрактов;
- исправить validator и канонические данные;
- проверять диапазоны, статусы, временные метки и обязательные поля;
- добавить тесты сериализации и обратной совместимости.

Критерий готовности: канонические данные валидируются, заведомо некорректные данные отклоняются, основной ContextBuilder не падает из-за несовпадающих полей.

### DB-01. Спроектировать SQLite-хранилище

Статус: завершено 2026-08-10. Реализованы версионируемая SQLite-схема, WAL, foreign keys, индексы, транзакционный repository, audit events, импорт/экспорт и backup/restore в отдельную БД. Текущий JSON ещё не переключён и остаётся рабочим источником до отдельного подтверждения пользователя.

Цель: заменить рабочую перезапись общего JSON-файла транзакционным локальным хранилищем.

В объёме задачи:

- схема SQLite;
- foreign keys и индексы;
- WAL mode;
- миграции;
- repository-интерфейсы;
- транзакционные операции;
- audit events;
- импорт существующего JSON;
- экспорт памяти в переносимый JSON;
- резервное копирование и восстановление.

Точка решения пользователя: перед необратимой миграцией существующих данных создаётся проверенная резервная копия и запрашивается подтверждение.

Критерий готовности: данные переживают перезапуск, параллельные операции не теряют обновления, backup восстанавливается в тестовой БД.

### ID-01. Создать Identity Kernel

Статус: завершено 2026-08-10. Утверждён защищённый manifest `masha-0.1`, добавлены read-only Identity Kernel, два визуальных референса с SHA-256 и структурные регрессионные сценарии образа. Правила поддержки, «дружеских пинков» и включённой проактивности не определялись и не активировались.

Цель: сделать идентичность Маши независимой от LLM.

В объёме задачи:

- единый persona manifest вместо дублирования Python/JSON;
- загрузка конституции;
- versioning identity manifest;
- разделение постоянных черт, текущего контекста и будущего relationship state;
- запрет автоматического изменения защищённых identity-данных;
- набор регрессионных диалогов для проверки образа;
- manifest визуальной идентичности.

Не входит: определение границ эмоциональной поддержки и инициативности.

Точка решения пользователя: пользователь утверждает постоянные черты, примеры речи и канонические визуальные материалы.

Критерий готовности: identity context одинаково собирается для fake provider и любой будущей модели; защищённые файлы не изменяются моделью.

### LLM-01. Создать нейтральный интерфейс модели

Статус: завершено 2026-08-10. Реализованы нейтральные Pydantic-контракты, `ModelProvider`, детерминированный `FakeProvider` и `ModelRouter` с capability checks и privacy gate. Реальные модели, runtime и внешние API не подключались.

Цель: исключить привязку Companion Core к конкретному runtime или API.

В объёме задачи:

- `ModelProvider`;
- `ModelCapabilities`;
- `ModelRequest` и `ModelResponse`;
- fake provider;
- Model Router;
- обработка offline, timeout и недоступности провайдера;
- capability checks для structured output, tools и vision;
- правила передачи приватного контекста.

Не входит: скачивание больших моделей и подключение платных API.

Критерий готовности: Conversation Engine тестируется без настоящей LLM, а провайдер можно заменить конфигурацией.

### LLM-02. Выбрать локальный runtime и модели

Цель: подобрать основной и резервный локальные режимы под текущий компьютер.

Кандидаты для измерения, а не заранее утверждённый выбор:

- Qwen3.5 4B;
- Qwen3.5 9B;
- подходящая версия Gemma;
- дополнительный кандидат только при явной пользе.

Измерения:

- качество русского языка;
- сохранение образа;
- скорость первого токена и генерации;
- RAM/VRAM;
- structured output;
- tool calling;
- работа без интернета.

Точка решения пользователя: установка runtime и загрузка каждой крупной модели требуют подтверждения.

Критерий готовности: выбран основной локальный профиль, быстрый резервный профиль и рабочие пределы контекста на основании измерений.

### CHAT-01. Реализовать первый офлайн-разговор

Цель: получить минимальный сквозной сценарий общения.

Поток:

`User Input -> Conversation Engine -> Identity Context -> Model Provider -> Response -> Message History`

В объёме задачи:

- локальный CLI или минимальный API;
- conversation и message persistence;
- сбор identity context;
- потоковый либо обычный ответ;
- обработка перезапуска и недоступности модели;
- ограничение размера активного контекста.

Критерий готовности: после отключения интернета и перезапуска можно продолжить локальный разговор с сохранённой историей.

### MEM-03. Подключить управляемую долговременную память

Цель: сделать память полезной, объяснимой и контролируемой.

В объёме задачи:

- явная команда «запомни»;
- extraction memory candidates;
- подтверждение, изменение и отклонение кандидатов;
- provenance и confidence;
- deduplication;
- supersession с проверкой циклов;
- retrieval по проекту, статусу, времени и релевантности;
- указание использованных записей памяти;
- просмотр, архивирование и восстановление.

Точка решения пользователя: правила чувствительной памяти и автоматического подтверждения определяются отдельно до включения.

Критерий готовности: inference не становится trusted fact без предусмотренного правила, а пользователь может объяснить и отменить сохранение.

### TIME-01. Реализовать время и обязательства

Цель: обеспечить детерминированное понимание времени без предположений LLM.

В объёме задачи:

- Temporal Engine;
- UTC в хранении и `Europe/Moscow` в пользовательском представлении;
- current time, last interaction и elapsed time;
- commitments и deadlines;
- локальный scheduler;
- восстановление пропущенных событий после выключения;
- техническая поддержка quiet hours, cooldown и уровней инициативности.

Не входит: выбор значений quiet hours, правил поддержки и силы «дружеских пинков».

Точка решения пользователя: любое проактивное поведение остаётся выключенным до совместной настройки.

Критерий готовности: время и сроки корректны в тестах, напоминание переживает перезапуск, а LLM получает явный temporal context.

### UI-01. Создать локальное пространство MVP

Цель: объединить готовые возможности в понятном локальном интерфейсе.

Минимальные разделы:

- чат;
- проекты;
- память и кандидаты;
- обязательства;
- настройки;
- статусы offline/online и активной модели;
- канонический визуальный образ.

Не входит: обязательная генерация нового изображения на каждый ответ, сложная анимация и голос.

Точка решения пользователя: пользователь утверждает канонический портрет, выражения и визуальные ограничения.

Критерий готовности: основные сценарии доступны без терминала и работают локально.

### REL-01. Совместно определить границы взаимодействия

Цель: до реализации проактивной поддержки формально определить потребности пользователя.

Обсуждаются только совместно:

- допустимые ситуации для инициативы;
- уровни и формы «дружеского пинка»;
- признаки, когда нужно отступить;
- тихие часы и частота;
- поддержка в сложных состояниях;
- запрещённые формулировки и действия;
- способы временно отключить или изменить режим.

На этом этапе сначала создаётся согласованная спецификация. Реализация начинается только после утверждения пользователем.

Критерий готовности: пользователь явно подтвердил версию спецификации границ.

### MVP-01. Подготовить и проверить MVP 0.1

Цель: получить восстанавливаемую локальную версию для ежедневного пилота.

Проверки:

- полный запуск без интернета;
- установка и запуск по документации;
- восстановление после перезагрузки;
- backup/restore;
- повреждение или блокировка БД;
- отсутствие модели;
- переключение локальных профилей;
- сохранение identity context;
- отсутствие утечки приватного контекста во внешние адаптеры;
- управляемый расход диска, RAM и VRAM;
- экспорт пользовательских данных.

Критерий готовности: утверждённый набор MVP-сценариев проходит, критические риски отсутствуют, версия отмечена как `0.1`.

## 3. После MVP

Работы выполняются отдельными решениями и не входят автоматически в MVP:

1. Реализация согласованной проактивности и поддержки.
2. Локальные speech-to-text и text-to-speech.
3. Динамический визуальный образ и локальная генерация изображений.
4. Версионированные навыки с разрешениями.
5. Локальные интеграции и n8n.
6. Необязательные внешние low-cost API.
7. Tool Gateway и контролируемая агентность.
8. Доступ к выбранным папкам и приложениям по отдельным разрешениям.

## 4. Обязательные остановки для решения пользователя

Работа не продолжается автоматически, если требуется:

- изменить постоянные черты Маши;
- определить или изменить границы поддержки;
- включить инициативные обращения;
- выбрать форму «дружеских пинков»;
- скачать крупную модель или установить системный runtime;
- подключить внешний API;
- передать личные данные наружу;
- предоставить доступ к новой папке, приложению или устройству;
- выполнить необратимую миграцию или удаление;
- расширить агентные полномочия;
- существенно изменить согласованный MVP.

## 5. Следующая задача

`ID-03 — Identity Evolution Design` завершён как **design only**: определены
immutable approved manifests, explicit user approval, compatibility check памяти
и rollback contract. Никакой runtime-код, SQLite schema или manifest не менялись.

Рекомендуемая следующая задача — отдельная реализация versioned Identity
workflow только после утверждения schema/audit контракта; она не начинается
автоматически.

### MEM-10. Управляемая долгосрочная память

Статус: **DONE**

Добавлены local inspection, deterministic keyword search, project filtering,
retrieval trace, pending mutation proposals и подтверждённые edit/archive/
forget/supersession operations. Conversation history остаётся отдельным JSON
механизмом и обычный диалог не меняет SQLite memory.

### MEM-11. Temporal Engine

Статус: **DONE**

Deterministic Clock/TemporalContext, bounded model context, deadline parsing,
computed overdue status and explicit Commitment creation/completion are active.
No scheduler, reminders, proactive behaviour or event recovery is included.

### MEM-12.1. Temporal recovery and proactive decision foundation

Статус: **DONE**

Implemented only local deterministic recovery of overdue Commitment events,
stable event IDs, bounded temporal candidates, and a pure injected proactive
policy/decision engine. There is no scheduler, daemon, CLI, delivery, LLM
decision, external source, schema migration, or Memory/Commitment mutation.

### MEM-12.2. Proactive Interaction

Статус: **DONE**

An authorised reminder can be formulated locally through the active model
profile and stored as a delivered interaction. Explicit acknowledgement/dismiss
persists separately from Commitment state and prevents repeat delivery after
restart. No scheduler or autonomous external action exists.

### MEM-12.3. Persistent proactive policy and controlled local delivery

Статус: **DONE**

The separate local policy store and human-readable CLI control whether a manual
local delivery pass may formulate an already authorised overdue-Commitment
reminder. Policy, interaction state and execution model remain separate from
Identity and Memory. Check-in permission is deterministic at Level 2; delivery
is intentionally deferred pending its own event contract.

### MEM-12.5. Proactive Event Store

Статус: **DONE**

Persistent proactive events now have a separate SQLite lifecycle store. It is
not a Memory record and does not activate check-in detection or delivery.

### MEM-12.6. Deterministic check-in detection

Статус: **DONE**

Detection uses the read-only global latest history message as a stable absence
anchor. Only `absence > threshold` creates an idempotent CHECK_IN event; no
delivery or background execution is enabled.

### MEM-12.7. Check-in lifecycle and decision flow

Статус: **DONE**

Policy determines `SUPPRESS` or `CHECK_IN`; only an authorised event becomes a
candidate. No delivery, LLM call, scheduler or background runtime was added.

### MEM-12.8. Controlled proactive runtime

Статус: **DONE**

Dual-source interaction persistence, bounded local CHECK_IN formulation,
manual/background modes and a stoppable single-instance local daemon are
implemented without fallback or external delivery.

### MEM-12.9. Proactive runtime UX and safety boundaries

Статус: **DONE**

Human-readable status, pending interaction numbering and deterministic decision
history are implemented. Daemon stale-lock and cycle-failure recovery are
covered by regression tests. External events remain an explicit suppressed
boundary; model switching changes formulation execution only.

### LLM-03. Local Model Profiles

Статус: **DONE**

The local execution profile is persisted in `local-data/config/models.json`.
`primary` uses `qwen3.5:9b`; `fast` uses `qwen3.5:4b`; both use `think=false`.
Selection is manual via `model list`, `model current`, and `model use <profile>`.
Availability is checked before persistence and no automatic fallback exists.
Changing a profile changes only the LLM execution target; it does not mutate
Identity, SQLite memory, proposals/audit, conversation history/ID, or
TemporalContext.

### STAGE-13. Daily Runtime Hardening

Статус: **DONE**

One `DailyRuntime` now orchestrates Commitment reminders and CHECK_IN in a
single deterministic heartbeat. Reminder priority, one-contact-per-cycle and
waiting-for-user suppression protect attention without LLM discretion. Manual
and background execution share the same path. A bounded receipt journal,
read-only runtime health and `masha.ps1` human entry point are implemented.
SQLite schema, Identity, Memory and Commitment contracts were not changed.

### STAGE-14. Shared Continuity

Статус: **DONE**

Existing `RelationshipMemory` and `ContinuityState` records are now connected
to explicit proposals, confirmation, audit, bounded retrieval and a human-first
`continuity` CLI. Shared moments are kept separate from Facts and Episodes;
open threads remain separate from Commitments and proactive permission. No new
SQLite schema, second memory system, automatic extraction or model-owned
relationship state was introduced.

### STAGE-15. Masha Perspective & Honest Help

Статус: **DONE (15.1, bounded 15.2, 15.3)**

Explicit, evidence-linked `MashaReflection` generation is connected to the
existing MemoryCandidate/SQLite/audit contracts. Self-reflections with
sufficient confidence may be adopted as Masha's subjective perspective;
shared interpretations require Misha's explicit confirmation. Reconsideration
adds a linked immutable view instead of rewriting history. General conversation
does not automatically create or receive reflections. An optional Help Offer
can produce conversation-only help only after explicit acceptance. No tools,
background diary, affective inference, Identity mutation, proactive influence,
external API or model fallback was added.

### STAGE-16.1. Skill Contract & Registry

Статус: **DONE**

Strict local skill manifests, package discovery, risk declarations, whole-package
SHA-256 registration and restart integrity checks are implemented. Registry
state is local operating configuration and does not grant execution permission.
Entrypoints are never imported, modified packages are blocked, human CLI hides
technical hashes by default, and no Identity/Memory/SQLite/Temporal/LLM contract
was changed.

### STAGE-16.2. Action Autonomy Policy

Статус: **DONE**

Explicit standing grants by skill, capability, scope, risk and level are stored
in a separate local policy. The deterministic engine returns `ALLOW`,
`REQUIRE_CONFIRMATION` or `DENY`; exact grants avoid repeated questions inside
approved boundaries. Identity write remains denied, while Memory write,
destructive actions and external communication require confirmation. No tool,
LLM planner or agent loop is connected.

### STAGE-16.3. Bounded Agent Loop

Статус: **DONE**

Application-owned immutable plans now have step/time/input budgets, per-step
policy and package-integrity evaluation, explicit confirmation pauses,
receipt-before-execution, injected Fake Tool verification and restart-safe
idempotence. Interrupted execution is never automatically replayed. No real
filesystem/process/network tool, LLM planner or ConversationService integration
is connected.

### STAGE-16.4. First Local Read-only Skill

Статус: **NEXT — NOT IMPLEMENTED**

Implement one application-wired ProjectObserver Tool with an explicit resolved
workspace root, bounded read-only operations and deterministic evidence. Do not
load arbitrary manifest entrypoints, write files, execute processes or access
the network.
