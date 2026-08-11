# UI-05A — Local Conversation Host Boundary

Статус: **UI-05B IMPLEMENTED / NO STREAMING OR COMMAND EXPANSION**

## Фактическая отправная точка

Для UI уже существует публичная локальная граница:

```text
UI host
→ MashaApplication.send_message(...)
→ ConversationApplicationService.send_message(...)
→ ConversationService
→ Identity + bounded Memory + Time + ModelRouter
→ local Ollama profile
```

`ConversationApplicationService` уже возвращает UI-safe `ConversationTurnResult` и
контролируемые статусы `completed`, `model_unavailable`, `timeout`, `failed`.
История доступна через `MashaApplication.conversation(conversation_id, limit=...)` как
`ConversationView` / `MessageView`.

Следовательно, UI-05A **не создаёт второй conversation adapter** и не обращается напрямую
к `ConversationService`, `ConversationStore`, Memory, IdentityKernel, ModelRouter, Ollama
или SQLite.

## Минимальный host contract

Будущий desktop host получает только такой порт:

```text
open_conversation(conversation_id, limit=16) -> ConversationView
submit_message(content, project_id, conversation_id?) -> ConversationTurnResult
status() -> MashaStatusView
```

`project_id` выбирается local application host, а не вводится в поле переписки и не
доверяется LLM. `conversation_id` хранится UI host как opaque local reference.

## Один честный turn

```text
user presses Send
→ UI validates non-empty bounded text
→ composer enters sending (button disabled, text remains visible)
→ worker calls MashaApplication.send_message
→ result is mapped deterministically
   completed        → render persisted user + assistant MessageView
   unavailable      → retain user message if persisted; show local availability state
   timeout          → retain user message if persisted; show retry affordance
   failed           → do not fabricate Masha text; show controlled local error
→ composer becomes ready
```

The call runs outside the renderer event loop through one local worker. The selected transport
is a closed Qt WebChannel object named `mashaHome`; no HTTP server, websocket, cloud transport,
or generic RPC surface is introduced.

## Conversation Surface rules

- Transcript is a scrollable, bounded human-readable view; initial window is 16 persisted
  messages, matching the existing conversation boundary default.
- New turn appends in chronological order and scrolls only when the user is already near
  the latest message. Reading older history must never be forcibly interrupted.
- Only one send is in flight per Conversation Surface. The Send button is disabled while
  waiting; this is a UI invariant, not a ModelRouter policy.
- The UI may show `thinking / inward` while a turn is in flight, but must not show a
  fabricated assistant response.
- After an actual completed assistant message, Presentation Runtime may select
  `warm / user`; presentation state does not alter the message content.
- Model failure leaves Masha visually present. It is not represented as silence, a false
  response, or a change to Identity.

## Safety and privacy

Emergency Stop does not block ordinary conversation unless the existing application boundary
returns a controlled error. It stops autonomous activity only. UI must never use Stop to
delete a draft, history, or conversation reference.

Privacy mode only masks rendered content. It does not reload, erase, mutate, or re-query
conversation history.

## Explicit non-goals

- no frontend framework decision;
- no HTTP server, websocket, cloud, or external channel;
- no streaming implementation;
- no new history store or client-side source of truth;
- no automatic model fallback or switch;
- no direct UI access to Memory / Identity / SQLite;
- no LLM-owned expression or scene selection.

## First implementation slice after UI-05A approval

Create a local desktop host adapter that injects `MashaApplication` and converts only
`ConversationView` / `ConversationTurnResult` to the existing Presentation Runtime events.
It replaces the `SIMULATED_ASSISTANT_RESPONSE` fixture, preserves the 1-in-flight composer
rule, and is verified using the existing isolated application-boundary test fixture.

The host choice is now PySide6 + Qt WebEngine with a closed `masha://home/` origin. The bridge
has only `loadInitialState()` and `submitMessage(content)`; it holds the opaque conversation
reference and application-owned `project_masha_home` identifier locally. It loads at most 16
persisted messages from the conversation with the latest actual interaction.
