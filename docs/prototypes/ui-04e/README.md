# UI-04E Visual Asset & Motion Workshop

Disposable layered 2D workshop. It consumes the semantics already approved in
UI-04B but does not import or change production runtime code.

Open `index.html` directly in a desktop browser. No server, dependency, LLM,
Ollama, persistence or network is required.

Controls:

- `1`–`8`: Idle, Conversation, Deep Conversation, Activity, Confirmation,
  Check-in, Emergency Stop, Special Evening;
- `E`: expression workshop;
- `A`: attention workshop;
- `P`: pose workshop;
- `O`: outfit workshop;
- `S`: Surface workshop;
- `M`: motion workshop;
- `Left` / `Right`: previous / next state inside the current workshop;
- `Space`: replay the selected authored motion sequence;
- `H`: hide workshop chrome;
- `F`: fullscreen;
- `R`: deterministic reset.

The normal experience uses one room background, separately composited Masha pose
and expression atlases, spatial CSS Surfaces, ambient/depth/light layers and a
safety overlay. `prefers-reduced-motion` disables authored movement.

Run the deterministic checks:

```powershell
node --test docs\prototypes\ui-04e\workshop.test.cjs
```

All PNG assets, coordinates, timings, typography and CSS effects are disposable.
Opaque asset IDs, semantic axes, deterministic selection and authority boundaries
are the intended contract candidates.
