# UI-05E — Recent Conversations and Scene Pack 1

Status: **IMPLEMENTED / TWO FUTURE SCENES HELD FOR EXPLICIT CUES**

## Recent conversations

The small `Разговоры` panel is a read-only view over the existing JSON `ConversationStore`.
It shows at most eight recent branches ordered by their latest actual message. Each item exposes
only a short readable preview and date; UUIDs and storage details remain hidden. Opening a branch
sets the local window's opaque conversation reference and loads its bounded 16-message transcript.

`Новый разговор` does not delete any branch. It clears only the active window reference; the next
sent message creates a new branch through the existing `ConversationService` flow.

## Scene Pack 1

All three scene assets are full images, generated from the approved canonical Masha Home scene as
an identity-preserving reference. They preserve the same room, seated framing, outfit, light, and
right-side quiet zone.

| Semantic cue | Scene | Runtime status |
| --- | --- | --- |
| user message accepted / `PresenceActivity.WAITING` | `scene.home.listening` | active |
| future explicit quiet-presence cue | `scene.home.quiet_beside` | registered, inactive |
| future explicit firm-disagreement cue | `scene.home.firm_disagreement` | registered, inactive |

The bridge now emits `turn_started` (listening) before `turn_thinking` (processing). Neither
assistant text nor model output can choose a visual scene. Quiet and firm scenes will be used only
after a separately approved deterministic presentation event exists; no sentiment classifier or
LLM-based emotion guessing is introduced.
