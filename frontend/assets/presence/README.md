# Masha presence library

This is the curated production library for the Home scene resolver.

- `day/` — one coherent late-morning family for the ordinary activity states.
- `evening/` — the canonical warm family plus the preserved rare cozy variants.
- `context/` — approved poses with clear emotional or situational value; these
  are not selected directly by model text.

The renderer may select only from the closed registry in
`frontend/scenes/scene-map.js`. New visual variants should preserve Masha's
identity, room geometry, camera direction, and the right-side quiet zone.
