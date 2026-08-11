# UI-04F Living Room Integration Prototype

Disposable local vertical slice of one Masha Home room. UI-04F replaces the
separate face/body composition of UI-04E with integrated full-character authored
states and keeps the room, Masha, ambient response and Interaction Surfaces in a
single scene.

Open `index.html` directly in a desktop browser. No server, framework, LLM,
Ollama, backend, persistence or network is required.

Controls:

- `1`: Idle;
- `2`: Conversation;
- `3`: Activity;
- `4`: Completed;
- `5`: Home Evening;
- `6`: Special Evening;
- `7`: Thinking / Attention;
- `8`: Emergency Stop;
- `Space`: advance/replay the deterministic vertical slice;
- `Left` / `Right`: adjacent review state;
- `H`: hide all prototype chrome;
- `V`: privacy projection;
- `F`: fullscreen;
- `R`: reset.

The complete vertical slice is:

```text
Idle → Conversation → Activity → 28% → 62% → 88% → 100%
→ Completed → collapsing → ambient return → Idle
```

Run deterministic checks:

```powershell
node --test docs\prototypes\ui-04f\living.test.cjs
```

Generated PNGs, CSS geometry, timing, typography and chroma extraction are
disposable. The semantic asset IDs, lifecycle, single-room hierarchy and
authored interruptible transition model are contract candidates.
