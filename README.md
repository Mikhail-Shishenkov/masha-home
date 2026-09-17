# Masha Home

Masha Home — local-first персональная AI-система для одного пользователя и цифровой Дом Маши.

Главный архитектурный принцип проекта: **Masha != LLM**. Языковая модель является заменяемым когнитивным и языковым движком. Identity, долговременная память, история, время, разрешения, выбранные реальные объекты, состояние операций и факт выполнения принадлежат приложению.

Обычный диалог проходит через один application-owned контур. Семантическая модель может предложить смысл реплики и evidence, но не получает authority. Любое действие с последствиями проходит через доменный proposal / policy / confirmation / operation / receipt lifecycle. Фраза модели никогда не является подтверждением выполненного действия.

## Текущее состояние разработки

Активная ветка `new/agent-coherence-continuation` содержит незавершённый checkpoint по coherent dialogue / meaning-first semantic resolution.

В checkpoint уже собраны единый bounded conversational context, application-owned result/entity continuity и meaning-first путь: сначала определяется speech act без capability IDs, затем действие сопоставляется только с совместимыми application-owned capability specifications.

Этот checkpoint **не является релизом и не принят для merge в `main`**. Открыты как минимум relative-time field extraction, полные многоходовые dialogue journeys и живая conversational acceptance. Зелёные deterministic tests сами по себе не означают, что естественный язык принят.

## Source of Truth

Читать текущую систему в таком порядке:

1. [Конституция](CONSTITUTION.md) — продуктовые и человеческие принципы.
2. [Current State](docs/CURRENT_STATE.md) — фактический implementation/release status на сегодня.
3. [Архитектурный канон](docs/MASHA_HOME_CANON.md) — стабильная модель Дома и архитектурные границы.
4. [Журнал решений](docs/DECISIONS.md) — принятые и superseding решения.
5. [Memory contract](docs/MEMORY_SPEC.md) — нормативная модель долговременной памяти.
6. [Dialogue / Action lifecycle](docs/DIALOGUE_ACTION_LIFECYCLE.md) — разделение meaning, proposal, confirmation, operation и receipt.
7. [Agent Coherence Plan](docs/AGENT_COHERENCE_PLAN.md) — active continuation capsule незавершённой рабочей ветки.
8. [Карта документации](docs/README.md) — где лежат остальные контракты и исторические материалы.

Текущий код, `CURRENT_STATE.md` и подтверждённые checkpoint-ы имеют приоритет над историческими roadmap/snapshot документами.
