# UI-04H — Confirmation Surface Workshop

Disposable local renderer for three related questions: can a conversation composer,
an explicit confirmation, and a readable long-running activity coexist beside Masha
without becoming dashboard cards or a blocking modal?

Open `index.html` locally. This prototype has no network, model, persistence or
domain mutation. Buttons change only immutable in-memory presentation fixture.

Keyboard: `Enter` confirms an open preview when the composer is not focused, `Esc`
dismisses it, `E` emergency stop, `P` privacy, `C` opens decision fixture, `A` toggles
the Activity fixture, `I` shows a local check-in fixture. No actual task runs or messages.

Conversation is a scrollable in-memory fixture. After sending, the button is disabled until a
deterministic demonstration response appears; it is deliberately not a local-model call or saved history.

The small bottom "Дом" orientation strip switches only local visual fixtures; it is not an
application navigation system and does not access backend data.

Run deterministic checks:

```powershell
node --test docs/prototypes/ui-04h/confirmation.test.cjs
```
