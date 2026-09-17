# Masha Home — Agent Coherence Continuation

Статус: **ACTIVE ENGINEERING CHECKPOINT — NOT RELEASED / NOT MERGE-ACCEPTED**  
Ветка: `new/agent-coherence-continuation`  
Последняя консолидация capsule: 2026-09-17

Этот файл — короткая **resume capsule** для незавершённой coherence-работы.

Полный исторический trace старого плана со всеми промежуточными checkpoint-ами, неудачными экспериментами и measured evidence сохранён без переписывания:

[`archive/checkpoints/AGENT_COHERENCE_PLAN_FULL_2026-09-16.md`](archive/checkpoints/AGENT_COHERENCE_PLAN_FULL_2026-09-16.md)

Не начинать расследование заново, если текущий код и эта capsule уже отвечают на вопрос.

## 1. Authority и release status

Исходный опубликованный engineering checkpoint: `7d9e10066b5c2f05bd6f34aba73b2a4ff37a6d7a`.

После него 17 сентября выполняется документационная консолидация. Docs-only commits не означают release acceptance.

Текущий пользовательский approval покрывает сохранение/ведение рабочей ветки и документационные правки. Он **не является approval** на:

- merge в `main`;
- объявление coherence завершённым;
- объявление natural-language quality принятой;
- ослабление grounding/safety ради прохождения примера.

Любое решение о merge принимается отдельно после acceptance gate.

## 2. Что уже реализовано в coherence checkpoint

### Bounded dialogue continuity

Устранена destructive history truncation после APPLICATION message. Предыдущий bounded user/model dialogue сохраняется для topic continuity.

Application history остаётся описательным контекстом и не даёт mutation authority.

### Shared application-owned turn context

Semantic understanding и response generation получают согласованные bounded projections текущего контекста, включая application-owned presented/focused real objects и verified recent results.

IDs, selection truth, confirmation и operation truth остаются у application/domain owners.

### Meaning-first semantic path

Первый semantic request предлагает только speech act:

```text
ordinary | create | update | read | unclear
```

На первом шаге нет capability IDs/catalog selection.

Ordinary conversation заканчивается без второго semantic mapping call.

Для action-like turn второй bounded step использует:

- исходную пользовательскую реплику;
- bounded turn context;
- только совместимые application-owned capability specifications.

Semantic mapping остаётся untrusted. Home валидирует candidate, literal evidence, slots, referents, provider ownership, grounding и supported operation.

Malformed/failed mapping не должен падать в unrestricted legacy mutation route.

### Provider ownership veto

Явный Google Drive request не может быть молча перенаправлен в Yandex Disk. Application может veto conflicting provider mapping, но не обязана придумывать замену ради успеха.

Narrow registry description correction `Google Drive (Гугл Диск)` дала правильный routing на измеренном 7/7 наборе FAST probes. Это routing evidence, не universal language proof.

### Existing-object continuity

Existing saved reminder update остаётся update и не должен превращаться в duplicate create.

Calendar event может быть typed temporal anchor для event-relative reminder, но не заменяет identity/time сохранённого reminder при его update.

## 3. Measured evidence

Последний полный deterministic gate внутри checkpoint-а:

```text
pytest -q -m "not live_smoke"
736 passed, 2 skipped
```

Дополнительно в checkpoint-е зафиксированы:

- `compileall` clean;
- `git diff --check` clean;
- 23 Node test entries passed;
- после narrow Google Drive description correction — 122 focused/affected tests passed.

Configured semantic FAST profile в measured probes: `masha-fast:4b`, `think=false`; resolver probes использовали temperature 0.

Эти числа относятся к зафиксированному checkpoint-у. Docs-only commits после него не требуют притворяться, что полный Python gate был повторён.

## 4. Что доказано только частично

### Event-relative reminder

Один измеренный case:

> «Можешь напомнить мне об этом за час до начала?»

при focused Calendar event на 14:00 корректно дал Home reminder на 13:00 Saratov.

Это доказывает конкретный resolver/application path, а не весь класс relative-time языка.

### Google/Yandex/Mail routing

Narrow fixed set прошёл routing, но routing ≠ end-to-end provider journey. Например корректный Mail candidate ещё может иметь неполные extracted fields.

## 5. Открытый blocker: relative-time field extraction

Ключевой известный failure:

> «Не дай мне забыть об этом, напомни за полчаса до события»

Модель может правильно выбрать reminder capability, но вернуть date/time вместо `relative_time`.

Application в этом случае правильно отклоняет неподходящие поля и просит уточнение.

Нельзя «чинить» это так:

- phrase-specific router/regex vocabulary;
- silent acceptance неправильного evidence;
- loosening grounding;
- подстановка Calendar anchor вместо отсутствующего saved-reminder anchor;
- broad prompt/catalog dump;
- смена модели без измеренного root-cause evidence.

Следующий шаг — измерять proposed fields/schema presentation на маленьком фиксированном + unseen наборе.

## 6. Complete dialogue journeys — обязательный acceptance gate

После field-quality gate проверить несколько **законченных** сценариев, а не отдельные фразы.

Минимальный pattern:

```text
earlier result
→ natural reference
→ clarification/correction
→ preview/proposal
→ explicit confirmation
→ operation through fake/synthetic adapter
→ verified receipt/outcome
→ natural follow-up
```

Нужны как минимум:

1. existing Calendar event → reference → update/correction → confirmation → verified result;
2. event → relative reminder → correction → confirmation → SAME reminder semantics;
3. prior Mail/File/Web result → deictic follow-up → correct grounded action/read;
4. ordinary topic across application message → «о чём мы говорим?» без conversation amnesia;
5. new ordinary chat → уместное возвращение к одной открытой continuity-теме без task-review greeting.

Engineering probes должны использовать fake/synthetic adapters для writes. Не мутировать реальный mailbox/calendar ради acceptance trace.

## 7. Gentle cross-chat continuity

Рекомендованный UX direction:

- помнить релевантные незавершённые темы;
- иногда естественно возвращать одну подходящую тему;
- не превращать каждое приветствие в список задач;
- не поднимать forgotten/sensitive темы;
- не смешивать Special Evening с ordinary chat;
- уважать «не сейчас»;
- если remembered fact мог устареть — уточнять, а не утверждать его как текущий.

Provenance, dated Memory, Saratov time, current topic, selected real objects, pending requests и verified results остаются application-owned и model-independent настолько, насколько это архитектурно возможно.

Language quality при смене модели полностью model-independent быть не может; continuity state при этом не должна исчезать.

## 8. Invariants, которые нельзя потерять

- `Masha != LLM`;
- semantic output = proposal, не authority;
- conversation history = context, не permission;
- selected real object / provider ID = application truth;
- mutation requires domain proposal + policy/confirmation;
- operation truth принадлежит provider/domain owner;
- model promise != receipt;
- external evidence не может авторизовать write;
- no hidden second dialogue-state owner;
- no live destructive/provider mutation during language diagnostics;
- deterministic green tests != conversational acceptance.

Подробный contract: [`DIALOGUE_ACTION_LIFECYCLE.md`](DIALOGUE_ACTION_LIFECYCLE.md).

## 9. Resume protocol

Перед следующей **инженерной** правкой:

1. проверить branch / HEAD / working tree;
2. прочитать [`CURRENT_STATE.md`](CURRENT_STATE.md) и эту capsule;
3. читать полный archived trace только если нужен provenance конкретного решения;
4. выбрать один оставшийся failed journey;
5. измерить root cause;
6. изменить минимальный owner;
7. прогнать focused deterministic checks;
8. при достижении stage gate — нужный full deterministic gate;
9. затем eval/live/manual acceptance;
10. merge обсуждать отдельно.

Не повторять broad forensic audit и не строить новый framework без нового evidence.

## 10. Что делать после acceptance

После успешной human acceptance:

- перенести устойчивые решения в Canon / Decisions / domain contracts;
- зафиксировать оставшиеся known limitations;
- повторить release-relevant deterministic gates;
- отдельно получить approval на merge;
- после merge архивировать эту active capsule как завершённый checkpoint.

Пока эти условия не выполнены, ветка остаётся recoverable engineering checkpoint, а не release.
