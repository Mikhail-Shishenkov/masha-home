# UI-05D — Conversation UX Clarity

Status: **IMPLEMENTED**

UI-05D improves the existing local Conversation Surface without changing conversation, memory,
identity, temporal, model, or safety semantics.

- **New conversation** is explicit and human-readable. It forgets only the current window's
  opaque conversation reference; it never deletes a transcript, long-term memory, or any other
  persistent data. The next submitted message creates the new conversation through the existing
  application boundary.
- The transcript remains bounded and scrollable. When history exists, the large welcome title
  contracts to give the actual conversation more room; user and assistant messages remain
  distinct and readable.
- The visual background uses two full-scene image layers. A verified presentation state crossfades
  over 520 ms instead of replacing a single image abruptly. No cutout compositing, blur, random
  animation, or LLM-selected visual state is introduced.
- Only one turn remains in flight. The new-conversation action is disabled while the local model
  is responding.

This is a UI/UX change only. A model calling the user by the wrong name or producing an unhelpful
answer is a separate behavior/identity regression and must be fixed at the conversation contract,
not hidden or rewritten by the renderer.
