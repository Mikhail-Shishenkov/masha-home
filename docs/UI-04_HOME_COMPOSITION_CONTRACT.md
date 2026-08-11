# UI-04A — Home Composition / Interaction Surface Contract

Статус: **UI-04A DESIGN COMPLETE / UI-04B FOUNDATION IMPLEMENTED**

Дата: **2026-08-11**

## 1. Design goals

Masha Home — одно живое пространство, а не набор экранов продукта. Главный
визуальный anchor пространства — Маша. Комната сохраняет узнаваемость, а
функциональные области появляются рядом с ней, меняют масштаб и положение и
уходят обратно в ambient-состояние.

Контракт должен обеспечить:

- присутствие Маши до, во время и после выполнения функций;
- одну понятную композицию из независимых presentation-состояний;
- детерминированное размещение Surface без решений LLM;
- расширение voice, media, skills, Agent Runs и devices без нового layout engine;
- различимость safety, proactive, model и runtime состояний без dashboard;
- privacy и graceful degradation как свойства композиции;
- одинаковую семантику для Tier 1 и будущего Tier 2 renderer.

Главный ответ UI-04A:

> Комната не переключается между страницами. Она сохраняет Машу и узнаваемое
> окружение, выбирает один текущий центр совместного внимания и собирает вокруг
> него не более одной primary и нескольких bounded supporting Surfaces.

## 2. Non-goals

UI-04A не:

- выбирает frontend framework или production renderer;
- реализует layout engine, CSS/canvas, анимации или новые visual assets;
- оптимизирует будущий Home под текущую Tk-композицию;
- меняет Presentation Reducer, UI-01 или domain contracts;
- даёт LLM право выбирать expression, pose, layout, animation или overlay;
- добавляет voice, media, scheduler, external events или autonomous capability;
- определяет новую Identity, Memory, Commitment, Safety или permission semantics;
- делает room state источником истины для domain state.

### 2.1 UI-04B implementation record

`backend.presentation.composition` implements the renderer-neutral foundation:

- immutable `ViewportCharacteristics`, `MashaComposition`,
  `CompositionRegion`, `CompositionOverlay` and `CompositionPlan`;
- `SurfaceCompositionIntent` and closed spatial/priority/interaction/occlusion
  vocabularies on `InteractionSurface`;
- pure deterministic `CompositionResolver`;
- three variants of the same resolver: `presence_first`,
  `conversation_first` and `adaptive_cinematic`;
- semantic responsive recipes for wide, standard, narrow and very narrow;
- bounded surface capacity, lifecycle-aware terminal Activity traces, decision
  priority, proactive suppression, safety and privacy priority;
- explicit `previous_plan` hysteresis with no hidden mutable state;
- stable `cmp1_...` layout signature that ignores text, progress and expression
  changes when the spatial topology is unchanged.

The implementation imports no application/domain repository, provider, LLM,
frontend or persistence code. It returns no coordinates or executable payloads.

## 3. Home spatial model

### 3.1 Пространственные слои

Home состоит из пяти независимых слоёв, расположенных не как панели, а как
единая сцена:

1. **Room layer** — постоянная геометрия и узнаваемые предметы комнаты.
2. **Presence layer** — Маша, её поза, выражение, внимание и локальная зона
   свободного пространства.
3. **Surface layer** — динамические функциональные объекты вокруг общего фокуса.
4. **Ambient layer** — свет, глубина, спокойное движение и локальные признаки
   времени/работы, не требующие ответа.
5. **Overlay layer** — privacy, safety и недоступность, которые не перестраивают
   domain state и не притворяются отдельными экранами.

Порядок задаёт смысл и приоритет, а не конкретный z-index renderer.

### 3.2 Базовая композиция

Для широкого desktop-окна рекомендуется асимметричная presence-first сцена:

- Маша занимает центральную область с небольшим смещением влево от геометрического
  центра;
- справа от неё остаётся основное свободное поле для Conversation и совместного
  просмотра;
- ближняя нижняя область принимает компактные решения и Activity;
- дальние края комнаты используются только для ambient и свернутых Surfaces;
- лицо, взгляд и верхняя часть силуэта Маши остаются визуально читаемыми.

Это recommendation, а не зафиксированная координата. На узком окне Presence
переходит выше primary Surface, а не уменьшается до боковой avatar-card.

### 3.3 Постоянные элементы

- узнаваемая геометрия комнаты;
- Visual Identity Маши;
- доступный, но визуально спокойный путь домой/к разговору;
- доступный emergency stop affordance;
- минимальная operating truth, когда она действительно отклонена от нормы.

Постоянный элемент не обязан быть постоянно подписанной кнопкой. Он может быть
семантически доступным объектом комнаты с keyboard/screen-reader эквивалентом.

### 3.4 Динамические элементы

- Conversation, Activity, Confirmation, Proactive и capability Surfaces;
- расширенная model/runtime информация;
- контролы конкретного действия;
- media и результат работы;
- локальные переходные акценты внимания.

Динамический элемент появляется только из application-owned presentation event
и уходит по lifecycle. Его исчезновение не удаляет domain data.

### 3.5 Ambient-элементы

Ambient показывает присутствие без требования ответа: состояние света, спокойную
позу, направление внимания, след фоновой Activity и разрешённый time-of-day cue.
Ambient не содержит личные тексты, срочные цвета или ложные признаки работы.

### 3.6 Idle

В отсутствие активного взаимодействия Home возвращается к комнате, Маше и
минимальному operating truth. Conversation может оставаться доступной, но не
обязана быть открытой панелью. Завершённые Surfaces сворачиваются или закрываются
по presentation policy; это не меняет историю или память.

## 4. Presence-first composition

### 4.1 Центр присутствия и центр внимания

`presence anchor` — Маша. `attention anchor` — пользователь, Surface или ambient
область, на которую направлено её внимание. Эти anchors могут различаться:
Маша остаётся на месте, пока её внимание переводит пользователя к Activity.

### 4.2 Adaptive placement recipes

| Ситуация | Композиция | Attention |
|---|---|---|
| Idle | Маша и комната, функциональный UI почти отсутствует | ambient / user при focus |
| Conversation | Surface появляется преимущественно справа или рядом с Машей | user при вводе, Surface при общем просмотре |
| Activity | Activity разворачивается рядом с рабочей зоной Маши; Conversation остаётся доступной компактно | Surface |
| Confirmation | Небольшой decision Surface занимает ближний foreground рядом с источником решения | decision Surface |
| Proactive | Сначала меняются attention/pose Маши, затем появляется компактный Surface | user → proactive Surface |
| Settings | Маша остаётся видимой, Surface уходит к периферии и не изображает личностное состояние | Surface / ambient |
| Immersive media | Контент может занять пространство только по явному выбору пользователя | Surface; Presence compact, но доступна |
| Safety stop | Автономное движение/Activity визуально останавливается, Маша и chat остаются | user / interrupted |

Conversation имеет предпочтение справа от Маши для первой широкой композиции,
но placement resolver вправе выбрать другую разрешённую позицию из-за размера,
активного Activity, handedness/accessibility preference или occlusion budget.

### 4.3 Occlusion budget

Обычная Surface не закрывает лицо Маши и не превращает её в фон карточки.
Supporting Surfaces могут частично окружать Presence, но не занимают её primary
silhouette zone. Полное или почти полное перекрытие допустимо только при:

- явном выборе immersive media/task режима;
- privacy masking;
- критическом renderer failure, когда остаётся semantic fallback.

Даже тогда остаётся доступный путь к Conversation и safety control.

### 4.4 Переключение функциональной зоны

Прямой выбор пользователя меняет primary Surface. Предыдущая Surface становится
supporting, background, minimized или closed согласно её lifecycle; она не
копируется во второй экран. Маша переводит attention к новому общему фокусу, но
Visual Identity и базовое присутствие не заменяются.

## 5. Surface model

`InteractionSurface` has identity, kind, lifecycle, role, title, summary,
sensitivity, capabilities, optional Activity relation and an optional bounded
`SurfaceCompositionIntent`:

```text
InteractionSurface
  surface_id
  kind / semantic role
  lifecycle
  content projection
  capabilities
  composition_intent

SurfaceCompositionIntent
  anchor                  presence | room | viewport | surface:<opaque-id>
  preferred_position      near_right | near_left | lower | foreground | peripheral
  allowed_positions       closed bounded set
  size_class              whisper | compact | standard | expanded | immersive
  priority                ambient | supporting | primary | decision | safety
  interaction_mode        passive | inspect | input | decision | direct | mixed
  expandable              boolean
  collapsible             boolean
  transform_targets       closed set of semantic Surface kinds
  presence_relation       beside | shared_attention | surrounding | background | compact_presence
```

Это renderer-neutral intention, не пиксельные координаты. Renderer получает
детерминированный `CompositionPlan`, соответствующий viewport и accessibility
constraints. Surface не передаёт CSS, HTML, callbacks или произвольную разметку.

### 5.1 Общие правила

- в композиции не более одной primary Surface;
- decision Surface имеет приоритет в рамках только своего действия;
- safety overlay выше Surface, но не закрывает conversation без причины;
- supporting Surface не вытесняет primary по собственной инициативе;
- passive proactive event не крадёт focus;
- unknown kind использует application-owned generic renderer;
- transform создаёт новый семантический вариант через reducer event, а не
  мутирует renderer component;
- layout выбирается из authored recipes, а не генерируется моделью.

### 5.2 Примеры

| Surface | Обычный intent | Возможная трансформация |
|---|---|---|
| Conversation | `presence / near_right / standard / primary` | compact при Activity, expanded по выбору |
| Activity | `presence / lower или near_right / standard / supporting` | primary detail, compact progress trace |
| Confirmation | `source Surface / foreground / compact / decision` | resolved → closed, details → standard |
| Proactive | `presence / near_right / whisper / supporting` | acknowledged → closed, inspect → related Surface |
| Settings | `room / peripheral / standard / primary` | compact operating control |
| Skill | `source Activity / near_right / standard / supporting` | Activity detail, permission decision |
| AgentRun | `presence / surrounding / expanded / primary` | compact Activity trace |
| Memory | `presence / near_right / standard / primary` | confirmation for mutation proposal |
| Commitment | `presence / near_right / standard / primary` | completion confirmation |

Memory/Commitment Surface отображает UI-safe projection. Видимость никогда не
даёт права на mutation.

## 6. Composition state model

Home не имеет гигантского enum. Исходная сцена компонуется из независимых осей:

```text
presence      VisualIdentity + pose + expression + presence activity
attention     user | surface | ambient | proactive | interrupted
engagement    idle | conversation | decision | inspect | immersive
activity      none | queued | running | waiting | terminal
proactive     off | quiet | candidate | presented
safety        normal | proactive_disabled | autonomy_stopped
model         available | switching | unavailable
runtime       manual | background + daemon state
ambient       active | quiet | privacy | low_power
window        focused | unfocused | minimized | locked
```

UI-03 implements the presentation axes. UI-04B implements spatial intent and
composition planning. `engagement` as a separate stored axis and window
lifecycle beyond focus remain design-only because current state can be resolved
without inventing them.

### 6.1 Deterministic composition resolver

Будущий pure resolver применяет приоритеты:

1. privacy/accessibility constraints;
2. emergency/safety truth;
3. обязательное explicit decision пользователя;
4. выбранная пользователем primary Surface;
5. активная observable Activity;
6. разрешённая proactive presentation;
7. ambient scene.

Он возвращает `CompositionPlan`: Presence slot, primary slot, bounded supporting
slots, overlay slots, focus target и fallback plan. Строка ответа LLM не является
входом resolver.

Пример:

```text
presence=present
attention=surface
engagement=conversation
activity=running
proactive=quiet
safety=normal
model=primary_available
runtime=background
window=focused

→ Masha centre-left, Conversation primary near-right,
  Activity compact lower, calm background-runtime ambient cue.
```

## 7. Overlay model

Overlay сообщает поперечную operating truth и не становится новой страницей:

| Overlay | Пространственное проявление | Не означает |
|---|---|---|
| Proactive off | исчезает инициативный жест; спокойный локальный control state | emergency stop |
| Autonomy stopped | остановленное autonomous движение, ясная safety boundary и release affordance | Masha unavailable |
| Model unavailable | речь/мышление недоступны, Presence и deterministic Home сохраняются | Identity lost |
| Runtime unavailable | Activity/runtime cue degraded рядом с источником | model unavailable |
| Degraded presentation | упрощённые assets/motion, semantic UI сохранён | domain failure |
| Privacy | sensitive content masked, Presence generic/quiet | data deleted |

Overlay не должен использовать только badge. Он сочетает bounded изменение
пространства, движение/неподвижность, доступный текст и icon/shape cue. Цвет
никогда не является единственным носителем значения.

## 8. Masha visual state mapping

LLM не выбирает expression. Deterministic presentation event и одобренная
application cue выбирают визуальное намерение из закрытого словаря.

| State | Visual intention | Allowed presentation |
|---|---|---|
| neutral | спокойно присутствует | idle pose, мягкое дыхание/static fallback |
| warm | открытость и близость | мягкий взгляд/улыбка без обязательной похвалы |
| attentive | слушает Мишу | взгляд к user, собранная поза |
| thinking | работает над ответом | взгляд кратко в сторону/к Surface, bounded loop |
| skeptical | не согласна или проверяет | сдержанная мимика; только trusted semantic cue |
| slightly_annoyed | живая реакция без унижения | короткий authored cue; не для system error |
| concerned | есть подтверждённая причина обратить внимание | спокойная серьёзность; отсутствие не является причиной |
| amused | общая шутка/лёгкость | короткая улыбка или authored motion |
| happy | подтверждённо хорошее событие | более открытая поза, bounded positive cue |
| tired | тихий режим/явно заданный character cue | reduced activity; не симуляция resource failure |
| surprised | неожиданное подтверждённое событие | короткий transition с возвратом к базе |

Текущий UI-03 может безопасно использовать только state-based subset. Богатые
реакции требуют отдельного trusted semantic cue contract; анализ сырого текста
в renderer запрещён.

## 9. Proactive visual language

Инициатива начинается с Маши, а не с notification card:

1. разрешённый backend candidate меняет её attention/pose;
2. Home даёт короткий non-blocking spatial cue;
3. при необходимости появляется compact/whisper Surface;
4. acknowledgement/dismissal завершает presentation lifecycle.

Различия:

- **Level 0 / рядом и ждёт:** ambient Presence, никаких вызовов внимания;
- **Reminder:** взгляд к связанному Commitment object и компактный time/task cue;
- **Check-in:** взгляд к пользователю и открытый мягкий Surface без тревожной
  семантики или диагноза;
- **Autonomous Activity:** working pose плюс Activity Surface с фактическим
  состоянием и progress;
- **Blocked autonomy:** interrupted/still Presence и причина у Activity, без
  имитации продолжения;
- **Emergency stop:** очевидная safety boundary, отсутствие autonomous motion,
  сохранённые chat и Presence.

Уровни 3–4 зарезервированы до появления утверждённой backend semantics. Level 5
не реализован. Визуальная интенсивность не повышает разрешения policy.

## 10. Safety visual language

- `proactive off`: тихое состояние — Маша отвечает, но сама не начинает контакт;
- `autonomy stopped`: чёткая остановка agent/proactive activity и постоянный
  доступный release control;
- `model unavailable`: Маша визуально остаётся собой; разговор сообщает, что
  локальный исполнитель сейчас недоступен;
- `runtime unavailable`: связанный Activity/daemon cue показывает остановку;
- `degraded presentation`: Home упрощает motion/layers, но не выглядит сломанным.

Emergency stop не окрашивает всю комнату красным. Предпочтительны остановка
автономного движения, локальная граница/контур, короткое человеческое объяснение
и доступный safety affordance. Normal chat не блокируется.

## 11. Privacy behavior

| Environment | Поведение |
|---|---|
| Focused | полный разрешённый Home по текущей privacy preference |
| Unfocused | sensitive Surface content маскируется, nonessential motion pauses, generic Presence остаётся |
| Minimized | rich rendering прекращается; наружу не уходит private preview |
| Screen locked | только нейтральный privacy-safe фон/Presence или ничего; никакого личного текста |
| Explicit privacy mode | скрывает content независимо от просьбы отдельной Surface |

При privacy masking могут оставаться: силуэт/нейтральный approved asset, local-only
индикатор безопасности и общий факт работы без названия задачи.

Никогда не показываются: conversation text, Memory/Commitment details, media
preview, filenames/paths, proposal payload, audit details, prompt/context, UUID,
external notification content и личные факты.

OS lock/minimize integration пока не реализуется. Контракт требует отдельных
presentation events, а не чтения OS state из domain layer.

## 12. Avatar / visual identity contract

Будущий canonical visual pack должен быть версионированным и проверяемым:

```text
VisualIdentityPack
  identity_id
  version
  lineage / approved predecessor
  canonical_appearance_asset_id
  pose_set
  expression_set
  clothing_variants
  scene_lighting_variants
  idle_sequences
  interaction_sequences
  compatibility_tier
  integrity metadata behind application boundary
```

Все runtime references — opaque asset IDs. Filesystem path и hash остаются за
`VisualIdentityResolver`. Новая одежда, освещение или pose не создаёт новую
личность и не может менять Identity manifest без отдельного approval flow.

Selection детерминирован:

```text
approved visual identity
+ semantic pose/expression/activity
+ room lighting state
+ user presentation preference
+ renderer capability
→ bounded authored asset/transition
```

Никакой frame, pose или промежуточное лицо не генерируется LLM на лету.
Animation использует authored transition graph, duration bounds, interruptible
safe states и static fallback.

## 13. Visual direction

| Направление | Плюсы | Минусы/риски | GPU/animation | Соответствие Home |
|---|---|---|---|---|
| Warm realistic room | близость, бытовая правдоподобность, сильное ощущение дома | uncanny valley, сложнее согласовать свет и asset continuity | layered 2D умеренно; full 3D дорого | высокое, если сохранить живость, а не photoreal perfection |
| Cinematic near-future | подчёркивает digital nature, удобно визуализирует состояния | легко стать холодным sci-fi dashboard | эффекты могут требовать GPU; motion проще стилизовать | среднее без тёплой бытовой основы |
| Hybrid | узнаваемая тёплая комната плюс сдержанный световой/пространственный digital layer | требует строгой меры и единой art direction | Tier 1 умеренный; эффекты деградируют отдельно | **лучшее соответствие концепции** |

Рекомендация: **hybrid** — реалистичная или полуреалистичная тёплая комната и
лёгкий cinematic near-future слой только для surfaces, operating truth и
переходов. Digital layer не должен превращаться в голографический dashboard.

## 14. Tier strategy

### Tier 0 — semantic placeholder

Полезен для reducer tests, fallback и быстрой проверки новых событий. Текущая Tk
визуальная композиция disposable и не является основой art direction.

### Tier 1 — layered 2D / composited assets

Рекомендуется для первого настоящего UI. Он даёт canonical внешность, authored
poses/expressions, room layers и детерминированные transitions при умеренной
нагрузке и хорошем static/reduced-motion fallback.

### Tier 2 — richer GPU renderer

Может добавить depth, richer animation и свет после проверки Tier 1. Он не
должен менять Presentation Model, Surface contract или authority boundaries.

Рекомендация не фиксирует renderer: начать настоящий UI с Tier 1, сохранив Tier
0 как semantic fallback. Tier 2 оправдан только после замеров железа и проверки,
что richer motion действительно усиливает присутствие.

## 15. Tier 0 audit

### 15.1 Оставить как semantic architecture

- `HomePresentationModel` и независимые Presence/overlay axes;
- immutable presentation events и pure reducer;
- `InteractionSurface` identity/lifecycle/role/capabilities;
- `ActivityPresentation` и честный progress lifecycle;
- opaque Visual Identity asset IDs;
- privacy masking и независимые safety/model/proactive/runtime states;
- no-LLM сценарии и deterministic tests;
- renderer как заменяемый consumer Presentation Model.

### 15.2 Убрать из визуальной метафоры

- постоянный status header;
- постоянно открытую левую conversation panel;
- Машу как отдельную avatar-card справа;
- постоянную activity panel снизу;
- ряд status badges как главный способ понять систему;
- test buttons/click zones как основу взаимодействия.

### 15.3 Перестроить

- сделать комнату и Машу базовым кадром, а не фоном dashboard;
- Conversation по умолчанию проявлять справа/рядом с Машей и адаптировать по
  контексту, а не просто поменять левую и правую колонки;
- Activity привязывать к общему рабочему фокусу и уметь сворачивать в trace;
- Confirmation связывать с исходной Surface, а не показывать generic modal;
- proactive начинать с Presence cue;
- operating state переводить в независимые overlays и ambient cues;
- добавить renderer-neutral spatial intent и pure Composition Resolver.

### 15.4 Считать disposable

- Tk layout, Canvas geometry, palette, typography и gradient;
- абстрактную фигуру Маши;
- текущие размеры/стороны панелей;
- клавиши `1..6` и prototype scenario controls;
- число Canvas objects и любые pixel coordinates.

## 16. Future capability compatibility

Каждая будущая capability проходит один путь:

```text
Capability runtime
→ existing authority / permissions / safety
→ UI-safe application projection
→ Presentation event
→ InteractionSurface + optional ActivityPresentation
→ Composition Resolver
→ renderer
```

- voice меняет Presence activity и создаёт bounded Voice/Conversation Surface;
- photos/image generation входят как Media Surface и observable Activity;
- skills не поставляют frontend, только UI-safe descriptor/result;
- Agent Runs и long operations используют Activity lifecycle;
- waiting for external result отображается как `waiting`, а не fake progress;
- confirmations используют Decision Surface, не новый modal framework;
- devices требуют существующие permission/confirmation/receipt boundaries;
- external events сначала проходят будущий trusted External Event Boundary;
- notifications и scheduled activity не получают право обойти proactive policy.

Новая capability может потребовать application projection и renderer для нового
закрытого Surface kind, но не новый layout engine.

## 17. Open decisions

Архитектура следующего шага не заблокирована. Для visual prototype потребуется
решение Миши по четырём вопросам:

1. Подтвердить hybrid-направление: тёплая полуреалистичная комната плюс тонкий
   cinematic digital layer.
2. Подтвердить базовую wide-композицию: Маша немного левее центра, Conversation
   преимущественно справа, с adaptive placement.
3. Выбрать privacy default для unfocused окна: маскировать все sensitive Surfaces
   (рекомендуется) или оставлять последний conversation preview.
4. Согласовать первый Tier 1 art slice: одна canonical комната, один clothing
   variant, 3–4 poses и минимальный набор выражений — без фиксации финального
   гардероба и всех состояний.

Окончательная палитра, framework, animation engine и Tier 2 не требуют решения
до проверки следующего композиционного prototype.

## 18. Recommended next implementation step

Следующий безопасный шаг: **UI-04C — Visual Composition Workshop**.

Он должен отобразить три существующих `CompositionVariant` как несколько
disposable визуальных вариантов одной комнаты, а не как разные frontend. Вместе
с пользователем нужно проверить визуальную иерархию, масштаб Маши, ощущение
Conversation справа, Activity/Confirmation transitions и privacy/safety language.

UI-04C не должен выбирать production framework, подключать LLM/domain runtime
или создавать финальный avatar pack. После выбора композиции можно отдельно
принять renderer decision и начать первый live shell поверх UI-01.

---

## UI-04 STATUS

**UI-04A DESIGN COMPLETE / UI-04B FOUNDATION IMPLEMENTED**

Targeted UI-04B/presentation/UI-01 regression: `55 passed`.
Full regression: `334 passed`.

No production renderer, frontend framework, domain contract, LLM call,
persistence or SQLite schema was added or changed.
