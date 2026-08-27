"""Вкладка «Диагностика»."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

from core.config import DiagnosticConfig
from core.i18n import t
from core.report import DiagnosticReport, result_lines
from core.session import DiagnosticSession
from core.status import TestStatus
from ui.linux.widgets import LivePad


class DiagnosticsView(Gtk.Box):
    def __init__(self, backend, config: DiagnosticConfig, on_open_report=None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_margin_top(6)
        self.set_margin_bottom(8)
        self._backend = backend
        self._config = config
        self._on_open_report = on_open_report
        self._session = DiagnosticSession(config, backend)
        self._session.set_update_callback(self._on_session_update)
        self._stop_btn: Gtk.Button | None = None
        self._check_btns: dict[str, Gtk.Button] = {}
        self._build()

    def _build(self) -> None:
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self._full_btn = Gtk.Button()
        self._full_btn.add_css_class("primary-btn")
        self._full_btn.connect("clicked", lambda *_: self._start(["sticks", "triggers", "buttons"]))
        actions.append(self._full_btn)
        chips = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        chips.set_valign(Gtk.Align.CENTER)
        for key, tests in (
            ("sticks", ["sticks"]),
            ("triggers", ["triggers"]),
            ("buttons", ["buttons"]),
        ):
            btn = Gtk.Button()
            btn.add_css_class("check-chip")
            btn.connect("clicked", lambda _b, names=tests: self._start(names))
            self._check_btns[key] = btn
            chips.append(btn)
        actions.append(chips)
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        actions.append(spacer)
        self._stop_btn = Gtk.Button()
        self._stop_btn.add_css_class("stop-btn")
        self._stop_btn.connect("clicked", lambda *_: self._session.stop())
        self._stop_btn.set_visible(False)
        actions.append(self._stop_btn)
        self._report_btn = Gtk.Button()
        self._report_btn.add_css_class("primary-btn")
        self._report_btn.connect("clicked", self._open_report)
        self._report_btn.set_visible(False)
        actions.append(self._report_btn)
        self.append(actions)

        self._step_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._step_card.add_css_class("step-card")
        self._step_card.add_css_class("idle")
        self._step_kicker = Gtk.Label(xalign=0.5)
        self._step_kicker.add_css_class("step-kicker")
        self._step_kicker.set_halign(Gtk.Align.CENTER)
        instr_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self._step_label = Gtk.Label(wrap=True, xalign=0.5)
        self._step_label.set_max_width_chars(64)
        self._step_label.set_justify(Gtk.Justification.CENTER)
        self._step_label.add_css_class("step-text")
        self._step_label.set_hexpand(True)
        self._skip_btn = Gtk.Button()
        self._skip_btn.add_css_class("ghost-btn")
        self._skip_btn.connect("clicked", lambda *_: self._session.skip())
        self._skip_btn.set_visible(False)
        self._skip_btn.set_valign(Gtk.Align.CENTER)
        instr_row.append(self._step_label)
        instr_row.append(self._skip_btn)
        self._step_state = Gtk.Label(xalign=0.5)
        self._step_state.add_css_class("step-state")
        self._step_state.set_halign(Gtk.Align.CENTER)
        self._step_state.add_css_class("idle")
        self._step_card.append(self._step_kicker)
        self._step_card.append(instr_row)
        self._step_card.append(self._step_state)
        self.append(self._step_card)

        self._pad = LivePad(compact=True)
        self._pad.set_telemetry_enabled(True)
        self._pad.set_rumble_handler(self._rumble)
        self.append(self._pad)

        result = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        result.add_css_class("result-card")
        self._result_card = result
        prog_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._prog_panel = prog_panel
        prog_head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._progress_title = Gtk.Label(xalign=0)
        self._progress_title.add_css_class("progress-caption")
        self._progress_title.set_hexpand(True)
        self._progress_count = Gtk.Label(xalign=1)
        self._progress_count.add_css_class("progress-count")
        prog_head.append(self._progress_title)
        prog_head.append(self._progress_count)
        prog_panel.append(prog_head)
        self._progress = Gtk.ProgressBar()
        self._progress.add_css_class("tech-progress")
        self._progress.set_show_text(False)
        self._progress.set_fraction(0)
        prog_panel.append(self._progress)
        prog_panel.set_visible(False)
        self._score_label = Gtk.Label(xalign=0)
        self._score_label.add_css_class("score-badge")
        self._score_label.set_visible(False)
        self._score_hint = Gtk.Label(wrap=True, xalign=0)
        self._score_hint.add_css_class("device-profile")
        self._score_hint.set_visible(False)
        self._result_label = Gtk.Label(wrap=True, xalign=0, selectable=True)
        self._result_label.add_css_class("device-profile")
        result.append(prog_panel)
        result.append(self._score_label)
        result.append(self._score_hint)
        result.append(self._result_label)
        result.set_visible(False)
        self.append(result)
        self.retranslate()

    def retranslate(self) -> None:
        self._full_btn.set_label("▶  " + t("diag.run_full"))
        self._check_btns["sticks"].set_label(t("diag.sticks"))
        self._check_btns["triggers"].set_label(t("diag.triggers"))
        self._check_btns["buttons"].set_label(t("diag.buttons"))
        if self._stop_btn is not None:
            self._stop_btn.set_label("■  " + t("diag.stop"))
        self._report_btn.set_label(t("diag.open_report"))
        self._skip_btn.set_label(t("diag.skip"))
        self._progress_title.set_label(t("diag.progress_title").upper())
        done, total = self._session.get_category_progress()
        self._progress_count.set_label(f"{done} / {total}")
        self._score_hint.set_label(t("diag.score_hint"))
        if not self._session.is_running():
            if self._diagnostics_finished():
                self._set_step_idle_done()
                self._report_btn.set_visible(True)
                self._update_result_card(self._session.get_results())
            else:
                self._set_step_idle()
                self._report_btn.set_visible(False)
                self._sync_footer_mode()
        else:
            self._sync_footer_mode()
        self._pad.retranslate()
        self._refresh_chips()

    def _set_step_idle(self) -> None:
        self._step_kicker.set_label(t("diag.step_idle_kicker"))
        self._step_label.set_label(t("diag.hint_idle"))
        self._step_state.set_visible(False)
        self._swap_card("idle")
        self._swap_state("idle")

    def _set_step_idle_done(self) -> None:
        done, total = self._session.get_category_progress()
        self._step_kicker.set_label(t("diag.step_n", current=max(done, total), total=total))
        self._step_label.set_label(t("diag.done_hint"))
        self._step_state.set_label(t("diag.state_done"))
        self._step_state.set_visible(True)
        self._swap_card("done")
        self._swap_state("done")

    def _swap_card(self, name: str) -> None:
        for cls in ("idle", "waiting", "holding", "done"):
            self._step_card.remove_css_class(cls)
        self._step_card.add_css_class(name)

    def _swap_state(self, name: str) -> None:
        for cls in ("idle", "hold", "done"):
            self._step_state.remove_css_class(cls)
        self._step_state.add_css_class(name)

    def _diagnostics_finished(self) -> bool:
        if self._session.is_running():
            return False
        if self._session.get_progress() >= 0.999:
            return True
        return self._session.get_results().overall != TestStatus.NOT_TESTED

    def _start(self, tests: list[str]) -> None:
        if not self._backend.is_connected():
            self._step_label.set_label(t("status.disconnected"))
            self._swap_card("idle")
            return
        self._pad.set_focus("")
        self._report_btn.set_visible(False)
        self._pad.set_hold_timer(None)
        self._skip_btn.set_visible(False)
        self._session.start(tests)
        self._sync_footer_mode()
        if self._stop_btn is not None:
            self._stop_btn.set_visible(True)
        self._refresh_chips()

    def _on_session_update(self) -> None:
        GLib.idle_add(self._refresh_ui)

    def _open_report(self, *_args) -> None:
        if self._on_open_report:
            self._on_open_report()

    def _rumble(self, left: float, right: float, duration: int) -> None:
        self._backend.rumble(left, right, duration)

    def update_live(self, state, profile) -> None:
        running = self._session.is_running()
        finished = self._diagnostics_finished()
        done, total = self._session.get_category_progress()
        self._progress.set_fraction(self._session.get_progress())
        self._progress_count.set_label(f"{done} / {total}")
        if running:
            done, total = self._session.get_category_progress()
            self._step_kicker.set_label(
                t("diag.step_n", current=min(total, done + 1), total=total)
            )
            self._step_label.set_label(self._session.get_current_step() or t("diag.hint_idle"))
            holding = self._session.get_hold_timer() is not None
            self._step_state.set_visible(True)
            if holding:
                self._step_state.set_label(t("diag.state_holding"))
                self._swap_card("holding")
                self._swap_state("hold")
            else:
                self._step_state.set_label(t("diag.state_waiting"))
                self._swap_card("waiting")
                self._swap_state("idle")
        elif finished:
            self._set_step_idle_done()
        else:
            self._set_step_idle()
        focus = self._session.get_focus() if running else ""
        self._pad.set_instruction(self._session.get_current_step() if running else "", focus)
        timer = self._session.get_hold_timer() if running else None
        if timer is None:
            self._pad.set_hold_timer(None)
        else:
            remaining, total_t = timer
            self._pad.set_hold_timer(remaining, total_t)
        self._pad.set_telemetry_enabled(running)
        dz = self._config.left_stick_deadzone
        if focus.startswith("right"):
            dz = self._config.right_stick_deadzone
        self._pad.set_deadzone(dz)
        cue_side, cue_motion, cue_repeats = self._session.get_stick_cue() if running else ("", "", 0)
        hold_s = self._config.hold_seconds() if running else 0
        self._pad.set_stick_cue(cue_side, cue_motion, cue_repeats, hold_s)
        self._pad.update(
            state,
            profile,
            trail=running,
            failed=self._session.get_failed_buttons(),
            passed=self._session.get_passed_buttons(),
        )
        if self._stop_btn is not None:
            self._stop_btn.set_visible(running)
        self._skip_btn.set_visible(self._session.can_skip())
        self._report_btn.set_visible(finished and not running)
        self._sync_footer_mode()
        self._refresh_chips()

    def _refresh_ui(self) -> None:
        running = self._session.is_running()
        report = self._session.get_results()
        finished = self._diagnostics_finished()
        done, total = self._session.get_category_progress()
        self._progress.set_fraction(self._session.get_progress())
        self._progress_count.set_label(f"{done} / {total}")
        if running:
            done, total = self._session.get_category_progress()
            self._step_kicker.set_label(
                t("diag.step_n", current=min(total, done + 1), total=total)
            )
            self._step_label.set_label(self._session.get_current_step() or t("diag.hint_idle"))
            self._step_state.set_visible(True)
        elif finished:
            self._set_step_idle_done()
        else:
            self._set_step_idle()
        timer = self._session.get_hold_timer() if running else None
        if timer is None:
            self._pad.set_hold_timer(None)
        else:
            self._pad.set_hold_timer(*timer)
        self._update_result_card(report)
        if self._stop_btn is not None:
            self._stop_btn.set_visible(running)
        self._skip_btn.set_visible(self._session.can_skip())
        self._report_btn.set_visible(finished and not running)
        self._refresh_chips()

    def _refresh_chips(self) -> None:
        titles = {
            "sticks": t("diag.sticks"),
            "triggers": t("diag.triggers"),
            "buttons": t("diag.buttons"),
        }
        running = self._session.is_running()
        phase = self._session.get_phase() if running else ""
        report = self._session.get_results()
        mapping = {
            "sticks": report.tests.get("sticks", TestStatus.NOT_TESTED),
            "triggers": report.tests.get("triggers", TestStatus.NOT_TESTED),
            "buttons": report.tests.get("buttons", TestStatus.NOT_TESTED),
        }
        for key, btn in self._check_btns.items():
            for cls in ("running", "pass", "warn", "fail"):
                btn.remove_css_class(cls)
            btn.set_sensitive(not running)
            prefix = "○  "
            status = mapping.get(key, TestStatus.NOT_TESTED)
            if running and phase == key:
                btn.add_css_class("running")
                prefix = "●  "
            elif status == TestStatus.PASS:
                btn.add_css_class("pass")
                prefix = "✓  "
            elif status == TestStatus.WARN:
                btn.add_css_class("warn")
                prefix = "!  "
            elif status == TestStatus.FAIL:
                btn.add_css_class("fail")
                prefix = "×  "
            btn.set_label(prefix + titles[key])

    def _sync_footer_mode(self) -> None:
        running = self._session.is_running()
        finished = self._diagnostics_finished()
        if running:
            self._result_card.set_visible(True)
            self._prog_panel.set_visible(True)
            self._score_label.set_visible(False)
            self._score_hint.set_visible(False)
            self._result_label.set_visible(False)
        elif finished:
            self._result_card.set_visible(True)
            self._prog_panel.set_visible(False)
            self._result_label.set_visible(True)
        else:
            self._result_card.set_visible(False)

    def _update_result_card(self, report: DiagnosticReport) -> None:
        self._sync_footer_mode()
        if self._session.is_running() or report.overall == TestStatus.NOT_TESTED:
            return
        for cls in ("score-good", "score-ok", "score-bad"):
            self._score_label.remove_css_class(cls)
        self._score_label.add_css_class(report.score_css_class())
        self._score_label.set_label(t("diag.score", score=report.score))
        self._score_label.set_visible(True)
        self._score_hint.set_label(t("diag.score_hint"))
        self._score_hint.set_visible(True)
        self._result_label.set_label("\n".join(result_lines(report)[1:]))
        self._result_label.set_visible(True)

    @property
    def session(self) -> DiagnosticSession:
        return self._session
