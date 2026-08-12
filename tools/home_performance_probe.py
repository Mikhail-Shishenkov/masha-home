"""One-off local performance probe for the QWebEngine Home renderer.

It intentionally uses the production desktop shell, but only reads DOM state
and opens/closes a read-only Workbench surface.  It writes no application data.
Run it with ``python tools/home_performance_probe.py`` from the project root.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from backend.ui.desktop_host import MashaHomeWindow, register_masha_scheme


START_SAMPLE = """
(() => {
  const frameTimes = [];
  const duration = window.__mashaPerformanceDuration || 1600;
  let previous = performance.now();
  const started = previous;
  function frame(now) {
    frameTimes.push(now - previous); previous = now;
    if (now - started < duration) { requestAnimationFrame(frame); return; }
    const sorted = [...frameTimes].sort((a, b) => a - b);
    const percentile = (p) => sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * p))] || 0;
    const visible = [...document.querySelectorAll('.conversation-surface, aside')]
      .filter((node) => !node.hidden)
      .map((node) => ({ id: node.id, opacity: getComputedStyle(node).opacity, pointerEvents: getComputedStyle(node).pointerEvents }));
    window.__mashaPerformanceProbe = {
      frames: frameTimes.length,
      avg_frame_ms: frameTimes.reduce((sum, value) => sum + value, 0) / frameTimes.length,
      p95_frame_ms: percentile(.95),
      max_frame_ms: Math.max(...frameTimes),
      visible,
      scenes: [...document.querySelectorAll('.scene')].map((node) => ({ src: node.getAttribute('src'), className: node.className, opacity: getComputedStyle(node).opacity })),
      hero_resources: performance.getEntriesByType('resource').filter((entry) => entry.name.includes('/assets/')).map((entry) => entry.name),
      hero_decode_state: [...document.querySelectorAll('.scene')].map((node) => ({ complete: node.complete, naturalWidth: node.naturalWidth, currentSrc: node.currentSrc })),
      filters: [...document.querySelectorAll('.scene')].map((node) => getComputedStyle(node).filter),
    };
    return;
  }
  requestAnimationFrame(frame);
})()
"""

READ_SAMPLE = "JSON.stringify(window.__mashaPerformanceProbe || null)"


def main() -> int:
    register_masha_scheme()
    app = QApplication(sys.argv)
    window = MashaHomeWindow()
    window.resize(3840, 2100)
    window.show()
    results: dict[str, object] = {}

    def sample(name: str, then, *, duration_ms: int = 1600, action: str | None = None) -> None:
        prefix = action or ""
        script = f"window.__mashaPerformanceDuration = {duration_ms}; {prefix}; {START_SAMPLE}"
        window._page.runJavaScript(script)
        QTimer.singleShot(duration_ms + 140, lambda: window._page.runJavaScript(READ_SAMPLE, lambda value: finish_sample(name, value, then)))

    def finish_sample(name: str, value, then) -> None:
        results[name] = json.loads(value) if value else {"error": "probe returned no value"}
        then()

    def open_workbench() -> None:
        window._page.runJavaScript("document.getElementById('workbench-trigger').click()")
        QTimer.singleShot(700, lambda: sample("workbench_open", close_workbench))

    def close_workbench() -> None:
        window._page.runJavaScript("document.getElementById('close-workbench').click()")
        QTimer.singleShot(700, lambda: sample("workbench_closed", start_hero_crossfade))

    def start_hero_crossfade() -> None:
        sample(
            "hero_crossfade",
            start_without_hero_filter,
            duration_ms=650,
            action="applyScene({home_state: 'ready', overlays: {safety: 'normal', model: 'ready'}, presence: {activity: 'listening', attention: 'toward_user', ambient: 'calm', expression: {code: 'warm'}}})",
        )

    def start_without_hero_filter() -> None:
        sample(
            "hero_no_filter",
            finish,
            duration_ms=650,
            action="document.querySelectorAll('.scene').forEach((node) => { node.style.filter = 'none'; }); applyScene({home_state: 'ready', overlays: {safety: 'normal', model: 'ready'}, presence: {activity: 'processing', attention: 'toward_user', ambient: 'calm', expression: {code: 'warm'}}})",
        )

    def finish() -> None:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        app.quit()

    window._view.loadFinished.connect(lambda ok: QTimer.singleShot(1200, lambda: sample("idle", open_workbench)) if ok else finish())
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
