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

### DEC-058. Shared history is confirmed relational meaning

Статус: **Принято и реализовано (Stage 14)**

`RelationshipMemory` хранит явно подтверждённое значение общей истории, а не
автоматический профиль Миши и не замену `Episode`. Исходный пользовательский
текст и provenance сохраняются; модель не может задним числом придумать вторую
точку зрения или превратить интерпретацию в общую правду.

### DEC-059. Continuity is a bridge, not a task or permission

Статус: **Принято и реализовано (Stage 14)**

`ContinuityState` содержит bounded открытые темы между разговорами. Изменение
проходит через существующий proposal/confirmation/audit flow. Открытая нить не
является `Commitment`, а её наличие не разрешает proactive contact. Повреждённые
legacy-фрагменты исключаются из обычного retrieval без изменения исходной БД.

### DEC-060. Masha Reflection is subjective, evidence-linked perspective

Статус: **Принято и реализовано (Stage 15.1)**

`MashaReflection` не является Fact о Мише, диагнозом, выполненным действием или
частью защищённой Identity. Она создаётся только явным reflection intent,
содержит bounded provenance и confidence и проходит deterministic validation и
deduplication. Достаточно уверенную self-reflection Маша может принять как свою;
shared reflection требует подтверждения Миши. Органичный мат не фильтруется как
ошибка сам по себе — живость не заменяется корпоративной стерильностью.

### DEC-061. Reconsideration appends history; general context does not absorb it

Статус: **Принято и реализовано частично (Stage 15.2)**

Пересмотр создаёт новую immutable reflection с `reconsiders_reflection_id`, не
переписывая прежнюю. Сохранённые рефлексии передаются модели только через
bounded perspective lens при явном вопросе о мнении Маши. Они не подмешиваются
автоматически в каждый общий ответ и не влияют на proactive policy.

### DEC-062. Honest Help is an accepted offer, not autonomous action

Статус: **Принято и реализовано (Stage 15.3)**

Help Offer принадлежит принятой рефлексии и ограничен помощью внутри разговора.
Только явное принятие пользователя разрешает одну локальную formulation через
active ModelProfile. LLM не может превратить offer в tool call, persistent
mutation или собственное разрешение действовать. Отклонение и доставка
идемпотентно фиксируются существующим audit, без новой storage subsystem.

### DEC-063. A skill declaration never grants execution permission

Статус: **Принято и реализовано (Stage 16.1)**

Skill manifest описывает procedure, requested capabilities, scopes, risk и
maximum autonomy ceiling, но не может включить себя, разрешить tool или изменить
policy. Registration означает только явное признание локального package Мишей.
Skill, Tool и Action Autonomy Policy остаются разными слоями.

### DEC-064. Registered skill packages are integrity-pinned and inert

Статус: **Принято и реализовано (Stage 16.1)**

Registry фиксирует SHA-256 всего пакета и после restart различает verified,
modified, missing и invalid. Discovery и registration не импортируют entrypoint
и не исполняют package code. Изменение пакета требует отдельного будущего
upgrade flow; оно не наследует прежнее доверие автоматически.

### DEC-065. Action autonomy is a standing deterministic boundary

Статус: **Принято и реализовано (Stage 16.2)**

Action autonomy хранится отдельно от proactive contact policy. `ALLOW` требует
verified package, manifest boundary, enabled master switch, global level и
точный grant по skill/capability/scope с достаточными risk/level limits.
Отсутствующий grant означает `REQUIRE_CONFIRMATION`, а не автоматический отказ.
LLM не создаёт request authority, grant или решение policy.

### DEC-066. Some capabilities cannot become silent standing permissions

Статус: **Принято и реализовано (Stage 16.2)**

Identity write всегда запрещён. Memory write сохраняет существующий explicit
confirmation flow. Destructive operations и external communication требуют
подтверждения на конкретное действие. Standing grant не может отменить эти
границы. Выключенная action policy является полным `DENY` для skill actions.

### DEC-067. Agent execution is receipt-first and re-evaluated per step

Статус: **Принято и реализовано (Stage 16.3)**

Каждый шаг проходит текущие registry integrity и Action Autonomy Policy заново.
До tool call сохраняется `executing` receipt. После restart такой шаг не
повторяется автоматически, потому что система не может доказать, успел ли tool
оказать эффект. Verified steps и terminal runs идемпотентны.

### DEC-068. A result exists only after deterministic verification

Статус: **Принято и реализовано (Stage 16.3)**

Успешный возврат Tool Adapter сам по себе не означает завершение. Отдельный
verification result обязан подтвердить evidence; failure, exception или
unverified result заканчивают run без claim `completed`. Receipts не сохраняют
raw inputs/outputs и не становятся Memory. LLM planner в loop отсутствует.

### DEC-069. A Tool Adapter is bound to one declared skill

Статус: **Принято и реализовано (Stage 16.4)**

Каждый application-injected Tool Adapter объявляет собственный `skill_id`.
Bounded Agent Loop отклоняет несовпадение между этим идентификатором и
`ActionRequest.skill_id` до вызова tool. Manifest остаётся декларацией и не
может подменить adapter через автоматический import entrypoint.

### DEC-070. Read results are verified but not persisted as agent history

Статус: **Принято и реализовано (Stage 16.4)**

ProjectObserver повторно получает тот же bounded read и сверяет точный output с
SHA-256 evidence. Только после этого результат передаётся вызывающему коду через
короткоживущий in-process канал. Содержимое файлов не сохраняется в AgentRunStore,
Memory или conversation history; receipt хранит только итог и verification code.

### DEC-071. Skill installation is a persistent preview and explicit confirmation

Статус: **Принято и реализовано (Stage 16.5)**

CLI и будущий UI используют один `SkillInstallerService`. Выбранная локальная
папка или ZIP сначала копируется в inert staging, валидируется и превращается в
человекочитаемый proposal. До отдельного подтверждения package destination и
Registry pin не меняются. Confirmation привязано к точному SHA-256 staged snapshot.
Подтверждённый package хранится в ignored `local-data/skills/`; bundled
`skills/` остаётся неизменяемым fallback и не загрязняется UI-установками.

### DEC-072. Upgrade never inherits standing permission

Статус: **Принято и реализовано (Stage 16.5)**

Upgrade требует более новую semantic version и совпадение текущего verified
package с preview. Перед активацией новой версии все grants этого skill
отзываются. Master switch и global autonomy level сохраняются, но новая версия
не получает прежнее или новое разрешение автоматически.

### DEC-073. Installing a package does not make arbitrary code executable

Статус: **Принято и реализовано (Stage 16.5)**

Installer не использует сеть и никогда не импортирует manifest entrypoint.
Package без заранее подключённого application-owned safe Tool Adapter можно
проверить и показать человеку, но нельзя подтвердить к установке. Поддержка
новых исполняемых skill-типов требует отдельного sandbox/declarative-runtime
решения, а не ослабления Registry.

### DEC-074. Emergency stop is a persistent higher-priority operating latch

Статус: **Принято и реализовано (Stage 16.6)**

`AutonomySafetyStore` хранится отдельно от Identity, Memory, conversation
history, commitments, model profiles и обеих autonomy policy. Включённый latch
перекрывает Action grants и Proactive Policy: Agent Loop не начинает следующий
tool-step, Daily Runtime не вызывает LLM, а proactive daemon завершает работу.
Это overlay, поэтому grants и настройки остаются видимыми, но неэффективными.

### DEC-075. Releasing emergency stop never resumes activity

Статус: **Принято и реализовано (Stage 16.6)**

`resume` снимает только safety latch. Он не включает policy, не восстанавливает
отозванные grants, не продолжает terminal AgentRun, не запускает daemon и не
доставляет ожидающее сообщение. Уже выполняющийся синхронный Tool Adapter нельзя
безопасно убить посередине вызова; граница остановки — до вызова и между шагами.

### DEC-076. Permissions UX is a derived view, not another authority

Статус: **Принято и реализовано (Stage 16.6)**

`PermissionControlService` агрегирует существующие Registry, policy, proposals
и receipts. Он вычисляет текущую эффективность grants с учётом safety latch и
целостности package, но не копирует permissions в новый store. CLI и будущий UI
должны использовать этот контракт; normal UX скрывает IDs, `--raw` сохраняет
технический UI/debug payload.

### DEC-047. Local model profiles are operating configuration

Статус: **Принято и реализовано (LLM-03)**

`primary` (`qwen3.5:9b`) и `fast` (`qwen3.5:4b`) — вручную выбираемые
локальные execution-профили в `local-data/config/models.json`. CLI проверяет
Ollama и конкретную модель до сохранения выбора. Неуспешная смена сохраняет
прежний профиль, automatic fallback отсутствует. Профиль передаёт в
provider-neutral `ModelRequest` только execution model и `think`; он не
является частью Identity, Memory, conversation history или temporal state.
Router выбирает provider, но не модель.

### DEC-077. The local UI is a thin client of an application boundary

Статус: **Принято и реализовано (UI-01)**

The future UI integrates through `MashaApplication`, not CLI handlers,
repositories or persistence files. The application layer may assemble services,
map UI commands, normalize errors and build presentation views, but it cannot
own or duplicate Identity, Memory, Temporal, proactive, model-routing or
permission semantics. UI-01 is in-process and adds no HTTP server.

### DEC-078. Model availability is checked before profile persistence

Статус: **Принято и реализовано (UI-01)**

`ModelSettingsService.use()` validates the requested profile, enabled state,
provider availability and exact local model before calling the existing
`ModelProfileStore` mutation. A rejected switch preserves the previous profile;
there is no fallback. Only the execution target changes.

### DEC-079. Visual identity paths and integrity stay behind the boundary

Статус: **Принято и реализовано (UI-01)**

The UI receives canonical asset identifiers, display metadata and resolved
bytes. `VisualIdentityResolver` alone reads manifest paths and validates the
approved SHA-256. The Identity manifest remains unchanged and is not a frontend
configuration file.

### DEC-080. Home is a composable Shared Room, not a dashboard

Статус: **Принято; semantic foundation реализован UI-03, target composition не реализована**

Masha is the persistent visual presence of one primary desktop space. Contextual
Conversation, Activity, Memory, Commitment, Proactive, Media, Permission and
other Surfaces transform around her according to direct intent and application
state. At most one Surface is primary; conversation and global safety control
remain reachable. This decision does not select a frontend framework or renderer.

### DEC-081. Presentation state is composable and has no domain authority

Статус: **Принято и реализовано в Presentation Runtime (UI-03)**

`MashaPresence` composes pose, expression, attention, activity, safety, ambient
and model availability instead of enumerating every combination. Emergency stop,
proactive off, model availability, runtime mode and daemon state remain
independent overlays. A deterministic reducer maps UI-safe application facts to
the scene; LLM text cannot select layout, animation, permission or safety state.

### DEC-082. Capabilities enter Home through declarative application-owned Surfaces

Статус: **Принято; generic Surface/Activity foundation реализован UI-03**

Future skills and runtimes may expose bounded UI-safe data through an
application-owned `InteractionSurface` / `ActivityPresentation` adapter. They
cannot inject arbitrary markup, scripts, renderer components or animation. An
unknown capability uses a safe generic Surface and receives no execution or UI
authority from presentation visibility.

### DEC-083. Presentation reduction is pure and compositional

Статус: **Принято и реализовано (UI-03)**

Immutable Home, Presence, overlay, Surface and Activity models are reduced only
from immutable presentation events. The reducer has no LLM, repository,
persistence, provider or renderer callback. Pose, expression, attention,
activity, ambient and operating overlays remain independent axes, preventing a
combinatorial global state machine.

### DEC-084. Tier 0 is a disposable renderer, not a frontend commitment

Статус: **Принято и реализовано (UI-03)**

The first interactive Shared Room uses a standard-library Tk adapter solely to
validate composition and deterministic state changes without GPU-specific
rendering or Ollama. It consumes the same Presentation Model expected by a
future renderer. Tk, its structural figure, placeholder palette and layout are
not the selected production framework, final appearance or visual identity.

### DEC-085. Home composition is presence-first and spatially adaptive

Статус: **Принято UI-04A и реализовано UI-04B**

The persistent room and Masha form the scene; contextual Surfaces appear around
the current shared-attention anchor. Conversation is recommended near/right of
Masha in the initial wide composition, but placement remains adaptive within a
closed allowed set. Ordinary Surfaces preserve a readable face and Presence
silhouette. A primary Surface is selected deterministically from explicit user
focus and application state, never from LLM output.

### DEC-086. Spatial intent is renderer-neutral and application-owned

Статус: **Принято UI-04A и реализовано UI-04B**

`SurfaceCompositionIntent` describes semantic anchor, preferred and
allowed positions, size class, priority, interaction mode, transform targets
and relation to Masha. A pure `CompositionResolver` produces a bounded
`CompositionPlan` under viewport, privacy and accessibility constraints. Skills,
models and capability runtimes cannot provide coordinates, markup, callbacks or
layout code.

### DEC-087. The first real Home should target layered Tier 1

Статус: **Рекомендация UI-04A, требует визуального согласования**

The preferred direction is a warm realistic/semi-realistic room with a restrained
cinematic near-future layer for Surfaces and operating truth. Layered/composited
2D provides canonical visual continuity, authored bounded transitions and a
low-cost static fallback. Tier 2 rich/GPU rendering remains optional and must
consume the same Presentation Model and composition contract.

### DEC-088. Composition hysteresis is explicit and pure

Статус: **Принято и реализовано (UI-04B)**

`CompositionResolver` owns no mutable layout history. A caller may supply the
previous immutable `CompositionPlan`; a continuing Surface retains its previous
placement only when it remains allowed under the same variant, viewport and
privacy constraints. Spatial stability signatures exclude conversational text,
Activity progress and expression changes. Privacy, safety and viewport changes
remain explicit deterministic overrides.

### DEC-089. Composition variants share one contract and resolver

Статус: **Принято и реализовано (UI-04B)**

Presence-first, conversation-first and adaptive-cinematic are bounded semantic
policies producing the same `CompositionPlan` type. They are not separate
frontends and cannot change Identity, authority, Surface lifecycle or domain
state. Visual comparison and final default selection remain a user decision.

### DEC-090. Scene motion has deterministic hysteresis and one visible identity

Статус: **Принято и реализовано (UI-06F)**

Presentation events select opaque scene IDs, but the renderer owns a bounded
settle delay and minimum hold time. A scene change exits the current frame before
revealing the next; two Masha frames must never be visible simultaneously.
Conversation content does not resize the primary surface or select a scene.
Reduced-motion remains an explicit deterministic policy.

### DEC-091. Capability grammar is accepted before production binding

Статус: **Принято; visual review passed and Slice A implemented (UI-06F)**

Every new capability moment is first reviewed as an offline disposable scene
through `appeared → focused → waiting → resolved|dismissed`. Only after user
acceptance may a separate UI-safe application projection and allowlisted action
be introduced. The workshop itself cannot access backend state or claim a domain
mutation.

### DEC-092. Capability objects are contextual, not permanent navigation

Статус: **Принято и реализовано для Slice A (UI-06F)**

Activity and Proactive Presence appear in the Home only when a real application
object exists. Empty capability categories do not become dashboard navigation.
Agent receipts are read-only until a real general action contract exists.
Reminder/Check-in exposes only the already-supported acknowledge/dismiss
lifecycle and never performs Memory or Commitment mutation.

### DEC-093. Continuity facts and Masha reflections stay visibly distinct

Статус: **Принято и реализовано в UI-06G**

Confirmed Memory and Shared Continuity are presented as read-only shared
history. A Masha reflection remains a fallible evidence-linked interpretation
and is never displayed as a Fact. It becomes adopted only after Misha's explicit
decision.

Honest Help is likewise an explicit offer. Dismissal has no model call;
acceptance delegates to the existing Stage 15 service and selected local model.
The renderer cannot infer, adopt or execute either capability and Emergency Stop
blocks their actions.

### DEC-094. Operating controls appear as one contextual workbench

Статус: **Принято и реализовано в UI-06H**

Skills, grants, Agent Runs and local model profiles must not become permanent
dashboard navigation. The Home presents them through one bounded `Режим` object
when Misha chooses to inspect operating state. Agent receipts retain their own
`Работа` surface.

Manual model selection is a local operating preference, not agent execution;
it remains available during Emergency Stop. The existing deterministic
availability check and no-fallback contract are retained. Installation, grants
and policy mutations require a separate explicit confirmation UX and are not
added to this slice.

## 6. Открытые вопросы ближайших этапов

- Формат identity manifest.
- Формат хранения визуальных assets и их версий.
- Состав регрессионного набора личности.
- Политика шифрования локальной БД и резервных копий.
- Конкретная технология локального UI.
- Пределы контекста и критерии выбора локальной модели.
