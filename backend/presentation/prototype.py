"""Interactive Tier 0 desktop prototype. Uses no model, network or persistence."""

from __future__ import annotations

from collections.abc import Callable

from .tier0 import TierZeroPrototypeController, TierZeroScene


class TierZeroHomeWindow:
    """A disposable Tk adapter over the framework-independent presentation scene."""

    def __init__(self, controller: TierZeroPrototypeController | None = None):
        import tkinter as tk

        self.tk = tk
        self.controller = controller or TierZeroPrototypeController()
        self.root = tk.Tk()
        self.root.title("Masha Home · UI-03 Tier 0")
        self.root.minsize(920, 620)
        self.root.geometry("1180x760")
        self.canvas = tk.Canvas(self.root, highlightthickness=0, bg="#11151c")
        self.canvas.pack(fill="both", expand=True)
        self._actions: list[tuple[tuple[int, int, int, int], Callable[[], object]]] = []
        self.canvas.bind("<Configure>", lambda _event: self.render())
        self.canvas.bind("<Button-1>", self._click)
        self.root.bind("<Key-1>", lambda _event: self._run(self.controller.conversation_next))
        self.root.bind("<Key-2>", lambda _event: self._run(self.controller.activity_next))
        self.root.bind("<Key-3>", lambda _event: self._run(self.controller.proactive_next))
        self.root.bind("<Key-4>", lambda _event: self._run(self.controller.toggle_safety))
        self.root.bind("<Key-5>", lambda _event: self._run(self.controller.cycle_model))
        self.root.bind("<Key-6>", lambda _event: self._run(self.controller.toggle_runtime_mode))
        self.root.bind("<FocusIn>", lambda _event: self._focus(True))
        self.root.bind("<FocusOut>", lambda _event: self._focus(False))
        self.render()

    def run(self) -> None:
        self.root.mainloop()

    def render(self) -> None:
        scene = self.controller.scene()
        width = max(self.canvas.winfo_width(), 920)
        height = max(self.canvas.winfo_height(), 620)
        self.canvas.delete("all")
        self._actions.clear()
        self._draw_room(width, height)
        self._draw_orientation(scene, width)
        self._draw_conversation(scene, width, height)
        self._draw_masha(scene, width, height)
        self._draw_activity(scene, width, height)
        self._draw_footer(width, height)
        if scene.privacy_masked:
            self._draw_privacy(width, height)

    def _draw_room(self, width: int, height: int) -> None:
        wall_bottom = int(height * 0.74)
        bands = 28
        for index in range(bands):
            ratio = index / max(bands - 1, 1)
            color = self._mix("#17202b", "#2f2930", ratio)
            y1 = int(wall_bottom * index / bands)
            y2 = int(wall_bottom * (index + 1) / bands) + 1
            self.canvas.create_rectangle(0, y1, width, y2, fill=color, outline=color)
        self.canvas.create_rectangle(0, wall_bottom, width, height, fill="#17191f", outline="")
        self.canvas.create_line(0, wall_bottom, width, wall_bottom, fill="#745a52", width=2)
        self.canvas.create_polygon(
            width * 0.55,
            wall_bottom,
            width,
            wall_bottom,
            width,
            height,
            width * 0.7,
            height,
            fill="#1d2027",
            outline="",
        )
        self.canvas.create_rectangle(
            width * 0.72,
            height * 0.16,
            width * 0.91,
            height * 0.47,
            fill="#192b38",
            outline="#7893a0",
            width=2,
        )
        self.canvas.create_line(
            width * 0.815,
            height * 0.16,
            width * 0.815,
            height * 0.47,
            fill="#49616d",
        )
        self.canvas.create_line(
            width * 0.72,
            height * 0.315,
            width * 0.91,
            height * 0.315,
            fill="#49616d",
        )
        self.canvas.create_oval(
            width * 0.765,
            height * 0.24,
            width * 0.78,
            height * 0.265,
            fill="#d7ba79",
            outline="",
        )

    def _draw_orientation(self, scene: TierZeroScene, width: int) -> None:
        self.canvas.create_text(
            34,
            30,
            anchor="w",
            text=scene.room_title.upper(),
            fill="#f2e9df",
            font=("Segoe UI Semibold", 16),
        )
        self.canvas.create_text(
            34,
            55,
            anchor="w",
            text="presentation runtime · tier 0 · local only",
            fill="#8d9aa8",
            font=("Segoe UI", 9),
        )

        items = [
            (scene.proactive_label, self.controller.proactive_next, "#829b8c"),
            (scene.runtime_label, self.controller.toggle_runtime_mode, "#73879d"),
            (scene.model_label, self.controller.cycle_model, "#aa8f73"),
            (scene.safety_label, self.controller.toggle_safety, "#a97878"),
        ]
        right = width - 28
        for label, action, color in reversed(items):
            text_id = self.canvas.create_text(
                right,
                34,
                anchor="e",
                text=label,
                fill="#e7e8e9",
                font=("Segoe UI", 9),
            )
            box = self.canvas.bbox(text_id)
            if box is None:
                continue
            x1, y1, x2, y2 = box
            self.canvas.create_line(x1, y2 + 5, x2, y2 + 5, fill=color, width=2)
            self._actions.append(((x1 - 8, y1 - 8, x2 + 8, y2 + 10), action))
            right = x1 - 34

    def _draw_conversation(self, scene: TierZeroScene, width: int, height: int) -> None:
        left = 42
        top = int(height * 0.17)
        right = int(width * 0.47)
        bottom = int(height * 0.68)
        self._rounded_rect(left, top, right, bottom, 24, fill="#202831", outline="#53606b")
        conversation = next((item for item in scene.surfaces if item.kind == "conversation"), None)
        title = "РАЗГОВОР" if conversation is None else conversation.title.upper()
        summary = "Кликни сюда, чтобы пройти: сообщение → мысль → ответ"
        if conversation is not None and conversation.summary:
            summary = conversation.summary
        self.canvas.create_text(
            left + 28,
            top + 30,
            anchor="w",
            text=title,
            fill="#d6c9bb",
            font=("Segoe UI Semibold", 11),
        )
        self.canvas.create_text(
            left + 28,
            top + 78,
            anchor="nw",
            width=right - left - 56,
            text="Это не лента сообщений. Здесь остаётся текущий разговор, пока пространство вокруг меняется.",
            fill="#eef0f2",
            font=("Segoe UI", 13),
        )
        self.canvas.create_text(
            left + 28,
            bottom - 72,
            anchor="nw",
            width=right - left - 56,
            text=summary,
            fill="#92a2b1",
            font=("Segoe UI", 10),
        )
        self.canvas.create_line(
            left + 28,
            bottom - 26,
            right - 28,
            bottom - 26,
            fill="#687684",
            width=2,
        )
        self.canvas.create_text(
            left + 28,
            bottom - 36,
            anchor="sw",
            text="Скажи что-нибудь…",
            fill="#b7c0c8",
            font=("Segoe UI", 11),
        )
        self._actions.append(((left, top, right, bottom), self.controller.conversation_next))

    def _draw_masha(self, scene: TierZeroScene, width: int, height: int) -> None:
        cx = int(width * 0.69)
        head_y = int(height * 0.31)
        stopped = "остановлена" in scene.safety_label.casefold()
        halo = "#6d565b" if stopped else "#796f5d"
        self.canvas.create_oval(
            cx - 150,
            head_y - 120,
            cx + 150,
            head_y + 270,
            fill=halo,
            outline="",
            stipple="gray50",
        )
        self.canvas.create_oval(
            cx - 82,
            head_y - 94,
            cx + 82,
            head_y + 72,
            fill="#b88b72",
            outline="#d5b49e",
            width=2,
        )
        self.canvas.create_arc(
            cx - 102,
            head_y - 110,
            cx + 102,
            head_y + 92,
            start=2,
            extent=176,
            style="pieslice",
            fill="#2a2021",
            outline="",
        )
        self.canvas.create_oval(cx - 36, head_y - 12, cx - 24, head_y, fill="#20252b", outline="")
        self.canvas.create_oval(cx + 24, head_y - 12, cx + 36, head_y, fill="#20252b", outline="")
        self.canvas.create_arc(
            cx - 32,
            head_y + 12,
            cx + 32,
            head_y + 52,
            start=200,
            extent=140,
            style="arc",
            outline="#5b3535",
            width=2,
        )
        self.canvas.create_polygon(
            cx - 118,
            head_y + 92,
            cx + 118,
            head_y + 92,
            cx + 158,
            head_y + 292,
            cx - 158,
            head_y + 292,
            fill="#252b32",
            outline="#727a83",
            width=2,
        )
        self.canvas.create_text(
            cx,
            head_y + 188,
            text=scene.presence_name,
            fill="#f0e9e1",
            font=("Segoe UI Semibold", 20),
        )
        state = f"{scene.pose_label} · {scene.expression_label}\n{scene.attention_label} · {scene.activity_label}"
        self.canvas.create_text(
            cx,
            head_y + 232,
            text=state,
            fill="#b7c0c8",
            justify="center",
            font=("Segoe UI", 9),
        )
        self.canvas.create_text(
            cx,
            head_y + 282,
            text=f"visual asset: {scene.asset_id}",
            fill="#7f8b95",
            font=("Consolas", 8),
        )
        if stopped:
            self.canvas.create_text(
                cx,
                head_y + 330,
                text="Я рядом. Автономные действия остановлены.",
                fill="#e5c7c7",
                font=("Segoe UI Semibold", 10),
            )

    def _draw_activity(self, scene: TierZeroScene, width: int, height: int) -> None:
        left = 42
        right = width - 42
        top = int(height * 0.78)
        bottom = height - 50
        self._rounded_rect(left, top, right, bottom, 18, fill="#1c2229", outline="#4f5d68")
        activity = scene.activities[-1] if scene.activities else None
        title = "АКТИВНОСТЬ"
        status = "Кликни, чтобы запустить локальный сценарий долгой задачи"
        progress = "queued → running → progress → completed"
        if activity is not None:
            title = f"{activity.title.upper()} · {activity.state}"
            status = activity.summary
            progress = activity.progress_label or "прогресс подтверждается runtime"
        self.canvas.create_text(
            left + 24,
            top + 24,
            anchor="w",
            text=title,
            fill="#d8c9b8",
            font=("Segoe UI Semibold", 10),
        )
        self.canvas.create_text(
            left + 24,
            top + 58,
            anchor="w",
            text=status,
            fill="#eef0f2",
            font=("Segoe UI", 11),
        )
        self.canvas.create_text(
            right - 24,
            top + 58,
            anchor="e",
            text=progress,
            fill="#8ea0ad",
            font=("Segoe UI", 9),
        )
        self._actions.append(((left, top, right, bottom), self.controller.activity_next))

    def _draw_footer(self, width: int, height: int) -> None:
        self.canvas.create_text(
            width / 2,
            height - 20,
            text="1 разговор   2 активность   3 инициатива   4 стоп   5 модель   6 runtime · или кликай по зонам",
            fill="#77838e",
            font=("Segoe UI", 8),
        )

    def _draw_privacy(self, width: int, height: int) -> None:
        self.canvas.create_rectangle(
            0,
            0,
            width,
            height,
            fill="#101319",
            outline="",
            stipple="gray50",
        )
        self.canvas.create_text(
            width / 2,
            height / 2,
            text="ДОМ В ДИСКРЕТНОМ РЕЖИМЕ\nВерни фокус окну, чтобы показать личный контекст",
            fill="#e4ded7",
            justify="center",
            font=("Segoe UI Semibold", 14),
        )

    def _click(self, event) -> None:
        for (x1, y1, x2, y2), action in reversed(self._actions):
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                self._run(action)
                return

    def _run(self, action: Callable[[], object]) -> None:
        action()
        self.render()

    def _focus(self, focused: bool) -> None:
        if self.controller.model.window_state.value == ("focused" if focused else "unfocused"):
            return
        self.controller.window_focus(focused)
        self.render()

    def _rounded_rect(self, x1, y1, x2, y2, radius, **kwargs):
        points = [
            x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
            x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
            x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
        ]
        return self.canvas.create_polygon(points, smooth=True, **kwargs)

    @staticmethod
    def _mix(first: str, second: str, ratio: float) -> str:
        a = tuple(int(first[index:index + 2], 16) for index in (1, 3, 5))
        b = tuple(int(second[index:index + 2], 16) for index in (1, 3, 5))
        values = tuple(round(start + (end - start) * ratio) for start, end in zip(a, b))
        return "#" + "".join(f"{value:02x}" for value in values)


def main() -> None:
    TierZeroHomeWindow().run()


if __name__ == "__main__":
    main()
