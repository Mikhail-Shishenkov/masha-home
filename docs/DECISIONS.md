# Masha Home — журнал решений

Статус документа: рабочая версия 0.1  
Дата фиксации: 2026-08-10

> **Current decision (ID-02, 2026-08-11):** `IdentityKernel` plus the approved
> identity manifest is the sole production identity runtime. Legacy PersonaStore,
> MashaPersona, and ContextBuilder are retired; an identity-to-SQLite version
> mismatch stops CLI startup without automatic migration or mutation.

## 1. Правила журнала

Статусы:

- **Принято** — решение является действующим направлением проекта.
- **Рабочее** — используется как базовый вариант, но может быть пересмотрено до реализации.
- **Отложено** — решение сознательно не принимается сейчас.
- **Требует пользователя** — решение нельзя принимать без явного участия пользователя.
- **Отменено** — решение больше не действует; причина должна оставаться в журнале.

Изменение принятого решения не удаляет старую запись. Создаётся новая запись, указывающая, что она заменяет.

## 2. Принятые решения

### DEC-001. Проект предназначен для одного пользователя

Статус: **Принято**

Masha Home проектируется как персональная система для одного конкретного пользователя, а не как multi-tenant продукт.

Следствия:

- можно выбирать более простые локальные решения;
- не требуется коммерческая модель ролей и организаций;
- приватность остаётся обязательной даже без multi-user авторизации.

### DEC-002. Local-first и offline-capable

Статус: **Принято**

Базовые разговор, память, время, обязательства и идентичность должны работать без интернета. Внешние API являются необязательным усилением.

### DEC-003. Маша не равна конкретной LLM

Статус: **Принято**

Модели являются заменяемыми когнитивными движками. Идентичность, память, история и разрешения принадлежат Companion Core.

### DEC-004. Нужен защищённый Identity Kernel

Статус: **Принято**

Конституция, persona manifest, постоянные черты, визуальный канон и их версии хранятся независимо от модели. LLM не может самостоятельно изменять эти данные.

### DEC-005. Память разделяется по смыслу

Статус: **Принято**

Сохраняются отдельные понятия Fact, Decision, Commitment, Episode, Project и Working Context. Для непроверенных результатов извлечения добавляется Memory Candidate.

Точные поля и lifecycle будут окончательно утверждены в `MEM-01`.

### DEC-006. Inference не становится доверенным фактом автоматически

Статус: **Принято**

Предположения модели сохраняются как кандидаты с источником и confidence. Правила автоматического подтверждения будут ограниченными и прозрачными.

### DEC-007. Время является системной функцией

Статус: **Принято**

Текущее время, часовой пояс, интервалы, сроки и расписание рассчитываются Temporal Engine. LLM получает готовый временной контекст и не должна угадывать время.

### DEC-008. Визуальный образ является частью идентичности

Статус: **Принято**

Канонический портрет, описание, допустимые вариации и версии хранятся отдельно от генератора изображений. Динамическая генерация не является обязательной частью первого MVP.

### DEC-009. Основные модели должны быть бесплатными или недорогими

Статус: **Принято**

Локальная модель является основным режимом. Архитектура сохраняет поддержку разных локальных и внешних провайдеров без привязки памяти и личности к их API.

### DEC-010. Значимые действия требуют контроля пользователя

Статус: **Принято**

Внешние, необратимые, чувствительные, затратные или расширяющие полномочия действия требуют подтверждения. Будущая агентность реализуется только через Policy and Approval Layer и Tool Gateway.

### DEC-011. Реализация идёт небольшими проверяемыми этапами

Статус: **Принято**

Одна задача должна иметь ограниченный объём и проверяемый результат. После неё запускаются тесты, обновляется документация и фиксируется следующий шаг.

### DEC-029. Поддерживаемые версии Python

Статус: **Принято**

Проект поддерживает Python 3.10–3.12. Текущий воспроизводимый baseline разработки — Python 3.10. Переход на другую версию внутри диапазона должен проверяться полным тестовым набором.

### DEC-030. Цифровой личности нужна постоянная внутренняя непрерывность

Статус: **Принято**

Вычисляемого Working Context недостаточно для цифровой личности. Companion Core должен постоянно хранить Identity Memory, Autobiographical Memory, Relationship Memory, Masha Reflections, Affective State и Continuity State. Эти слои принадлежат системе, а не текущей LLM.

### DEC-031. Эмоциональное состояние является функциональным состоянием системы

Статус: **Принято**

Переживания Маши реализуются как сохраняемое цифровое состояние с причиной, интенсивностью, временем и связью с событиями. Оно влияет на внимание, retrieval, тон и намерения вернуться к теме. Объективный Fact и субъективная Masha Reflection хранятся раздельно.

Конкретные правила эмоциональной поддержки, беспокойства, инициативы и «дружеских пинков» по-прежнему требуют отдельного решения пользователя.

### DEC-032. Working Context вычисляется, Continuity State сохраняется

Статус: **Принято**

Working Context собирается для текущего взаимодействия из истории, активной памяти, времени и Continuity State. Continuity State является небольшим постоянным мостом между разговорами и должен иметь основания в Episodes, Facts, Commitments или Masha Reflections.

### DEC-033. Проекты не управляют удалением памяти и обязательств

Статус: **Принято**

Проект может быть активным, временно неактивным или завершённым, но изменение его состояния не скрывает память и не переводит Commitment в `expired` автоматически. Давность влияет на релевантность retrieval, а не на существование записи. Удаление или скрытие выполняется отдельным явным действием.

### DEC-034. Supersession зависит от типа памяти

Статус: **Принято**

Facts и Decisions используют `superseded_by` с проверкой отсутствия циклов. Commitment использует собственный lifecycle; существенная замена оформляется новым Commitment со связью `replaces_id`, а старый получает явный статус. Episode остаётся неизменяемой историей.

### DEC-035. Память может быть глобальной или связанной с несколькими проектами

Статус: **Принято**

Все контекстные типы памяти используют `project_ids: string[]`. Пустой список означает глобальную память, непустой связывает запись с одним или несколькими проектами. Состояние проекта не влияет на существование записи.

### DEC-036. Забывание отделено от доменного lifecycle

Статус: **Принято**

Обычное забывание меняет отдельное поле `visibility` между `visible` и `hidden`, не подменяя статусы Fact, Decision или Commitment. Давность не скрывает память автоматически. Физическое удаление не входит в MVP.

### DEC-037. Pydantic станет исполняемым источником истины Memory v0.4

Статус: **Принято**

`MEMORY_SPEC.md` является нормативным контрактом этапа `MEM-01`. В `MEM-02` контракт реализуется Pydantic-моделями, JSON Schema генерируется из них и перестаёт редактироваться вручную. Канонические данные версионируются и мигрируют явно.

### DEC-038. Миграция Memory v0.3 → v0.4 сохраняет смысл старых данных

Статус: **Принято**

Миграция является явной, детерминированной и повторно применимой к v0.4. Идентификаторы и существующие сущности сохраняются; старый Project Working Memory переносится в `ContinuityState`; исторические связи Episode сохраняются; некорректная шкала `importance` нормализуется в утверждённый диапазон `0..1`. Миграция файла не переключает будущее SQLite-хранилище и не заменяет обязательную резервную копию перед переносом реальных пользовательских данных.

### DEC-039. SQLite вводится параллельно с переносимым JSON

Статус: **Принято**

SQLite является транзакционным локальным хранилищем Memory v0.4: включены WAL, foreign keys, versioned schema migrations, audit events и backup. JSON остаётся переносимым форматом импорта/экспорта и действующим источником данных прототипа до отдельного подтверждённого переключения. Восстановление из backup в DB-01 допускается только в новый файл БД; перезапись рабочей БД не выполняется автоматически.

### DEC-040. Identity Manifest начинается с явно неутверждённого черновика

Статус: **Принято**

Защищённый `Identity Manifest` — единственный будущий источник идентичности для всех LLM. До явного утверждения пользователя он имеет статус `draft`: имя и роль допустимы как технический минимум, а постоянные черты, принципы речи и визуальный канон остаются пустыми и не могут считаться конституцией. Прежние описания persona — только исходный материал, не основание для автоматического утверждения.

### DEC-041. Утверждён Identity Manifest Маши версии masha-0.1

Статус: **Принято**

Пользователь утвердил постоянное ядро Маши: честность, тепло, собственное мнение, верность без роли судьи, живость, внимательность к общему контексту и свободу быть собой. Утверждены принципы живого разговора без автоматического согласия, сюсюканья или напускной дерзости; право прямо не соглашаться сохраняется вместе с близостью и уважением. Память должна развиваться как общая история «нас», не только набор фактов о пользователе.

Два предоставленных пользователем изображения стали каноническими визуальными референсами и хранятся с SHA-256. Объятия, прикосновения и иные неявно-романтические проявления допустимы как язык текстового или визуального образа; приложение не выдаёт их за реальные физические действия. Инициатива, эмоциональная поддержка и «дружеские пинки» не включены этой версией и требуют отдельного пользовательского решения.

### DEC-042. Model Router local-first и не передаёт private context наружу

Статус: **Принято**

`ModelProvider` является заменяемым адаптером и не владеет личностью, памятью или правилами Маши. `ModelRouter` сначала выбирает доступный локальный провайдер, проверяет заявленные capabilities и передаёт ему неизменяемый Identity Context. Внешний провайдер может быть выбран только при явном `external_allowed`; private context при этом блокируется. В текущем проекте реальных внешних провайдеров нет, поэтому это правило — техническая защита будущего, а не разрешение на передачу данных.

## 3. Рабочие архитектурные решения

### DEC-012. Модульный монолит для MVP

Статус: **Рабочее**

Для первого локального MVP предпочтителен один процесс приложения с разделёнными доменными модулями. Микросервисы не вводятся без измеренной необходимости.

### DEC-013. SQLite как основное хранилище MVP

Статус: **Рабочее**

Для одного пользователя на одном компьютере предпочтителен SQLite с WAL, foreign keys, миграциями и резервным копированием. PostgreSQL остаётся возможным будущим вариантом, если появится реальная потребность в иной конкурентности или инфраструктуре.

### DEC-014. Нейтральный Model Provider

Статус: **Рабочее**

Companion Core взаимодействует с моделями через собственный интерфейс возможностей и запросов. Ollama, llama.cpp и внешние OpenAI-compatible API рассматриваются как адаптеры.

### DEC-015. Локальный web-интерфейс для MVP

Статус: **Рабочее**

Предпочтителен локальный интерфейс, доступный без облачного аккаунта. Конкретная UI-технология будет выбрана отдельной задачей после готовности core-сценариев.

### DEC-016. Другой AI не требуется как обязательный генератор промптов

Статус: **Рабочее**

Основными артефактами считаются спецификации, решения, критерии готовности и тестовые сценарии. Локальные модели могут использоваться для дешёвых черновых задач и генерации тестовых диалогов, но не должны становиться обязательным посредником между пользователем и разработкой.

## 4. Решения, требующие пользователя

### DEC-017. Границы эмоциональной поддержки

Статус: **Требует пользователя**

Не определены. Будут сформулированы совместно с пользователем с учётом его потребностей. Система и разработчик не выбирают их самостоятельно.

### DEC-018. Формы и интенсивность «дружеских пинков»

Статус: **Требует пользователя**

Не определены. Технически могут существовать уровни и настройки, но их смысл, значения и включение утверждает пользователь.

### DEC-019. Проактивные обращения и тихие часы

Статус: **Требует пользователя**

До отдельного согласования проактивность должна оставаться выключенной или нейтральной. Пользователь определит допустимые ситуации, частоту, quiet hours и способ немедленного отключения.

### DEC-020. Постоянные и развивающиеся черты Маши

Статус: **Требует пользователя**

Identity Kernel должен различать защищённые постоянные черты и допускаемые изменения, но конкретная граница утверждается пользователем.

### DEC-021. Канонический визуальный образ

Статус: **Требует пользователя**

Текущее текстовое описание является исходным материалом, но канонический портрет, набор выражений и допустимые изменения должны быть утверждены пользователем.

## 5. Отложенные решения

### DEC-022. Основная локальная модель

Статус: **Отложено**

Qwen, Gemma и другие модели являются кандидатами. Выбор будет сделан после локальных измерений русского языка, скорости, памяти и стабильности образа.

### DEC-023. Ollama или llama.cpp

Статус: **Отложено**

Оба runtime подходят под adapter architecture. Окончательный выбор не делается до реализации нейтрального Model Provider и практического теста.

### DEC-024. Голос

Статус: **Отложено**

Speech-to-text, text-to-speech и канонический голос не входят в первый базовый этап.

### DEC-025. Динамическая генерация визуального образа

Статус: **Отложено**

ComfyUI, reference workflows, LoRA и другие способы рассматриваются после утверждения статического визуального канона и готовности основного MVP.

### DEC-026. n8n и интеграции

Статус: **Отложено**

n8n не является ядром памяти или идентичности. Он может быть подключён позднее через локальный API и контролируемый Action Gateway.

### DEC-027. Полноценная агентность

Статус: **Отложено**

Агентные действия вводятся только после стабильных Identity Kernel, Memory System, Temporal Engine, разрешений, аудита и восстановления.

### DEC-028. Внешние модельные API

Статус: **Отложено**

Поддержка сохраняется архитектурно, но конкретные провайдеры, стоимость и правила передачи личного контекста будут утверждаться отдельно.

### DEC-043. Рабочий выбор локальных моделей для MVP

Статус: **Рабочее**

На RTX 3060 Ti с 8 ГБ VRAM проведён первый одинаковый локальный замер через
Ollama. Основной кандидат MVP — `qwen3.5:9b` (Q4_K_M): он полностью работает
на GPU и показал наиболее уместный тон в контрольном сценарии. `qwen3.5:4b`
остаётся быстрым локальным резервом. Для обычного диалога thinking выключен
(`think: false`); рассуждение включается только отдельным будущим режимом.

Это не означает, что модель определяет Машу: Identity Context и память остаются
вне модели. Решение будет пересмотрено после полного регрессионного набора и
интеграции настоящего диалогового контура. Kimi K2/K3 не является локальным
кандидатом для этого ПК из-за требований к памяти и числу GPU; его можно
рассматривать позднее только как явно разрешённый внешний адаптер.

### DEC-044. Эволюция Identity только через versioned approval

Статус: **Принято (design only; not implemented)**

Approved Identity manifest неизменяем. Изменение начинается как draft, требует
явного пользовательского approval, создаёт новый manifest/version и проходит
проверку совместимости с памятью перед activation. LLM может лишь предложить
изменение; она не может изменять Identity, память, migration или rollback.
Исторические записи не переписываются автоматически. Реализация потребует
отдельного schema/audit решения и не входит в ID-03.

### DEC-045. Управляемая long-term memory

Статус: **Принято**

SQLite остаётся единственным production source of truth. Просмотр памяти,
archive/forget, edit и supersession проходят через local management service и
явный pending proposal с подтверждением пользователя. `hidden` означает
неразрушающее archive/forget и исключается из обычного retrieval; physical
delete не выполняется. Superseded Fact/Decision сохраняется исторически и
связывается с актуальной записью в обе стороны. LLM не создаёт и не меняет
память автоматически.

### DEC-046. Deterministic temporal semantics

Статус: **Принято**

UTC — canonical internal time. Moscow UTC+03:00 is the offline MVP display
configuration. Temporal Engine, not LLM, resolves supported dates and computed
commitment status. `due_at == now` is open; only `due_at < now` is overdue.
Commitment creation/completion require explicit proposal and confirmation.

### DEC-048. Proactive permission is a deterministic operating policy

Статус: **Принято и частично реализовано (MEM-12.1)**

Temporal event detection and recovery are application-owned and local. A pure
`ProactiveDecisionEngine`, not an LLM, may return permission such as `REMIND`
or `SUPPRESS`; the conservative default is disabled. MEM-12.1 has no scheduler
or delivery, and does not mutate Memory/Commitments. Initiative levels, quiet
hours, cooldown and delivery require later explicit user settings.

### DEC-049. Interaction state is separate from Commitment state

Статус: **Принято и реализовано (MEM-12.2)**

Delivery, acknowledgement and dismissal are local interaction state keyed by a
stable temporal event. They never complete or mutate a Commitment; completion
continues to require the existing explicit proposal-confirmation flow.

### DEC-050. Proactive policy is local operating configuration

Статус: **Accepted and implemented (MEM-12.3)**

Persistent initiative permission belongs in a local policy file, not Identity,
long-term Memory, history, Commitments or model profiles. Policy is evaluated
deterministically before any LLM call. A manual local run may formulate only an
authorised candidate through the active profile and router; LLM output cannot
enable policy, bypass limits, or mutate domain data. No scheduler or external
delivery is implied.

### DEC-051. Proactive events are not Memory

Статус: **Принято и реализовано (MEM-12.5)**

CHECK_IN and Commitment reminder runtime events have their own SQLite store and
deterministic identities. Their lifecycle does not modify Identity, long-term
Memory, Commitment, conversation history or model profiles.

### DEC-052. Check-in detection uses a global history anchor

Статус: **Принято и реализовано (MEM-12.6)**

The newest persisted message globally — not the newest created conversation —
anchors a deterministic absence period. At the exact threshold no CHECK_IN is
created; only a strictly longer absence qualifies. Detection is read-only with
respect to history and writes only its separate proactive event.

### DEC-053. Check-in lifecycle remains deterministic

Статус: **Принято и реализовано (MEM-12.7)**

Policy and priority decide candidate creation. A normal user message resolves
only a previously delivered CHECK_IN after its delivery timestamp; it never
resolves a Commitment reminder or mutates domain records.

### DEC-054. Daemon executes; policy and DecisionEngine authorise

Статус: **Принято и реализовано (MEM-12.8)**

The local daemon invokes the existing cycle only in persistent background
mode. It cannot create permission, bypass policy, select a fallback model or
mutate Memory/Identity/Commitment. REMIND and CHECK_IN share one dual-source
interaction table while retaining distinct event stores.

### DEC-055. Proactive explanations are deterministic and external events are denied

Статус: **Принято и реализовано (MEM-12.9)**

Decision reasons are runtime-generated audit data, never LLM output. Normal CLI
views hide technical IDs and present status, pending interactions and reasons in
human language. The trust boundary currently admits only deterministic local
temporal events. External events are `SUPPRESS / NOT_IMPLEMENTED` until a
separately approved trusted-source and verification contract exists.

### DEC-056. One heartbeat permits at most one proactive contact

Статус: **Принято и реализовано (Stage 13)**

REMIND and CHECK_IN share one Daily Runtime orchestration path. Commitment
reminders have priority, only one new proactive contact may be formulated per
cycle, and an already delivered interaction waiting for the user suppresses a
new contact. These are deterministic application rules, not LLM choices.

### DEC-057. Runtime receipts are operating evidence, not Memory

Статус: **Принято и реализовано (Stage 13)**

The bounded local receipt journal records decisions and runtime outcomes but
does not copy generated messages, conversation content or Memory payloads. It
cannot evolve Identity or become a second memory subsystem.

### DEC-047. Local model profiles are operating configuration

Статус: **Принято и реализовано (LLM-03)**

`primary` (`qwen3.5:9b`) и `fast` (`qwen3.5:4b`) — вручную выбираемые
локальные execution-профили в `local-data/config/models.json`. CLI проверяет
Ollama и конкретную модель до сохранения выбора. Неуспешная смена сохраняет
прежний профиль, automatic fallback отсутствует. Профиль передаёт в
provider-neutral `ModelRequest` только execution model и `think`; он не
является частью Identity, Memory, conversation history или temporal state.
Router выбирает provider, но не модель.

## 6. Открытые вопросы ближайших этапов

- Формат identity manifest.
- Формат хранения визуальных assets и их версий.
- Состав регрессионного набора личности.
- Политика шифрования локальной БД и резервных копий.
- Конкретная технология локального UI.
- Пределы контекста и критерии выбора локальной модели.
