# UI-06H — Home performance investigation

**Status:** complete. Slice D is not started.

## Renderer boundary

Home is hosted by `QWebEngineView`: Chromium's DOM/CSS compositor inside a Qt
window. It is **not** a Qt Quick scene graph. There are no `MultiEffect`,
`ShaderEffectSource`, or Qt Quick `ShaderEffect` objects in this application.

Hardware compositing is the default. `MASHA_HOME_SOFTWARE_COMPOSITING=1` is an
explicit troubleshooting fallback only; it is not the normal renderer.

## Measurement

The local `tools/home_performance_probe.py` used the production desktop shell,
read DOM state with `runJavaScript`, clicked only the read-only Working corner,
and wrote no application data. Viewport: **3840 × 2100**.

| Scenario | Mean frame time | p95 | Result |
| --- | ---: | ---: | --- |
| Idle | 16.39 ms | 16.80 ms | ~61 FPS |
| Working corner open | 16.49 ms | 16.80 ms | ~61 FPS |
| Working corner closed | 16.35 ms | 16.80 ms | ~61 FPS |
| Hero crossfade | 15.91 ms | 16.70 ms | ~63 FPS |
| Hero crossfade without CSS `filter` | 16.25 ms | 16.70 ms | ~62 FPS |

The control run without hero filter did not improve frame time. `backdrop-filter`
and `clip-path` are already absent from production Home surfaces, so they are
not the observed bottleneck.

## Findings

1. **The previous global software-compositing change was a regression.** It
   makes a bitmap-heavy 4K Home sluggish. Hardware compositing remains default.
2. **The chat ghost was real.** After a contextual surface opened, the
   conversation had `opacity: 0` but remained an active full-size DOM layer.
   It is now set `hidden` after its short exit; on return it is restored before
   the normal fade-in. The probe now reports only the Working corner as visible
   while that surface is open.
3. **Two hero `<img>` elements coexist by design during crossfade.** They are
   both 1672 × 941 source images, scaled to the viewport. After a transition
   only one has opacity 1; the other remains in the DOM at opacity 0 so the next
   swap can reuse the layer.
4. **No source reload was observed during crossfade.** Scene assets report
   `complete: true` and an existing `naturalWidth` when used. The custom
   `masha://` scheme does not expose image entries through the browser Resource
   Timing API, so the Chromium decoded-image cache cannot be proved through the
   public Qt WebEngine API. The existing preload is still used.
5. **No layout reflow is coupled to hero swapping.** Surfaces are absolutely
   positioned. The one intentional `offsetWidth` read occurs only after the old
   surface has left, to stage a clean conversation fade-in; it does not occur
   during the hero image swap.

## Minimal correction

- Restore GPU default.
- Keep optional software fallback for a known-bad driver.
- Remove the concealed conversation surface from layout/paint using `hidden`.

## Manual visual check

The probe exercised actual Working corner open/close handlers. The visible DOM
state is deterministic: while the corner is open, only that contextual surface
is visible; after closing, only the conversation surface is visible.

If a user still sees whole-window stalls after this correction, capture the
process/GPU information from the affected machine before changing visual design:
the deterministic renderer measurements do not reproduce that stall.
