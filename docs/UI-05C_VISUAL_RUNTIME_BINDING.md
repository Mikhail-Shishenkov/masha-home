# UI-05C — Visual Runtime Binding

Status: **IMPLEMENTED / FOUR APPROVED LOCAL SCENES**

The desktop renderer uses a compact local scene registry rather than compositing a person over
an unrelated room. Each selected asset is a complete scene with Masha, room geometry, physical
anchor, and lighting already aligned.

| Presentation signal | Scene ID | Local asset |
| --- | --- | --- |
| idle or unavailable | `scene.home.idle` | `canonical-master.png` |
| listening, waiting, speaking | `scene.home.conversation` | `conversation-candidate.png` |
| processing | `scene.home.thinking` | `thinking-candidate.png` |
| working | `scene.home.activity` | `activity-candidate.png` |

The mapping is deterministic and local. It consumes only `HomePresentationModel.presence.activity`
and the model availability overlay. It does not inspect user text, LLM text, identity data, memory,
or any external source. When the local model is unavailable, the renderer intentionally returns
to the canonical idle scene and presents the controlled runtime error through the conversation
surface.

`special evening` assets are bundled for workshop continuity only. They are deliberately not part
of automatic runtime selection until a separate human review accepts the visual direction and a
user-facing semantic trigger is agreed.

No image generation, network loading, animation rig, or new domain capability is introduced.
