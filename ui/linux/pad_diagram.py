"""Схема Xbox 360 / Series с живой подсветкой нажатий."""

from __future__ import annotations

import math
import time

import cairo
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from core.paths import asset_path

# Нормализованные координаты картинки 700×576.
# Исходная разметка была под 1024×576; холст обрезан по центру (по 162 px слева и справа).
# Радиус — доля ширины картинки.
Hotspot = tuple[float, float, float]

LAYOUTS: dict[str, dict[str, object]] = {
    "360": {
        "file": "xbox-360.png",
        "buttons": {
            0: (0.752, 0.444, 0.050),  # A
            1: (0.817, 0.361, 0.050),  # B
            2: (0.683, 0.368, 0.050),  # X
            3: (0.755, 0.292, 0.050),  # Y
            4: (0.266, 0.125, 0.061),  # LB
            5: (0.734, 0.125, 0.061),  # RB
            6: (0.424, 0.365, 0.032),  # View / Back
            7: (0.576, 0.365, 0.032),  # Menu / Start
            8: (0.500, 0.240, 0.056),  # Xbox
            9: (0.234, 0.340, 0.073),  # L3
            10: (0.654, 0.540, 0.073),  # R3
            11: (0.368, 0.478, 0.035),  # ↑
            12: (0.368, 0.628, 0.035),  # ↓
            13: (0.307, 0.548, 0.035),  # ←
            14: (0.427, 0.548, 0.035),  # →
        },
        "left_stick": (0.234, 0.340, 0.080),
        "right_stick": (0.654, 0.540, 0.080),
        "lt": (0.164, 0.155, 0.059),
        "rt": (0.836, 0.155, 0.059),
        "dpad": (0.368, 0.548, 0.076),
    },
    "series": {
        "file": "xbox-series.png",
        "buttons": {
            0: (0.752, 0.444, 0.050),  # A
            1: (0.820, 0.361, 0.050),  # B
            2: (0.683, 0.368, 0.050),  # X
            3: (0.755, 0.292, 0.050),  # Y
            4: (0.266, 0.125, 0.061),  # LB
            5: (0.734, 0.125, 0.061),  # RB
            6: (0.424, 0.365, 0.032),  # View
            7: (0.576, 0.365, 0.032),  # Menu
            8: (0.500, 0.240, 0.056),  # Xbox
            9: (0.234, 0.340, 0.073),  # L3
            10: (0.646, 0.530, 0.073),  # R3
            11: (0.368, 0.478, 0.035),  # ↑
            12: (0.368, 0.628, 0.035),  # ↓
            13: (0.307, 0.548, 0.035),  # ←
            14: (0.427, 0.548, 0.035),  # →
            15: (0.500, 0.436, 0.026),  # Share
        },
        "left_stick": (0.234, 0.340, 0.080),
        "right_stick": (0.646, 0.530, 0.080),
        "lt": (0.164, 0.155, 0.059),
        "rt": (0.836, 0.155, 0.059),
        "dpad": (0.368, 0.548, 0.076),
    },
}

IMAGE_SIZE = (700, 576)
GREEN = (0.06, 0.82, 0.18)
RED = (0.77, 0.17, 0.11)


class PadDiagram(Gtk.DrawingArea):
    def __init__(self) -> None:
        super().__init__()
        self.add_css_class("pad-diagram")
        self.set_hexpand(True)
        self.set_content_width(IMAGE_SIZE[0])
        self.set_content_height(IMAGE_SIZE[1])
        self.set_draw_func(self._draw)
        self._surfaces: dict[str, cairo.ImageSurface] = {}
        self._kind = "series"
        self._connected = False
        self._buttons: dict[int, bool] = {}
        self._left = (0.0, 0.0)
        self._right = (0.0, 0.0)
        self._lt = 0.0
        self._rt = 0.0
        self._focus = ""
        self._trail_left: list[tuple[float, float]] = []
        self._trail_right: list[tuple[float, float]] = []
        self._failed: set[int] = set()
        self._pulse = 0.0
        self._load("series")
        self._load("360")

    def _load(self, kind: str) -> None:
        path = asset_path(str(LAYOUTS[kind]["file"]))
        if not path.is_file() or kind in self._surfaces:
            return
        try:
            self._surfaces[kind] = cairo.ImageSurface.create_from_png(str(path))
        except cairo.Error:
            pass

    def set_kind(self, kind: str) -> None:
        if kind not in LAYOUTS:
            kind = "series"
        if kind != self._kind:
            self._kind = kind
            self.queue_draw()

    def set_focus(self, focus: str) -> None:
        if focus != self._focus:
            stick_focus = focus == "left" or focus.startswith("left_") or focus == "right" or focus.startswith("right_")
            if not stick_focus:
                self._trail_left = []
                self._trail_right = []
            elif focus == "left" or focus.startswith("left_"):
                self._trail_right = []
            elif focus == "right" or focus.startswith("right_"):
                self._trail_left = []
            self._focus = focus
            self.queue_draw()

    def clear_trails(self) -> None:
        self._trail_left = []
        self._trail_right = []
        self.queue_draw()

    def update(
        self,
        *,
        connected: bool,
        kind: str,
        buttons: dict[int, bool],
        left: tuple[float, float],
        right: tuple[float, float],
        lt: float,
        rt: float,
        trail: bool = False,
        failed: set[int] | None = None,
    ) -> None:
        self._connected = connected
        self.set_kind(kind)
        self._buttons = {int(k): bool(v) for k, v in buttons.items()}
        self._left = left
        self._right = right
        self._lt = lt
        self._rt = rt
        self._failed = {int(i) for i in (failed or set())}
        self._pulse = time.monotonic()
        if trail and (self._focus == "left" or self._focus.startswith("left_")):
            self._trail_left.append(left)
            self._trail_left = self._trail_left[-500:]
        if trail and (self._focus == "right" or self._focus.startswith("right_")):
            self._trail_right.append(right)
            self._trail_right = self._trail_right[-500:]
        self.queue_draw()

    def image_size(self) -> tuple[int, int]:
        surface = self._surfaces.get(self._kind)
        if surface is not None:
            width, height = surface.get_width(), surface.get_height()
            if width > 0 and height > 0:
                return width, height
        return IMAGE_SIZE

    def _fitted(self, width: int, height: int) -> tuple[float, float, float, float]:
        iw, ih = self.image_size()
        scale = min(width / iw, height / ih) if iw and ih else 1.0
        dw, dh = iw * scale, ih * scale
        return (width - dw) / 2, (height - dh) / 2, dw, dh

    def _draw(self, _area, cr, width: int, height: int) -> None:
        cr.set_source_rgb(0.0, 0.0, 0.0)
        cr.paint()
        iw, ih = self.image_size()
        ox, oy, dw, dh = self._fitted(width, height)
        cr.save()
        cr.translate(ox, oy)
        cr.scale(dw / iw, dh / ih)
        surface = self._surfaces.get(self._kind)
        if surface is not None:
            cr.set_source_surface(surface, 0, 0)
            cr.paint()
        if not self._connected:
            cr.set_source_rgba(0.0, 0.0, 0.0, 0.55)
            cr.paint()
        self._paint_overlays(cr, iw, ih, LAYOUTS[self._kind])
        cr.restore()

    def _pressed(self, idx: int) -> bool:
        return bool(self._buttons.get(idx))

    def _paint_overlays(self, cr, iw: int, ih: int, layout: dict) -> None:
        buttons: dict[int, Hotspot] = layout["buttons"]  # type: ignore[assignment]

        def spot(nx: float, ny: float, nr: float) -> tuple[float, float, float]:
            return nx * iw, ny * ih, nr * iw

        focus = self._focus
        if focus == "left" or focus.startswith("left_"):
            self._ring(cr, *spot(*layout["left_stick"]))  # type: ignore[arg-type]
        if focus == "right" or focus.startswith("right_"):
            self._ring(cr, *spot(*layout["right_stick"]))  # type: ignore[arg-type]
        if focus == "lt":
            self._ring(cr, *spot(*layout["lt"]))  # type: ignore[arg-type]
        if focus == "rt":
            self._ring(cr, *spot(*layout["rt"]))  # type: ignore[arg-type]
        if focus == "dpad":
            self._ring(cr, *spot(*layout["dpad"]))  # type: ignore[arg-type]
        if focus.startswith("btn:"):
            try:
                idx = int(focus.split(":", 1)[1])
            except ValueError:
                idx = -1
            if idx in buttons:
                self._ring(cr, *spot(*buttons[idx]))

        pulse = 1.0 + 0.18 * abs(math.sin(self._pulse * 8.0))
        for idx, (nx, ny, nr) in buttons.items():
            if idx in self._failed:
                self._glow(cr, *spot(nx, ny, nr * pulse), RED)
            elif self._pressed(idx):
                self._glow(cr, *spot(nx, ny, nr * pulse), GREEN)

        self._trigger_fill(cr, *spot(*layout["lt"]), self._lt)  # type: ignore[arg-type]
        self._trigger_fill(cr, *spot(*layout["rt"]), self._rt)  # type: ignore[arg-type]

        lx, ly, lr = spot(*layout["left_stick"])  # type: ignore[arg-type]
        rx, ry, rr = spot(*layout["right_stick"])  # type: ignore[arg-type]
        left_on = focus == "left" or focus.startswith("left_")
        right_on = focus == "right" or focus.startswith("right_")
        self._stick(cr, lx, ly, lr, self._left, self._trail_left, active=left_on)
        self._stick(cr, rx, ry, rr, self._right, self._trail_right, active=right_on)

    def _glow(self, cr, x: float, y: float, r: float, color: tuple[float, float, float] = GREEN) -> None:
        cr.set_source_rgba(*color, 0.28)
        cr.arc(x, y, r * 2.1, 0, math.tau)
        cr.fill()
        cr.set_source_rgba(*color, 0.85)
        cr.arc(x, y, r * 1.25, 0, math.tau)
        cr.fill()
        cr.set_source_rgba(min(1.0, color[0] + 0.7), min(1.0, color[1] + 0.25), min(1.0, color[2] + 0.25), 1.0)
        cr.set_line_width(max(3.0, r * 0.22))
        cr.arc(x, y, r * 1.05, 0, math.tau)
        cr.stroke()
        cr.set_source_rgba(1, 1, 1, 0.95)
        cr.arc(x, y, max(4.0, r * 0.28), 0, math.tau)
        cr.fill()

    def _ring(self, cr, x: float, y: float, r: float) -> None:
        cr.set_source_rgba(*GREEN, 0.14)
        cr.arc(x, y, r * 1.55, 0, math.tau)
        cr.fill()
        cr.set_source_rgba(*GREEN, 0.28)
        cr.arc(x, y, r * 1.28, 0, math.tau)
        cr.fill()
        cr.set_source_rgba(*GREEN, 0.95)
        cr.set_line_width(2.4)
        cr.arc(x, y, r * 1.18, 0, math.tau)
        cr.stroke()

    def _trigger_fill(self, cr, x: float, y: float, r: float, value: float) -> None:
        if value <= 0.02:
            return
        cr.set_source_rgba(*GREEN, 0.25 + 0.55 * value)
        cr.arc(x, y, r * (0.55 + 0.7 * value), 0, math.tau)
        cr.fill()

    def _stick(
        self,
        cr,
        cx: float,
        cy: float,
        radius: float,
        pos: tuple[float, float],
        trail: list[tuple[float, float]],
        *,
        active: bool,
    ) -> None:
        for px, py in trail[-500:]:
            cr.set_source_rgba(*GREEN, 0.35)
            cr.arc(cx + px * radius, cy + py * radius, 2.2, 0, math.tau)
            cr.fill()
        moved = abs(pos[0]) > 0.08 or abs(pos[1]) > 0.08
        if not active and not trail and not moved:
            return
        if active:
            cr.set_source_rgba(*GREEN, 0.16)
            cr.arc(cx, cy, radius * 1.2, 0, math.tau)
            cr.fill()
        x = cx + max(-1.0, min(1.0, pos[0])) * radius
        y = cy + max(-1.0, min(1.0, pos[1])) * radius
        knob = 9.0 if active else 6.0
        cr.set_source_rgba(*GREEN, 0.95 if active else 0.45)
        cr.arc(x, y, knob, 0, math.tau)
        cr.fill()
        if active:
            cr.set_source_rgba(1, 1, 1, 0.95)
            cr.arc(x, y, 3.0, 0, math.tau)
            cr.fill()
