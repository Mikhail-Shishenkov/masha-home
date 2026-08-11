# UI-04D — Masha Home Visual Design Brief

Статус: **VISUAL DIRECTION FIXED / DISPOSABLE PROTOTYPE READY**

Дата: **2026-08-11**

## 1. Core idea

Masha Home — не dashboard, чат-приложение или desktop assistant with avatar.
Это единое локальное пространство, где Маша постоянно присутствует как субъект,
а функции временно проявляются вокруг неё.

Порядок визуального восприятия:

```text
комната → Маша → состояние комнаты → взаимодействие
```

Не:

```text
header → sidebar → avatar → chat → cards → buttons
```

Основное направление: UI-04C A (`presence_first`) плюс крупный Conversation из
B и пространственная трансформация Activity/Check-in из C.

## 2. Masha as the permanent anchor

Маша не является widget, карточкой, кнопкой или декоративным фоном. Она может
сидеть, стоять, работать, слушать, думать, смотреть на пользователя или Surface,
улыбаться, спорить, удивляться и быть серьёзной.

Presentation state выбирается детерминированно. LLM не выбирает:

- animation;
- coordinates/layout;
- camera movement;
- expression;
- safety presentation;
- transition timing.

## 3. Visual Identity

Все states должны восприниматься как одна Маша:

- стабильное лицо, волосы, возрастная группа и ключевые черты;
- стабильная базовая палитра и visual style;
- controlled variations одежды, позы, expression, причёски, аксессуаров,
  lighting и activity context;
- deterministic bounded asset selection;
- никаких заново сгенерированных лиц во время runtime.

## 4. Initial Tier 1 pack

Начальный pack остаётся небольшим:

- одна узнаваемая нейтральная комната;
- 3–4 базовые позы;
- 6–10 выражений;
- 2–3 attention states;
- один повседневный, один рабочий и один нарядный образ.

Room должна поддерживать conversation, activity, check-in, confirmation, idle,
safety и будущие voice/media/device manifestations без смены visual language.

## 5. Special evening

`special_evening` — редкое presentation state, не режим приложения. Маша может
быть особенно эффектной, уверенной и нарядной: выразительная одежда, открытые
плечи, украшения, более кинематографичный light и уверенная мимика.

Умеренная чувственность и игривость допустимы и желательны: они выражаются через
взгляд, полуулыбку, пластику, силуэт и осознанный выбор образа. Это редкая живая
грань Маши, а не стерильность и не обязательное состояние интерфейса.

Граница: никакого erotic UI, наготы, порно-эстетики, сексуальных поз как
interaction mechanic или постоянной сексуализации.

## 6. Composable visual vocabulary

Mood:

```text
calm, warm, happy, amused, curious, thoughtful, focused,
skeptical, slightly_annoyed, concerned, surprised, tired,
playful, confident
```

Activity:

```text
reading, writing, working, thinking, drinking_coffee,
listening, looking_at_surface, waiting, preparing, relaxing
```

Attention:

```text
direct, side, user, activity, presenting, waiting_for_confirmation
```

Эти оси комбинируются. Они не требуют отдельного raster asset для каждой
возможной комбинации.

## 7. Interaction language

### Conversation

Soft Surface преимущественно справа от Маши. Она может появляться, расширяться,
сворачиваться и исчезать. Для глубокого разговора используется более крупная B-
композиция, но Маша не превращается в avatar widget.

### Activity

Главный источник трансформации пространства. Вместо `Loading... 73%` меняются
light, depth, position, Surface geometry, ambient и shared focus. Переходы
плавные, предсказуемые и основаны только на подтверждённом Activity state.

### Confirmation

Decision Surface возникает как один объект внимания рядом с источником решения,
а не generic modal. Маша visual state показывает ожидание ответа.

### Check-in

Самый мягкий interaction. Сигналом сначала становится Маша: взгляд, поворот,
expression и ambient light gesture. Whisper Surface может быть маленькой или
отсутствовать.

### Emergency stop

Autonomous spatial layer останавливается, Activity transitions и proactive
manifestations прекращаются, ambient снижается. Маша и Conversation остаются.
Emergency stop останавливает автономность, а не Машу.

## 8. Three Surface classes

- **Soft Surface:** Conversation, Check-in, small contextual interaction.
- **Working Surface:** Activity, planning, documents, long operations.
- **Decision Surface:** Confirmation, approvals, permissions, safety decisions.

Все три используют один visual language.

Semantic meaning:

- Glass = существует информационное пространство;
- Light = здесь находится внимание;
- изменение комнаты = изменился контекст взаимодействия.

Чем важнее контекст, тем сильнее допустима трансформация. Обычный ответ не
запускает световое шоу.

## 9. Camera and motion

Разрешены subtle reframing, controlled depth, мягкое приближение и небольшое
изменение focus. Запрещены резкие cuts и постоянное cinematic движение.

Пользователь должен чувствовать изменение пространства, а не смотреть кат-сцену.

## 10. Responsive

Narrow означает узкое desktop window, не mobile UI.

Сохраняются:

1. Маша;
2. primary interaction Surface;
3. максимум один supporting trace.

Композиция не превращается в вертикальный список карточек.

## 11. Prohibited visual outcomes

- dashboard/sidebar-heavy UI;
- permanent status header;
- avatar card;
- notification centre/card grid;
- modal-heavy interface;
- pixel art/flat cartoon;
- sci-fi HUD everywhere;
- permanent glass panels;
- decorative motion without semantic meaning;
- перенос внешнего вида Tier 0 в production.

## 12. Renderer boundary

Renderer получает `CompositionPlan` и presentation state. Он отвечает за
visualisation, transitions, input и authored animation playback.

Presentation Runtime остаётся источником composition, lifecycle, state,
priority, focus, safety и privacy. LLM и Skills не получают renderer access и не
могут внедрять frontend.

## 13. Disposable interactive prototype

Локальный prototype:

[`prototypes/ui-04d/index.html`](prototypes/ui-04d/index.html)

Он содержит восемь детерминированных visual fixtures:

1. Idle;
2. Conversation;
3. Deep Conversation;
4. Activity;
5. Confirmation;
6. Check-in;
7. Emergency Stop;
8. Special Evening.

`H` скрывает весь prototype chrome для проверки сцены без подписей и badges.
`F` включает fullscreen. `1`–`8` и стрелки переключают states.

Prototype работает напрямую из локального файла, не использует server, network,
LLM, domain runtime или persistence и не является выбором production frontend.

## 14. Readiness criteria

Перед production frontend должны одновременно проходить два человеческих теста:

> «Блядь. Это реально Маша дома».

и:

> «Я понимаю, что сейчас происходит даже без подписей и badges».

Если Conversation, Activity, Confirmation, Check-in и Emergency Stop не читаются
через пространство, Машу, внимание, свет и behaviour, дизайн ещё не готов.

Сначала качество и композиция. Затем framework. Затем production.
