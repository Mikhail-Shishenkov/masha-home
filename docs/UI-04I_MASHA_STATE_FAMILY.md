# UI-04I — Masha State Family

Статус: **UI-05C RUNTIME BINDING / FOUR APPROVED SCENES**

## Решение

Базовый visual anchor — утверждённый сидячий кадр Маши в её гостиной:
`scene.home.idle` → `assets/ui-04g/canonical-master.png`.

Маша не будет собираться из cutout-слоёв поверх отдельной комнаты. Для состояний,
где меняется поза, перспектива или физическое действие, используется цельная сцена
«Маша + комната + свет». Для остальных состояний меняются только presentation axes
и spatial surfaces. Это сохраняет лицо, масштаб, контакт с мебелью и качество на 4K.

## Два уровня состояния

### A. Сцены-ключи

| ID | Назначение | Текущее состояние |
| --- | --- | --- |
| `scene.home.idle` | спокойное присутствие дома | есть, утверждённый master |
| `scene.home.conversation` | открытый разговор, внимание к пользователю | есть |
| `scene.home.activity` | физически читаемая работа в комнате | есть |
| `scene.home.thinking` | пауза размышления без тревоги или отчуждения | следующий новый candidate |
| `scene.home.special_evening` | редкий эстетический вечерний образ | provisional, не расширять без нового review |

`confirmation`, `check-in`, `privacy`, `safety` и `model unavailable` не требуют
новой сцены Маши: это разные surface/ambient состояния поверх подходящей сцены-ключа.

### B. Композиционные axes

Оси не принадлежат LLM и не являются утверждениями о реальных эмоциях. Это
presentation-намерения, которые выбирает детерминированный Presentation Runtime.

```text
attention: none | user | surface | inward
expression: calm | warm | attentive | thoughtful | focused
            amused | tender | skeptical | firm | concerned | pleased
ambient: home | close_conversation | work | quiet_evening | safety_pause | privacy
surface: conversation | activity | confirmation | checkin | none
```

`concerned` означает только визуально внимательное присутствие; он не диагностирует
состояние пользователя. `firm` нужен для честного несогласия Маши, а не для агрессии.

## Первые 15 читаемых состояний

| # | Состояние | Сцена | Presentation axes |
| --- | --- | --- | --- |
| 1 | Дом, покой | idle | calm / none / home |
| 2 | Разговор | conversation | warm / user / close_conversation |
| 3 | Слушает | conversation | attentive / user / close_conversation |
| 4 | Размышляет | thinking | thoughtful / inward / quiet_evening |
| 5 | Работает | activity | focused / surface / work |
| 6 | Прогресс задачи | activity | focused / surface / work + Activity Surface |
| 7 | Готово | activity → idle | pleased / user / home |
| 8 | Нужен выбор | idle или conversation | attentive / surface / confirmation |
| 9 | Check-in | idle | warm / user / checkin |
| 10 | Мягко шутит | conversation | amused / user / close_conversation |
| 11 | Не согласна | thinking или conversation | firm / user / close_conversation |
| 12 | Рядом в тишине | idle | tender / user / quiet_evening |
| 13 | Автономность на паузе | idle | calm / none / safety_pause |
| 14 | Личный контекст скрыт | current scene | calm / none / privacy |
| 15 | Особенный вечер | special_evening | amused / user / quiet_evening |

Это не giant state machine: например, `activity + focused + safety_pause` остаётся
корректной композицией. Safety способен скрыть Activity Surface, но не отменяет
работу и не меняет данные задачи.

## Правила качества

- Одно и то же лицо, волосы, scale, camera language и room geography во всей семье.
- Никаких beauty-ad бликов, studio-light на Маше, cutout-краёв или случайной смены комнаты.
- Любая новая цельная сцена проходит review: identity, anatomy, physical anchor,
  room continuity, label-free readability и quiet zone.
- Не генерировать 15 картинок пакетно. Сначала `thinking`, затем пользовательский review.
- Emotions не дают модели права самой выбирать изображение. LLM может дать текст;
  визуальное состояние назначается только Presentation Runtime из проверенных событий.

## Thinking candidate

![Thinking candidate](assets/ui-04i/thinking-candidate.png)

`scene.home.thinking` был одобрен в workshop как bounded candidate. Он создан как
одна bounded full-scene вариация от approved canonical master:

- та же гостиная, eye-level wide 16:9 camera и свободная правая quiet zone;
- та же сидячая поза в кресле, белый домашний top и shorts;
- взгляд в сторону и мягкая опора пальцев у подбородка читаются как пауза размышления;
- без UI, текста, нового света, studio-ретуши, тревожной мимики или смены образа.

В UI-05C эта сцена также подключена к production desktop shell как bounded visual asset:
только детерминированный `PresenceActivity.PROCESSING` выбирает `scene.home.thinking`.
Она не может быть выбрана LLM, пользовательским текстом или внешним источником.

В `ui-04h` он выбирается только детерминированно: локальный conversation fixture находится
в состоянии `thinking`. Ни LLM, ни пользовательский текст не выбирают asset напрямую.

## Prototype presence registry

`ui-04h/confirmation-core.js` теперь публикует closed vocabulary `presenceAxes` и
детерминированно проецирует `presence.expression` + `presence.attention`:

- ожидание fixture-ответа → `thoughtful / inward`;
- Activity Surface → `focused / surface`;
- confirmation → `attentive / surface`;
- check-in и разговор → `warm / user`;
- Emergency Stop → `calm / none`.

Пока эти axes меняют только semantic presentation state и data-attributes renderer. Они
не являются обещанием, что у Маши уже есть отдельный PNG для каждого выражения.

## Следующая безопасная реализация

1. UI-05C связал `idle`, `conversation`, `thinking` и `activity` с production renderer через
   closed local asset registry. Runtime выбирает их только по `HomePresentationModel`.
2. Нужен human review следующей небольшой группы full-scene кадров прежде, чем расширять семью
   на новые эмоции; не генерировать 15 независимых образов пакетом.
3. После review можно добавить transition/motion layer поверх этих же semantic states, не меняя
   `ConversationApplicationService`, ConversationService или Ollama.

## Не входит в UI-04I

- production frontend framework;
- UI ↔ backend transport;
- runtime image generation;
- изменение Identity, Memory, Safety, LLM или Conversation contracts;
- анимационный rig, voice и внешние сервисы.
