"""Оркестратор диагностических тестов."""

from __future__ import annotations

import threading
import time
from typing import Callable, Protocol

from core.button import (
    PRESS_TIMEOUT,
    STICKY_LIMIT,
    buttons_for_device,
    check_button,
    summarize,
)
from core.config import DiagnosticConfig
from core.i18n import t
from core.report import DiagnosticReport, EventRateResult, StickTestResult
from core.stats import analyze_event_rate
from core.status import TestStatus
from core.stick import StickDiagnostic
from core.trigger import TriggerDiagnostic
from pad_common import AxisProfile, normalize_trigger


ANALOG_ACTIVE = 0.38
ANALOG_REST = 0.22
ANALOG_HOLD = 0.85
TRIGGER_ACTIVE = 0.12
TRIGGER_REST = 0.06
TRIGGER_HOLD = 0.85
CIRCLE_RIM = 0.55


class SampleSource(Protocol):
    def is_connected(self) -> bool: ...
    def get_device_name(self) -> str: ...
    def get_device_path(self) -> str: ...
    def get_vendor_product(self) -> tuple[int | None, int | None]: ...
    def get_axis_profile_name(self) -> str: ...
    def get_axis_profile(self) -> AxisProfile: ...
    def get_state(self): ...
    def start_logging(self, test_id: str) -> None: ...
    def stop_logging(self) -> None: ...
    def get_logged_samples(self) -> list: ...
    def get_event_timestamps(self) -> list[int]: ...
    def wait_for_user_step(
        self, message: str, timeout: float, stop_check: Callable[[], bool], expect: str = "any"
    ) -> bool: ...


class DiagnosticSession:
    V2_TESTS = frozenset({"rumble", "stress"})

    def __init__(self, config: DiagnosticConfig, source: SampleSource) -> None:
        self._config = config
        self._source = source
        self._stick = StickDiagnostic(config)
        self._trigger = TriggerDiagnostic(config)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._progress = 0.0
        self._step = ""
        self._focus = ""
        self._report = DiagnosticReport(disclaimer=t("report.disclaimer"))
        self._running = False
        self._on_update: Callable[[], None] | None = None
        self._hold_total = 0.0
        self._hold_ends_at = 0.0
        self._hold_paused = False
        self._hold_frozen = 0.0
        self._skip = threading.Event()
        self._can_skip = False
        self._failed_buttons: set[int] = set()
        self._phase = ""
        self._step_index = 0
        self._step_total = 1
        self._selected: list[str] = []
        self._cue_side = ""
        self._cue_motion = ""
        self._cue_repeats = 0

    def set_update_callback(self, cb: Callable[[], None] | None) -> None:
        self._on_update = cb

    def start(self, tests: list[str] | None = None) -> None:
        if self._running:
            return
        selected = tests or ["sticks", "triggers", "buttons"]
        self._stop.clear()
        self._skip.clear()
        self._running = True
        with self._lock:
            self._focus = ""
            self._progress = 0.0
            self._step = ""
            self._hold_total = 0.0
            self._hold_ends_at = 0.0
            self._hold_paused = False
            self._hold_frozen = 0.0
            self._can_skip = False
            self._failed_buttons = set()
            self._phase = ""
            self._step_index = 0
            self._step_total = 1
            self._selected = list(selected)
            self._cue_side = ""
            self._cue_motion = ""
            self._cue_repeats = 0
        self._report = DiagnosticReport(
            locale=self._config.locale,
            disclaimer=t("report.disclaimer"),
            thresholds={
                "stick_drift_warn": self._config.stick_drift_warn,
                "stick_drift_fail": self._config.stick_drift_fail,
                "trigger_min": self._config.trigger_min,
                "trigger_max": self._config.trigger_max,
            },
        )
        self._thread = threading.Thread(
            target=self._run,
            args=(selected,),
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._skip.set()

    def skip(self) -> None:
        if self.can_skip():
            self._skip.set()

    def can_skip(self) -> bool:
        with self._lock:
            return self._can_skip and self._running

    def get_failed_buttons(self) -> set[int]:
        with self._lock:
            return set(self._failed_buttons)

    def _set_can_skip(self, enabled: bool) -> None:
        with self._lock:
            self._can_skip = enabled

    def _mark_failed(self, index: int) -> None:
        with self._lock:
            self._failed_buttons.add(index)

    def _aborting(self) -> bool:
        return self._stop.is_set() or self._skip.is_set()

    def _consume_skip(self) -> bool:
        if self._skip.is_set() and not self._stop.is_set():
            self._skip.clear()
            return True
        return False

    def _hold_seconds(self) -> int:
        return self._config.hold_seconds()

    def _enabled_checks(self) -> tuple[bool, bool, bool]:
        sticky = bool(self._config.test_stickiness)
        hold = bool(self._config.test_hold)
        sens = bool(self._config.test_sensitivity)
        if not (sticky or hold or sens):
            return True, True, True
        return sticky, hold, sens

    def is_running(self) -> bool:
        return self._running

    def get_progress(self) -> float:
        with self._lock:
            return self._progress

    def get_current_step(self) -> str:
        with self._lock:
            return self._step

    def get_focus(self) -> str:
        with self._lock:
            return self._focus

    def get_stick_cue(self) -> tuple[str, str, int]:
        with self._lock:
            return self._cue_side, self._cue_motion, self._cue_repeats

    def _set_stick_cue(self, side: str, motion: str, repeats: int = 0) -> None:
        with self._lock:
            self._cue_side = side
            self._cue_motion = motion
            self._cue_repeats = repeats

    def get_phase(self) -> str:
        with self._lock:
            return self._phase

    def get_step_numbers(self) -> tuple[int, int]:
        with self._lock:
            return self._step_index, max(1, self._step_total)

    def get_category_progress(self) -> tuple[int, int]:
        runnable = ("sticks", "triggers", "buttons")
        with self._lock:
            selected = [name for name in (self._selected or runnable) if name in runnable]
            if not selected:
                selected = list(runnable)
            done = 0
            for name in selected:
                status = self._report.tests.get(name, TestStatus.NOT_TESTED)
                if status not in (TestStatus.NOT_TESTED, TestStatus.NOT_SUPPORTED):
                    done += 1
            return done, len(selected)

    def get_passed_buttons(self) -> set[int]:
        with self._lock:
            return {
                item.index
                for item in self._report.buttons.buttons
                if item.pressed and not item.skipped and item.sensitive and not item.sticky
            }

    def get_selected_tests(self) -> list[str]:
        with self._lock:
            return list(self._selected)

    def _set_phase(self, phase: str) -> None:
        with self._lock:
            self._phase = phase

    def get_results(self) -> DiagnosticReport:
        with self._lock:
            return self._report

    def get_hold_timer(self) -> tuple[float, float] | None:
        with self._lock:
            if self._hold_paused:
                return max(0.0, self._hold_frozen), self._hold_total
            if self._hold_ends_at <= 0:
                return None
            remaining = self._hold_ends_at - time.monotonic()
            return max(0.0, remaining), self._hold_total

    def _begin_hold(self, seconds: float) -> None:
        with self._lock:
            self._hold_paused = False
            self._hold_frozen = 0.0
            self._hold_total = max(0.0, seconds)
            self._hold_ends_at = time.monotonic() + self._hold_total if seconds > 0 else 0.0

    def _begin_hold_from(self, remaining: float, total: float) -> None:
        with self._lock:
            self._hold_paused = False
            self._hold_frozen = 0.0
            self._hold_total = max(0.0, total)
            self._hold_ends_at = time.monotonic() + max(0.0, remaining)

    def _pause_hold(self, remaining: float, total: float) -> None:
        with self._lock:
            self._hold_paused = True
            self._hold_frozen = max(0.0, remaining)
            self._hold_total = max(0.0, total)
            self._hold_ends_at = 0.0

    def _clear_hold(self) -> None:
        with self._lock:
            self._hold_total = 0.0
            self._hold_ends_at = 0.0
            self._hold_paused = False
            self._hold_frozen = 0.0

    def _notify(self) -> None:
        if self._on_update:
            self._on_update()

    def _wait_held(self, is_down: Callable[[], bool], seconds: float) -> bool:
        """Отсчёт только пока действие удерживается; при отпускании таймер сбрасывается."""
        accumulated = 0.0
        last = time.monotonic()
        deadline = time.monotonic() + max(40.0, seconds * 8)
        counting = False
        last_notify = 0.0
        try:
            while accumulated < seconds:
                if self._aborting():
                    return False
                now = time.monotonic()
                if now > deadline:
                    return False
                down = bool(is_down())
                dt = min(0.1, now - last)
                last = now
                if down:
                    if not counting:
                        counting = True
                        accumulated = 0.0
                        self._begin_hold(seconds)
                        self._notify()
                    else:
                        accumulated += dt
                elif counting:
                    counting = False
                    accumulated = 0.0
                    self._clear_hold()
                    self._notify()
                if now - last_notify >= 0.08:
                    last_notify = now
                    self._notify()
                time.sleep(0.03)
            return True
        finally:
            self._clear_hold()
            self._notify()

    def _wait_button_hold(self, index: int, seconds: float) -> bool:
        return self._wait_held(
            lambda: bool(self._source.get_state().buttons.get(index, False)),
            seconds,
        )

    def _wait_seconds(self, seconds: float, *, timed: bool = True, tick=None) -> bool:
        if seconds <= 0:
            return not self._stop.is_set()
        if timed:
            self._begin_hold(seconds)
            self._notify()
        end = time.monotonic() + seconds
        last_notify = 0.0
        try:
            while time.monotonic() < end:
                if self._stop.is_set():
                    return False
                if tick is not None:
                    tick()
                now = time.monotonic()
                if timed and now - last_notify >= 0.08:
                    last_notify = now
                    self._notify()
                time.sleep(0.03)
            return True
        finally:
            if timed:
                self._clear_hold()
                self._notify()

    def _wait_until_released(self, index: int) -> bool:
        while bool(self._source.get_state().buttons.get(index, False)):
            if self._aborting():
                return False
            time.sleep(0.02)
        time.sleep(0.08)
        return not self._aborting()

    def _wait_press_release(self, index: int, timeout: float) -> tuple[str, float]:
        """Быстрое нажатие: press затем release. ok / sticky / miss / skip / stop."""
        if not self._wait_until_released(index):
            return ("skip" if self._skip.is_set() and not self._stop.is_set() else "stop", 0.0)
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self._aborting():
                return ("skip" if self._skip.is_set() and not self._stop.is_set() else "stop", 0.0)
            if bool(self._source.get_state().buttons.get(index, False)):
                break
            time.sleep(0.01)
        else:
            return ("miss", 0.0)

        t0 = time.monotonic()
        while True:
            if self._aborting():
                kind = "skip" if self._skip.is_set() and not self._stop.is_set() else "stop"
                return (kind, time.monotonic() - t0)
            down = bool(self._source.get_state().buttons.get(index, False))
            dur = time.monotonic() - t0
            if not down:
                return ("sticky" if dur > STICKY_LIMIT else "ok", dur)
            if dur > STICKY_LIMIT:
                if not self._wait_until_released(index):
                    kind = "skip" if self._skip.is_set() and not self._stop.is_set() else "stop"
                    return (kind, time.monotonic() - t0)
                return ("sticky", time.monotonic() - t0)
            time.sleep(0.01)

    def _logical_axes(self) -> dict[str, float]:
        return self._source.get_axis_profile().read(self._source.get_state().axes)

    def _dir_value(self, axis_x: str, axis_y: str, direction: str) -> float:
        axes = self._logical_axes()
        x = float(axes.get(axis_x, 0.0))
        y = float(axes.get(axis_y, 0.0))
        if direction == "up":
            return -y
        if direction == "down":
            return y
        if direction == "left":
            return -x
        return x

    def _stick_radius(self, axis_x: str, axis_y: str) -> float:
        axes = self._logical_axes()
        x = float(axes.get(axis_x, 0.0))
        y = float(axes.get(axis_y, 0.0))
        return (x * x + y * y) ** 0.5

    def _trigger_value(self, axis: str) -> float:
        return normalize_trigger(self._logical_axes().get(axis, -1.0))

    def _wait_until_pred(self, pred: Callable[[], bool], timeout: float | None = None) -> str:
        end = None if timeout is None else time.monotonic() + timeout
        while True:
            if self._aborting():
                return "skip" if self._skip.is_set() and not self._stop.is_set() else "stop"
            if pred():
                return "ok"
            if end is not None and time.monotonic() >= end:
                return "miss"
            time.sleep(0.01)

    def _wait_analog_pulse(
        self,
        is_active: Callable[[], bool],
        is_rest: Callable[[], bool],
        timeout: float,
    ) -> tuple[str, float]:
        """Быстрое отклонение/нажатие и возврат. ok / sticky / miss / skip / stop."""
        kind = self._wait_until_pred(is_rest)
        if kind != "ok":
            return (kind, 0.0)
        kind = self._wait_until_pred(is_active, timeout)
        if kind != "ok":
            return (kind, 0.0)
        t0 = time.monotonic()
        while True:
            if self._aborting():
                kind = "skip" if self._skip.is_set() and not self._stop.is_set() else "stop"
                return (kind, time.monotonic() - t0)
            dur = time.monotonic() - t0
            if is_rest():
                return ("sticky" if dur > STICKY_LIMIT else "ok", dur)
            if dur > STICKY_LIMIT:
                rest = self._wait_until_pred(is_rest)
                if rest != "ok":
                    return (rest, time.monotonic() - t0)
                return ("sticky", time.monotonic() - t0)
            time.sleep(0.01)

    def _action_issues(
        self,
        name: str,
        *,
        pressed: bool,
        held: bool,
        skipped: bool,
        sticky: bool,
        sensitive: bool,
        want_sticky: bool,
        want_hold: bool,
        want_sens: bool,
    ) -> list[str]:
        hold = self._hold_seconds()
        issues: list[str] = []
        if skipped:
            issues.append(t("button.skipped", name=name))
        elif not pressed:
            issues.append(t("button.missed", name=name))
        if pressed and not skipped and want_sens and not sensitive:
            issues.append(t("button.insensitive", name=name))
        if pressed and not skipped and want_sticky and sticky:
            issues.append(t("button.sticky", name=name))
        if pressed and not skipped and want_hold and not held:
            issues.append(t("button.not_held", name=name, seconds=hold))
        return issues

    def _perform_action_checks(
        self,
        *,
        name: str,
        focus: str,
        progress: float,
        tap_text: Callable[[int], str],
        hold_text: str,
        is_active: Callable[[], bool],
        is_rest: Callable[[], bool],
        is_held: Callable[[], bool],
        log_id: str,
        stick_cue: tuple[str, str] | None = None,
    ) -> tuple[dict, list]:
        want_sticky, want_hold, want_sens = self._enabled_checks()
        hold = self._hold_seconds()
        result = {
            "pressed": False,
            "held": not want_hold,
            "skipped": False,
            "sticky": False,
            "sensitive": True,
            "stopped": False,
            "taps": 0,
        }
        self._skip.clear()
        self._source.start_logging(log_id)
        try:
            if want_sticky or want_sens:
                for tap_n in (1, 2):
                    if stick_cue:
                        self._set_stick_cue(stick_cue[0], stick_cue[1], 2)
                    self._set_progress(progress, tap_text(tap_n), focus=focus)
                    kind, _dur = self._wait_analog_pulse(is_active, is_rest, PRESS_TIMEOUT)
                    if kind == "stop" or self._stop.is_set():
                        result["stopped"] = True
                        result["skipped"] = True
                        break
                    if kind == "skip":
                        self._consume_skip()
                        result["skipped"] = True
                        break
                    if kind == "miss":
                        result["sensitive"] = False
                        break
                    result["pressed"] = True
                    result["taps"] += 1
                    if kind == "sticky":
                        result["sticky"] = True
                if result["stopped"] or result["skipped"] or not result["pressed"]:
                    return result, self._source.get_logged_samples()
                if want_sens and result["taps"] < 2:
                    result["sensitive"] = False

            if want_hold and not self._stop.is_set() and not result["skipped"]:
                if stick_cue:
                    self._set_stick_cue(stick_cue[0], stick_cue[1], 0)
                self._set_progress(progress, hold_text, focus=focus)
                rest = self._wait_until_pred(is_rest)
                if rest == "stop" or self._stop.is_set():
                    result["stopped"] = True
                    return result, self._source.get_logged_samples()
                if rest == "skip":
                    self._consume_skip()
                    result["skipped"] = True
                    result["held"] = False
                    result["pressed"] = True
                    return result, self._source.get_logged_samples()
                held = self._wait_held(is_held, float(hold))
                if self._stop.is_set():
                    result["stopped"] = True
                    return result, self._source.get_logged_samples()
                if self._consume_skip():
                    result["skipped"] = True
                    result["held"] = False
                    result["pressed"] = True
                elif held:
                    result["held"] = True
                    result["pressed"] = True
                else:
                    result["held"] = False
                    result["pressed"] = True
            return result, self._source.get_logged_samples()
        finally:
            self._source.stop_logging()

    def _set_progress(self, value: float, step: str, focus: str | None = None) -> None:
        with self._lock:
            if step and step != self._step:
                self._step_index = min(self._step_total, self._step_index + 1)
            self._progress = value
            self._step = step
            if focus is not None:
                self._focus = focus
        if self._on_update:
            self._on_update()

    def _estimate_steps(self, tests: list[str]) -> int:
        sticky, hold, sens = self._enabled_checks()
        per = (2 if sticky or sens else 0) + (1 if hold else 0)
        per = max(1, per)
        n = 0
        if "sticks" in tests:
            n += 2 * (1 + 4 * per + 1)
        if "triggers" in tests:
            n += 2 * per
        if "buttons" in tests:
            items = buttons_for_device(
                self._source.get_axis_profile_name(),
                self._source.get_device_name(),
            )
            n += max(1, len(items)) * per
        return max(1, n)

    def _run(self, tests: list[str]) -> None:
        t0 = time.monotonic()
        try:
            self._report.device_name = self._source.get_device_name()
            self._report.device_path = self._source.get_device_path()
            vid, pid = self._source.get_vendor_product()
            self._report.vendor_id = vid
            self._report.product_id = pid
            self._report.axis_profile = self._source.get_axis_profile_name()
            with self._lock:
                self._step_total = self._estimate_steps(tests)
                self._step_index = 0

            for name in ("rumble", "stress"):
                self._report.tests[name] = TestStatus.NOT_TESTED
            if "buttons" not in tests:
                self._report.tests["buttons"] = TestStatus.NOT_TESTED

            steps: list[tuple[str, Callable[[], None]]] = []
            if "sticks" in tests:
                steps.append(("sticks", self._run_sticks))
            if "triggers" in tests:
                steps.append(("triggers", self._run_triggers))
            if "buttons" in tests:
                steps.append(("buttons", self._run_buttons))

            for name, fn in steps:
                if self._stop.is_set() or not self._source.is_connected():
                    break
                fn()
                self._report.tests[name] = self._group_status(name)

            timestamps = self._source.get_event_timestamps()
            rate = analyze_event_rate(timestamps[-5000:])
            self._report.event_rate = EventRateResult(
                mean_interval_ms=rate.mean_interval_ms,
                median_interval_ms=rate.median_interval_ms,
                max_interval_ms=rate.max_interval_ms,
                estimated_hz=rate.estimated_hz,
                note=t("report.event_rate_note"),
            )
        finally:
            self._clear_hold()
            self._report.duration_seconds = time.monotonic() - t0
            self._report.finalize()
            self._set_progress(1.0, t("diag.done_hint"), focus="")
            self._running = False
            if self._on_update:
                self._on_update()

    def _group_status(self, name: str) -> TestStatus:
        if name == "sticks":
            return self._worst(self._report.left_stick.status, self._report.right_stick.status)
        if name == "triggers":
            return self._worst(self._report.lt.status, self._report.rt.status)
        if name == "buttons":
            return self._report.buttons.status
        return TestStatus.NOT_TESTED

    @staticmethod
    def _worst(*statuses: TestStatus) -> TestStatus:
        if TestStatus.FAIL in statuses:
            return TestStatus.FAIL
        if TestStatus.WARN in statuses:
            return TestStatus.WARN
        if all(s == TestStatus.PASS for s in statuses):
            return TestStatus.PASS
        return TestStatus.NOT_TESTED

    def _run_sticks(self) -> None:
        hold = self._hold_seconds()
        want_sticky, want_hold, want_sens = self._enabled_checks()
        self._set_phase("sticks")
        for side, axis_x, axis_y, attr, dz in (
            ("left", "left_x", "left_y", "left_stick", self._config.left_stick_deadzone),
            ("right", "right_x", "right_y", "right_stick", self._config.right_stick_deadzone),
        ):
            if self._stop.is_set():
                return
            stick_name = t("stick.left") if side == "left" else t("stick.right")
            self._set_stick_cue(side, "rest", 0)
            self._set_progress(
                0.08 if side == "left" else 0.28,
                t("stick.rest_instruction", stick=stick_name, seconds=3),
                focus=f"{side}_rest",
            )
            if not self._wait_seconds(3, timed=True):
                return
            self._source.start_logging(f"rest_{side}")
            if not self._wait_seconds(self._config.rest_test_seconds, timed=True):
                self._source.stop_logging()
                return
            rest_samples = self._source.get_logged_samples()
            self._source.stop_logging()
            rest_result = self._stick.analyze_rest(rest_samples, axis_x, axis_y, dz)
            setattr(self._report, attr, rest_result)

            self._set_can_skip(True)
            self._notify()
            try:
                defects = 0
                for direction, dir_key in (
                    ("up", "stick.dir_up"),
                    ("down", "stick.dir_down"),
                    ("left", "stick.dir_left"),
                    ("right", "stick.dir_right"),
                ):
                    if self._stop.is_set():
                        return
                    dir_label = t(dir_key)
                    name = t("stick.action", stick=stick_name, direction=dir_label)
                    progress = 0.15 if side == "left" else 0.35
                    check, step_samples = self._perform_action_checks(
                        name=name,
                        focus=f"{side}_{direction}",
                        progress=progress,
                        tap_text=lambda n, nm=name: t("stick.tap", name=nm, n=n),
                        hold_text=t("stick.holding", name=name, seconds=hold),
                        is_active=lambda d=direction: self._dir_value(axis_x, axis_y, d) >= ANALOG_ACTIVE,
                        is_rest=lambda d=direction: self._dir_value(axis_x, axis_y, d) <= ANALOG_REST,
                        is_held=lambda d=direction: self._dir_value(axis_x, axis_y, d) >= ANALOG_HOLD,
                        log_id=f"range_{side}_{direction}",
                        stick_cue=(side, direction),
                    )
                    if check["stopped"] or self._stop.is_set():
                        return
                    cur: StickTestResult = getattr(self._report, attr)
                    ok, range_issues = self._stick.analyze_range_step(
                        step_samples, axis_x, axis_y, direction
                    )
                    action_issues = self._action_issues(
                        name,
                        pressed=check["pressed"],
                        held=check["held"],
                        skipped=check["skipped"],
                        sticky=check["sticky"],
                        sensitive=check["sensitive"],
                        want_sticky=want_sticky,
                        want_hold=want_hold,
                        want_sens=want_sens,
                    )
                    failed = bool(
                        check["skipped"]
                        or not check["pressed"]
                        or (want_hold and not check["held"])
                        or (want_sticky and check["sticky"])
                        or (want_sens and not check["sensitive"])
                        or not ok
                    )
                    if not ok:
                        cur.range_ok = False
                    cur.issues.extend(action_issues)
                    cur.issues.extend(range_issues)
                    if failed:
                        defects += 1
                        if cur.status == TestStatus.PASS:
                            cur.status = TestStatus.WARN

                if self._stop.is_set():
                    return
                circle_name = t("stick.circle_name", stick=stick_name)
                msg = t("stick.range_circle", stick=stick_name)
                progress = 0.22 if side == "left" else 0.42
                self._skip.clear()
                self._set_stick_cue(side, "circle", 0)
                self._set_progress(progress, msg, focus=f"{side}_circle")
                self._source.start_logging(f"circ_{side}")
                try:
                    start = self._wait_until_pred(
                        lambda: self._stick_radius(axis_x, axis_y) >= ANALOG_ACTIVE,
                        PRESS_TIMEOUT,
                    )
                    circ_skipped = False
                    circ_missed = False
                    circ_held = True
                    if start == "stop" or self._stop.is_set():
                        return
                    if start == "skip":
                        self._consume_skip()
                        circ_skipped = True
                    elif start == "miss":
                        circ_missed = True
                    elif want_hold:
                        self._set_progress(
                            progress,
                            t("stick.circle_hold", stick=stick_name, seconds=hold),
                            focus=f"{side}_circle",
                        )
                        circ_held = self._wait_held(
                            lambda: self._stick_radius(axis_x, axis_y) >= CIRCLE_RIM,
                            float(hold),
                        )
                        if self._stop.is_set():
                            return
                        if self._consume_skip():
                            circ_skipped = True
                            circ_held = False
                    else:
                        if not self._wait_seconds(float(hold), timed=True):
                            return
                    circ_samples = self._source.get_logged_samples()
                finally:
                    self._source.stop_logging()

                err, circ_status, circ_issues = self._stick.analyze_circularity(
                    circ_samples, axis_x, axis_y
                )
                cur = getattr(self._report, attr)
                cur.circularity_pct = err
                if circ_skipped:
                    cur.issues.append(t("button.skipped", name=circle_name))
                    defects += 1
                elif circ_missed:
                    cur.issues.append(t("button.missed", name=circle_name))
                    defects += 1
                elif want_hold and not circ_held:
                    cur.issues.append(t("button.not_held", name=circle_name, seconds=hold))
                    defects += 1
                cur.issues.extend(circ_issues)
                if circ_status == TestStatus.FAIL or (
                    circ_status == TestStatus.WARN and cur.status == TestStatus.PASS
                ):
                    cur.status = circ_status
                if defects >= 2 and cur.status != TestStatus.FAIL:
                    cur.status = TestStatus.FAIL
                elif defects and cur.status == TestStatus.PASS:
                    cur.status = TestStatus.WARN
            finally:
                self._set_can_skip(False)
                self._skip.clear()
                self._notify()

    def _run_triggers(self) -> None:
        hold = self._hold_seconds()
        want_sticky, want_hold, want_sens = self._enabled_checks()
        self._set_phase("triggers")
        self._set_stick_cue("", "", 0)
        self._set_can_skip(True)
        self._notify()
        try:
            for axis, attr, label, progress in (("lt", "lt", "LT", 0.52), ("rt", "rt", "RT", 0.62)):
                if self._stop.is_set():
                    return
                check, samples = self._perform_action_checks(
                    name=label,
                    focus=axis,
                    progress=progress,
                    tap_text=lambda n, nm=label: t("trigger.tap", name=nm, n=n),
                    hold_text=t("trigger.holding", name=label, seconds=hold),
                    is_active=lambda a=axis: self._trigger_value(a) >= TRIGGER_ACTIVE,
                    is_rest=lambda a=axis: self._trigger_value(a) <= TRIGGER_REST,
                    is_held=lambda a=axis: self._trigger_value(a) >= TRIGGER_HOLD,
                    log_id=f"trigger_{axis}",
                )
                if check["stopped"] or self._stop.is_set():
                    return
                result = self._trigger.analyze(samples, axis)
                action_issues = self._action_issues(
                    label,
                    pressed=check["pressed"],
                    held=check["held"],
                    skipped=check["skipped"],
                    sticky=check["sticky"],
                    sensitive=check["sensitive"],
                    want_sticky=want_sticky,
                    want_hold=want_hold,
                    want_sens=want_sens,
                )
                result.issues = action_issues + result.issues
                failed = bool(
                    check["skipped"]
                    or not check["pressed"]
                    or (want_hold and not check["held"])
                    or (want_sticky and check["sticky"])
                    or (want_sens and not check["sensitive"])
                )
                if failed and result.status in (TestStatus.PASS, TestStatus.NOT_TESTED):
                    result.status = TestStatus.WARN
                if check["skipped"] or not check["pressed"]:
                    if result.status != TestStatus.FAIL:
                        result.status = TestStatus.WARN
                setattr(self._report, attr, result)
        finally:
            self._set_can_skip(False)
            self._skip.clear()
            self._notify()

    def _run_buttons(self) -> None:
        items = buttons_for_device(
            self._source.get_axis_profile_name(),
            self._source.get_device_name(),
        )
        self._set_phase("buttons")
        self._set_stick_cue("", "", 0)
        hold = self._hold_seconds()
        want_sticky, want_hold, want_sens = self._enabled_checks()
        checks = []
        n = max(1, len(items))
        self._set_can_skip(True)
        self._notify()
        try:
            for i, (idx, name) in enumerate(items):
                if self._stop.is_set():
                    break
                self._skip.clear()
                progress = 0.70 + 0.25 * i / n
                pressed = False
                held = not want_hold
                skipped = False
                sticky = False
                sensitive = True
                taps = 0

                if want_sticky or want_sens:
                    for tap_n in (1, 2):
                        msg = t("button.tap", name=name, n=tap_n)
                        self._set_progress(progress, msg, focus=f"btn:{idx}")
                        kind, _dur = self._wait_press_release(idx, PRESS_TIMEOUT)
                        if kind == "stop" or self._stop.is_set():
                            skipped = True
                            break
                        if kind == "skip":
                            self._consume_skip()
                            skipped = True
                            break
                        if kind == "miss":
                            sensitive = False
                            if tap_n == 1:
                                pressed = False
                            break
                        pressed = True
                        taps += 1
                        if kind == "sticky":
                            sticky = True
                    if self._stop.is_set():
                        break
                    if skipped:
                        self._mark_failed(idx)
                        checks.append(
                            check_button(
                                idx, name, False, False,
                                skipped=True, seconds=hold,
                            )
                        )
                        self._notify()
                        continue
                    if not pressed:
                        self._mark_failed(idx)
                        checks.append(
                            check_button(
                                idx, name, False, False,
                                sensitive=False, seconds=hold,
                            )
                        )
                        self._notify()
                        continue
                    if want_sens and taps < 2:
                        sensitive = False

                if want_hold and not self._stop.is_set():
                    self._set_progress(
                        progress,
                        t("button.holding", name=name, seconds=hold),
                        focus=f"btn:{idx}",
                    )
                    if not self._wait_until_released(idx):
                        if self._stop.is_set():
                            break
                        self._consume_skip()
                        self._mark_failed(idx)
                        checks.append(
                            check_button(
                                idx, name, True, False,
                                skipped=True, sticky=sticky, sensitive=sensitive,
                                tap_count=taps, seconds=hold,
                            )
                        )
                        continue
                    held = self._wait_button_hold(idx, float(hold))
                    if self._stop.is_set():
                        break
                    if self._consume_skip():
                        skipped = True
                        held = False
                    elif held:
                        pressed = True

                failed = (
                    skipped
                    or not pressed
                    or (want_hold and not held)
                    or (want_sticky and sticky)
                    or (want_sens and not sensitive)
                )
                if failed:
                    self._mark_failed(idx)
                checks.append(
                    check_button(
                        idx,
                        name,
                        pressed,
                        held if want_hold else True,
                        skipped=skipped,
                        sticky=sticky if want_sticky else False,
                        sensitive=sensitive if want_sens else True,
                        tap_count=taps,
                        seconds=hold,
                    )
                )
                self._notify()
                time.sleep(0.08)
        finally:
            self._set_can_skip(False)
            self._skip.clear()
            self._notify()
        self._report.buttons = summarize(checks)
