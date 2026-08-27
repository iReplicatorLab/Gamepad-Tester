"""Shared GTK widgets."""

from __future__ import annotations

import math

import cairo
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from core.i18n import t
from pad_common import diagram_kind, normalize_trigger
from ui.linux.pad_diagram import PadDiagram


class PadButton(Gtk.Box):
    def __init__(self, label: str, css_class: str = "pad-btn") -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        for cls in css_class.split():
            self.add_css_class(cls)
        self._label = Gtk.Label(label=label)
        self.append(self._label)
        self._mark = Gtk.Label()
        self._mark.add_css_class("pad-btn-mark")
        self._mark.set_visible(False)
        self.append(self._mark)

    def set_active(self, active: bool) -> None:
        if active:
            self.add_css_class("pressed")
        else:
            self.remove_css_class("pressed")

    def set_focused(self, focused: bool) -> None:
        if focused:
            self.add_css_class("focused")
        else:
            self.remove_css_class("focused")

    def set_failed(self, failed: bool) -> None:
        if failed:
            self.add_css_class("failed")
            self._mark.set_label("!")
            self._mark.set_visible(True)
        else:
            self.remove_css_class("failed")
            if self._mark.get_label() == "!":
                self._mark.set_visible(False)
                self._mark.set_label("")

    def set_passed(self, passed: bool) -> None:
        if passed and not self.has_css_class("failed"):
            self.add_css_class("passed")
            self._mark.set_label("✓")
            self._mark.set_visible(True)
        else:
            self.remove_css_class("passed")
            if self._mark.get_label() == "✓":
                self._mark.set_visible(False)
                self._mark.set_label("")


class DpadWidget(Gtk.Box):
    """Крестовина рядом с левым стиком."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.add_css_class("analog-panel")
        self.add_css_class("analog-panel-left")
        self.add_css_class("dpad-panel")
        self._title = Gtk.Label(label=t("stick.dpad"), css_classes=["caption", "dim-label"], halign=Gtk.Align.START)
        self.append(self._title)
        grid = Gtk.Grid(column_spacing=4, row_spacing=4, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self.buttons: dict[int, PadButton] = {}
        for idx, name, col, row in (
            (11, "↑", 1, 0),
            (13, "←", 0, 1),
            (14, "→", 2, 1),
            (12, "↓", 1, 2),
        ):
            btn = PadButton(name, css_class="pad-btn dpad")
            self.buttons[idx] = btn
            grid.attach(btn, col, row, 1, 1)
        self.append(grid)

    def set_highlight(self, active: bool) -> None:
        if active:
            self.add_css_class("focused")
        else:
            self.remove_css_class("focused")

    def retranslate(self) -> None:
        self._title.set_label(t("stick.dpad"))


class StickWidget(Gtk.Box):
    def __init__(self, title: str, side: str, trigger_name: str) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.add_css_class("analog-panel")
        self.add_css_class(f"analog-panel-{side}")
        self._trigger_name = trigger_name
        self._title = Gtk.Label(label=title, css_classes=["caption", "dim-label"], halign=Gtk.Align.START)
        self.append(self._title)
        self._hint = Gtk.Label(wrap=True, xalign=0)
        self._hint.set_width_chars(16)
        self._hint.set_max_width_chars(24)
        self._hint.add_css_class("stick-hint")
        self._hint.set_visible(False)
        self.append(self._hint)
        self._x = 0.0
        self._y = 0.0
        self._trail: list[tuple[float, float]] = []
        self._area = Gtk.DrawingArea()
        self._area.add_css_class("stick-area")
        self._area.set_content_width(96)
        self._area.set_content_height(96)
        self._area.set_halign(Gtk.Align.CENTER)
        self._area.set_draw_func(self._draw_stick)
        self.append(self._area)
        self._trig = Gtk.ProgressBar()
        self._trig.add_css_class("trigger-bar")
        self._trig.set_show_text(True)
        self._trig.set_hexpand(True)
        self.append(self._trig)
        self.set_trigger(0.0)

    def _draw_stick(self, _area, context, width, height) -> None:
        cx, cy = width / 2, height / 2
        radius = min(width, height) * 0.42
        context.set_source_rgba(0.45, 0.45, 0.45, 0.25)
        context.set_line_width(1.2)
        context.arc(cx, cy, radius, 0, 6.28318)
        context.stroke()
        context.set_source_rgba(0.45, 0.45, 0.45, 0.12)
        context.arc(cx, cy, radius * 0.08, 0, 6.28318)
        context.fill()
        for x, y in self._trail[-500:]:
            context.set_source_rgba(0.06, 0.49, 0.06, 0.35)
            context.arc(cx + x * radius, cy + y * radius, 2.0, 0, 6.28318)
            context.fill()
        context.set_source_rgba(0.06, 0.49, 0.06, 1.0)
        context.arc(cx + self._x * radius, cy + self._y * radius, 8, 0, 6.28318)
        context.fill()

    def set_position(self, x: float, y: float, *, trail: bool = False) -> None:
        self._x = max(-1.0, min(1.0, x))
        self._y = max(-1.0, min(1.0, y))
        if trail:
            self._trail.append((self._x, self._y))
            if len(self._trail) > 600:
                self._trail = self._trail[-500:]
        self._area.queue_draw()

    def set_trail(self, points: list[tuple[float, float]]) -> None:
        self._trail = points[-500:]
        self._area.queue_draw()

    def clear_trail(self) -> None:
        self._trail = []
        self._area.queue_draw()

    def set_trigger(self, value: float) -> None:
        clamped = max(0.0, min(1.0, value))
        self._trig.set_fraction(clamped)
        self._trig.set_text(f"{self._trigger_name} {int(clamped * 100)}%")

    def set_highlight(self, active: bool) -> None:
        if active:
            self.add_css_class("focused")
        else:
            self.remove_css_class("focused")

    def set_step_hint(self, text: str) -> None:
        self._hint.set_label(text)
        self._hint.set_visible(bool(text))

    def set_title(self, title: str) -> None:
        self._title.set_label(title)


class StickCue(Gtk.Box):
    """Круг со стрелкой направления стика."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.set_halign(Gtk.Align.CENTER)
        self._motion = ""
        self._area = Gtk.DrawingArea()
        self._area.set_content_width(120)
        self._area.set_content_height(120)
        self._area.set_draw_func(self._draw)
        self._times = Gtk.Label()
        self._times.add_css_class("stick-cue-times")
        self._times.set_halign(Gtk.Align.CENTER)
        self._times.set_xalign(0.5)
        self.append(self._area)
        self.append(self._times)
        self.set_visible(False)

    def set_cue(self, motion: str, repeats: int = 0, hold_seconds: int = 0) -> None:
        self._motion = motion
        if repeats > 1:
            text = f"×{repeats}"
        elif hold_seconds > 0 and motion in ("up", "down", "left", "right", "circle"):
            text = f"{hold_seconds}s"
        else:
            text = ""
        self._times.set_label(text)
        self._times.set_visible(bool(text))
        self.set_visible(bool(motion))
        self._area.queue_draw()

    def _draw(self, _area, cr, width: int, height: int) -> None:
        cx, cy = width / 2, height / 2
        radius = min(width, height) * 0.38
        cr.set_source_rgb(0.09, 0.78, 0.07)
        cr.set_line_width(2.2)
        cr.arc(cx, cy, radius, 0, math.tau)
        cr.stroke()
        motion = self._motion
        if motion in ("up", "down", "left", "right"):
            angle = {"up": -math.pi / 2, "down": math.pi / 2, "left": math.pi, "right": 0.0}[motion]
            self._arrow(cr, cx, cy, radius * 0.82, angle)
        elif motion == "circle":
            cr.set_line_width(2.2)
            cr.arc(cx, cy, radius * 0.55, 0.4, math.tau - 0.9)
            cr.stroke()
            tip = 0.4
            tx = cx + radius * 0.55 * math.cos(tip)
            ty = cy + radius * 0.55 * math.sin(tip)
            self._arrowhead(cr, tx, ty, tip + math.pi / 2, 12)
        cr.arc(cx, cy, 5.5, 0, math.tau)
        cr.fill()

    def _arrow(self, cr, cx: float, cy: float, length: float, angle: float) -> None:
        cr.set_line_width(2.4)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        dx, dy = math.cos(angle), math.sin(angle)
        cr.move_to(cx + dx * 8.0, cy + dy * 8.0)
        cr.line_to(cx + dx * length, cy + dy * length)
        cr.stroke()
        self._arrowhead(cr, cx + dx * length, cy + dy * length, angle, 14)

    @staticmethod
    def _arrowhead(cr, x: float, y: float, angle: float, size: float) -> None:
        cr.move_to(x, y)
        cr.line_to(
            x - size * math.cos(angle - 0.55),
            y - size * math.sin(angle - 0.55),
        )
        cr.line_to(
            x - size * math.cos(angle + 0.55),
            y - size * math.sin(angle + 0.55),
        )
        cr.close_path()
        cr.fill()


class LivePad(Gtk.Box):
    """Живая схема Xbox 360 / Series, индикаторы кнопок и триггеры."""

    def __init__(self, *, compact: bool = False) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._focus = ""
        self._compact = compact
        self._show_telem = False
        self._deadzone = 0.05
        self._rumble_cb = None
        self._rumble_left = 0.8
        self._rumble_right = 0.8
        self._rumble_ms = 1000

        stage = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        stage.add_css_class("pad-stage")
        left_col, right_col, self.buttons = build_side_buttons()
        left_col.set_valign(Gtk.Align.CENTER)
        right_col.set_valign(Gtk.Align.CENTER)
        stage.append(left_col)

        center = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        center.set_hexpand(True)
        self._device_title = Gtk.Label()
        self._device_title.add_css_class("pad-device-name")
        self._device_title.set_halign(Gtk.Align.FILL)
        self._device_title.set_hexpand(True)
        self._device_title.set_xalign(0.5)
        self._device_title.set_ellipsize(Pango.EllipsizeMode.END)
        self._device_title.set_max_width_chars(42)
        center.append(self._device_title)

        mid = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._lt_col, self._lt, self._lt_value = self._trigger_column("LT")
        self._rt_col, self._rt, self._rt_value = self._trigger_column("RT")
        self._cue_left = StickCue()
        self._cue_right = StickCue()
        self._rumble_l = self._rumble_button("l")
        self._rumble_r = self._rumble_button("r")
        left_motor = self._motor_rail(self._cue_left, self._rumble_l, "l")
        right_motor = self._motor_rail(self._cue_right, self._rumble_r, "r")
        mid.append(self._lt_col)
        mid.append(left_motor)

        self._diagram = PadDiagram()
        overlay = Gtk.Overlay()
        overlay.set_hexpand(True)
        overlay.set_child(self._diagram)
        self._timer_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._timer_box.add_css_class("hold-timer-box")
        self._timer_box.set_halign(Gtk.Align.CENTER)
        self._timer_box.set_valign(Gtk.Align.CENTER)
        self._timer_box.set_can_target(False)
        self._timer_value = Gtk.Label(label="")
        self._timer_value.add_css_class("hold-timer")
        self._timer_caption = Gtk.Label(label="")
        self._timer_caption.add_css_class("hold-timer-caption")
        self._timer_box.append(self._timer_value)
        self._timer_box.append(self._timer_caption)
        overlay.add_overlay(self._timer_box)
        self._timer_box.set_visible(False)
        self._telem_left = self._stick_telem("left")
        self._telem_right = self._stick_telem("right")
        overlay.add_overlay(self._telem_left["box"])
        overlay.add_overlay(self._telem_right["box"])
        self._rumble_lr = self._rumble_button("lr")
        self._rumble_lr.set_halign(Gtk.Align.CENTER)
        self._rumble_lr.set_valign(Gtk.Align.END)
        self._rumble_lr.set_margin_bottom(10)
        overlay.add_overlay(self._rumble_lr)
        mid.append(overlay)
        mid.append(right_motor)
        mid.append(self._rt_col)
        center.append(mid)
        self.set_compact(compact)
        stage.append(center)
        stage.append(right_col)
        self.append(stage)
        self.set_trigger("LT", 0.0)
        self.set_trigger("RT", 0.0)

    @staticmethod
    def _trigger_column(name: str):
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        col.add_css_class("trigger-col")
        col.set_valign(Gtk.Align.CENTER)
        lab = Gtk.Label(label=name)
        lab.add_css_class("trigger-label")
        bar = Gtk.ProgressBar()
        bar.add_css_class("trigger-bar")
        bar.add_css_class("vertical")
        bar.set_orientation(Gtk.Orientation.VERTICAL)
        bar.set_inverted(True)
        bar.set_show_text(False)
        bar.set_valign(Gtk.Align.FILL)
        bar.set_vexpand(False)
        val = Gtk.Label()
        val.add_css_class("trigger-value")
        val.set_width_chars(4)
        val.set_max_width_chars(4)
        val.set_xalign(0.5)
        val.set_halign(Gtk.Align.CENTER)
        col.append(lab)
        col.append(val)
        col.append(bar)
        return col, bar, val

    @staticmethod
    def _stick_telem(side: str) -> dict:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        box.add_css_class("stick-telem")
        box.set_halign(Gtk.Align.START if side == "left" else Gtk.Align.END)
        box.set_valign(Gtk.Align.START)
        box.set_margin_top(8)
        box.set_margin_start(8 if side == "left" else 0)
        box.set_margin_end(8 if side == "right" else 0)
        box.set_can_target(False)
        title = Gtk.Label(xalign=0)
        title.add_css_class("telem-title")
        x_lab = Gtk.Label(xalign=0)
        x_lab.add_css_class("telem-mono")
        y_lab = Gtk.Label(xalign=0)
        y_lab.add_css_class("telem-mono")
        flags = Gtk.Label(xalign=0)
        flags.add_css_class("telem-ok")
        box.append(title)
        box.append(x_lab)
        box.append(y_lab)
        box.append(flags)
        box.set_visible(False)
        return {"box": box, "title": title, "x": x_lab, "y": y_lab, "flags": flags}

    def _motor_rail(self, cue: Gtk.Widget, rumble: Gtk.Widget, side: str) -> Gtk.Box:
        rail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        rail.set_valign(Gtk.Align.FILL)
        overlay = Gtk.Overlay()
        overlay.set_valign(Gtk.Align.FILL)
        overlay.set_vexpand(True)
        overlay.set_size_request(56, -1)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        col.set_valign(Gtk.Align.FILL)
        col.set_vexpand(True)
        spacer = Gtk.Box()
        spacer.set_vexpand(True)
        rumble.set_halign(Gtk.Align.CENTER)
        rumble.set_valign(Gtk.Align.END)
        rumble.set_margin_bottom(2)
        col.append(spacer)
        col.append(rumble)
        overlay.set_child(col)
        cue.set_halign(Gtk.Align.CENTER)
        cue.set_valign(Gtk.Align.START)
        cue.set_margin_top(8)
        overlay.add_overlay(cue)
        rail.append(overlay)
        rail.append(self._rumble_scale(side))
        return rail

    def _rumble_scale(self, side: str) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_halign(Gtk.Align.CENTER)
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        scale.set_value(80)
        scale.set_draw_value(False)
        scale.set_size_request(60, -1)
        scale.set_hexpand(False)
        scale.add_css_class("rumble-scale")
        value = Gtk.Label(label="80%")
        value.add_css_class("rumble-power-value")
        value.set_halign(Gtk.Align.CENTER)
        value.set_xalign(0.5)
        scale.connect("value-changed", self._on_rumble_scale, side, value)
        box.append(scale)
        box.append(value)
        return box

    def _on_rumble_scale(self, scale: Gtk.Scale, side: str, value_label: Gtk.Label) -> None:
        pct = int(round(scale.get_value()))
        value_label.set_label(f"{pct}%")
        self.set_rumble_power(
            left=pct / 100.0 if side == "l" else None,
            right=pct / 100.0 if side == "r" else None,
        )

    def _rumble_button(self, key: str) -> Gtk.Button:
        btn = Gtk.Button(label=t(f"monitor.rumble_{key}"))
        btn.add_css_class("rumble-btn")
        motors = {"l": (1.0, 0.0), "r": (0.0, 1.0), "lr": (1.0, 1.0)}[key]
        btn.connect("clicked", self._on_rumble, *motors)
        return btn

    def set_rumble_handler(self, cb) -> None:
        self._rumble_cb = cb

    def set_rumble_power(self, left: float | None = None, right: float | None = None) -> None:
        if left is not None:
            self._rumble_left = max(0.0, min(1.0, left))
        if right is not None:
            self._rumble_right = max(0.0, min(1.0, right))

    def _on_rumble(self, btn: Gtk.Button, left: float, right: float) -> None:
        btn.add_css_class("active")
        if self._rumble_cb:
            self._rumble_cb(left * self._rumble_left, right * self._rumble_right, self._rumble_ms)
        GLib.timeout_add(900, lambda: (btn.remove_css_class("active") or False))

    def set_compact(self, compact: bool) -> None:
        self._compact = compact
        iw, ih = self._diagram.image_size()
        scale = 0.58 if compact else 0.85
        self._diagram.set_content_width(max(1, round(iw * scale)))
        self._diagram.set_content_height(max(1, round(ih * scale)))
        bar_h = 225 if compact else 300
        if hasattr(self, "_lt"):
            self._lt.set_size_request(10, bar_h)
            self._rt.set_size_request(10, bar_h)

    def set_telemetry_enabled(self, enabled: bool) -> None:
        self._show_telem = enabled
        if not enabled:
            self._telem_left["box"].set_visible(False)
            self._telem_right["box"].set_visible(False)

    def set_deadzone(self, value: float) -> None:
        self._deadzone = max(0.0, min(0.5, value))

    def set_trigger(self, name: str, value: float) -> None:
        clamped = max(0.0, min(1.0, value))
        bar = self._lt if name == "LT" else self._rt
        label = self._lt_value if name == "LT" else self._rt_value
        bar.set_fraction(clamped)
        label.set_label(f"{int(clamped * 100)}%")

    def set_hold_timer(self, remaining: float | None, total: float = 0.0) -> None:
        del total
        if remaining is None or remaining <= 0:
            self._timer_box.set_visible(False)
            return
        shown = max(1, math.ceil(remaining - 1e-6))
        self._timer_value.set_label(str(shown))
        self._timer_caption.set_label(t("diag.hold_seconds").upper())
        self._timer_box.set_visible(True)

    def set_stick_cue(
        self, side: str, motion: str, repeats: int = 0, hold_seconds: int = 0
    ) -> None:
        left = side == "left"
        right = side == "right"
        self._cue_left.set_cue(
            motion if left else "",
            repeats if left else 0,
            hold_seconds if left else 0,
        )
        self._cue_right.set_cue(
            motion if right else "",
            repeats if right else 0,
            hold_seconds if right else 0,
        )

    def set_instruction(self, text: str, focus: str = "") -> None:
        self.set_focus(focus)

    def set_focus(self, focus: str) -> None:
        self._focus = focus
        self._diagram.set_focus(focus)

    def update(self, state, profile, *, trail: bool = False, failed: set[int] | None = None, passed: set[int] | None = None) -> None:
        kind = diagram_kind(getattr(profile, "name", ""), state.name)
        if state.connected:
            extra = f" · {state.axis_profile}" if state.axis_profile else ""
            self._device_title.set_label(f"{state.name}{extra}")
        else:
            self._device_title.set_label(state.hint or t("status.waiting"))
        axes = profile.read(state.axes) if state.connected else {
            "left_x": 0.0,
            "left_y": 0.0,
            "right_x": 0.0,
            "right_y": 0.0,
            "lt": -1.0,
            "rt": -1.0,
        }
        lt = normalize_trigger(axes["lt"]) if state.connected else 0.0
        rt = normalize_trigger(axes["rt"]) if state.connected else 0.0
        left = (axes["left_x"], axes["left_y"])
        right = (axes["right_x"], axes["right_y"])
        self._diagram.update(
            connected=state.connected,
            kind=kind,
            buttons=state.buttons,
            left=left,
            right=right,
            lt=lt,
            rt=rt,
            trail=trail,
            failed=failed or set(),
        )
        failed_set = failed or set()
        passed_set = passed or set()
        for idx, btn in self.buttons.items():
            btn.set_active(bool(state.buttons.get(idx)))
            btn.set_focused(self._focus == f"btn:{idx}")
            btn.set_failed(idx in failed_set)
            btn.set_passed(idx in passed_set and idx not in failed_set)
        share = self.buttons.get(15)
        if share is not None:
            share.set_visible(kind != "360")
        self.set_trigger("LT", lt)
        self.set_trigger("RT", rt)
        self._update_telemetry(left, right)

    def _update_telemetry(self, left: tuple[float, float], right: tuple[float, float]) -> None:
        focus = self._focus
        show_left = self._show_telem and (focus == "left" or focus.startswith("left_"))
        show_right = self._show_telem and (focus == "right" or focus.startswith("right_"))
        self._fill_telem(self._telem_left, t("telem.left_stick"), left, show_left)
        self._fill_telem(self._telem_right, t("telem.right_stick"), right, show_right)

    def _fill_telem(self, widgets: dict, title: str, pos: tuple[float, float], show: bool) -> None:
        widgets["box"].set_visible(show)
        if not show:
            return
        x, y = pos
        r = (x * x + y * y) ** 0.5
        widgets["title"].set_label(title)
        widgets["x"].set_label(f"X  {x:+.3f}")
        widgets["y"].set_label(f"Y  {y:+.3f}")
        center = "✓" if r < 0.08 else "—"
        widgets["flags"].set_label(f"{t('telem.center')} {center}")

    def retranslate(self) -> None:
        self._rumble_l.set_label(t("monitor.rumble_l"))
        self._rumble_r.set_label(t("monitor.rumble_r"))
        self._rumble_lr.set_label(t("monitor.rumble_lr"))


def _pad_button(idx: int, name: str) -> PadButton:
    if idx < 4:
        css = "pad-btn face"
    elif idx < 6:
        css = "pad-btn bumper"
    elif idx >= 11:
        css = "pad-btn dpad"
    else:
        css = "pad-btn"
    return PadButton(name, css_class=css)


def _cluster(items: list[tuple[int, str, int, int]], buttons: dict[int, PadButton]) -> Gtk.Grid:
    grid = Gtk.Grid(column_spacing=4, row_spacing=4, halign=Gtk.Align.CENTER)
    for idx, name, col, row in items:
        btn = _pad_button(idx, name)
        buttons[idx] = btn
        grid.attach(btn, col, row, 1, 1)
    return grid


def build_side_buttons() -> tuple[Gtk.Box, Gtk.Box, dict[int, PadButton]]:
    buttons: dict[int, PadButton] = {}
    left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    left.add_css_class("pad-side")
    right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    right.add_css_class("pad-side")

    for idx, name in ((4, "LB"),):
        btn = _pad_button(idx, name)
        buttons[idx] = btn
        left.append(btn)
    left.append(
        _cluster(
            [
                (11, "↑", 1, 0),
                (13, "←", 0, 1),
                (14, "→", 2, 1),
                (12, "↓", 1, 2),
            ],
            buttons,
        )
    )
    for idx, name in ((6, "View"), (8, "Xbox"), (9, "L3")):
        btn = _pad_button(idx, name)
        buttons[idx] = btn
        left.append(btn)

    for idx, name in ((5, "RB"),):
        btn = _pad_button(idx, name)
        buttons[idx] = btn
        right.append(btn)
    right.append(
        _cluster(
            [
                (3, "Y", 1, 0),
                (2, "X", 0, 1),
                (1, "B", 2, 1),
                (0, "A", 1, 2),
            ],
            buttons,
        )
    )
    for idx, name in ((7, "Menu"), (15, "Share"), (10, "R3")):
        btn = _pad_button(idx, name)
        buttons[idx] = btn
        right.append(btn)
    return left, right, buttons
