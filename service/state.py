"""Shared service state: backend + diagnostics session."""

from __future__ import annotations

import sys
import threading

from backend.protocol import PadState
from core.config import DiagnosticConfig, save_config
from core.i18n import init_from_config
from core.report import result_lines
from core.session import DiagnosticSession
from pad_common import diagram_kind, normalize_trigger

from service.serialize import config_dict, pad_state_dict, report_dict


def _create_backend():
    if sys.platform.startswith("linux"):
        from backend.linux import LinuxGamepadBackend

        return LinuxGamepadBackend()
    from backend.windows import WindowsGamepadBackend

    return WindowsGamepadBackend()


class GamepadService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.config = DiagnosticConfig.load()
        init_from_config(self.config.locale)
        self.backend = _create_backend()
        self.session = DiagnosticSession(self.config, self.backend)
        self.backend.start()
        self._log_lines: list[str] = []
        self._log_seq = 0

    def shutdown(self) -> None:
        self.session.stop()
        self.backend.stop()

    def _append_log(self, line: str) -> None:
        with self._lock:
            self._log_lines.append(line)
            self._log_seq += 1
            if len(self._log_lines) > 2000:
                self._log_lines = self._log_lines[-1500:]

    def refresh_log(self) -> None:
        events = self.backend.logger.recent_events(80)
        if not events:
            return
        for event in events[-5:]:
            self._append_log(f"{event.event_type} {event.code}={event.value}")

    def get_log(self, since: int = 0) -> dict:
        with self._lock:
            lines = self._log_lines[since:]
            return {"lines": lines, "next": self._log_seq}

    def get_state_payload(self) -> dict:
        state = self.backend.get_state()
        profile = self.backend.get_axis_profile()
        return pad_state_dict(state, profile)

    def get_diagnostics_payload(self) -> dict:
        hold = self.session.get_hold_timer()
        cue = self.session.get_stick_cue()
        report = self.session.get_results()
        done, total = self.session.get_category_progress()
        return {
            "running": self.session.is_running(),
            "progress": self.session.get_progress(),
            "step": self.session.get_current_step(),
            "focus": self.session.get_focus(),
            "phase": self.session.get_phase(),
            "step_index": self.session.get_step_numbers()[0],
            "step_total": self.session.get_step_numbers()[1],
            "can_skip": self.session.can_skip(),
            "selected": self.session.get_selected_tests(),
            "failed_buttons": sorted(self.session.get_failed_buttons()),
            "passed_buttons": sorted(self.session.get_passed_buttons()),
            "hold": {"remaining": hold[0], "total": hold[1]} if hold else None,
            "cue": {"side": cue[0], "motion": cue[1], "repeats": cue[2]},
            "hold_seconds": self.config.hold_seconds(),
            "tests": {name: status.value for name, status in report.tests.items()},
            "overall": report.overall.value,
            "score": report.score,
            "category_done": done,
            "category_total": total,
        }

    def get_report_payload(self) -> dict:
        report = self.session.get_results()
        return {
            "report": report_dict(report),
            "lines": result_lines(report),
        }

    def update_config(self, data: dict) -> dict:
        fields = DiagnosticConfig.__dataclass_fields__
        for key, value in data.items():
            if key in fields:
                setattr(self.config, key, value)
        save_config(self.config)
        init_from_config(self.config.locale)
        self.session = DiagnosticSession(self.config, self.backend)
        return config_dict(self.config)

    def start_diagnostics(self, tests: list[str] | None) -> None:
        self._append_log("Diagnostics started")
        self.session.start(tests)

    def stop_diagnostics(self) -> None:
        self.session.stop()
        self._append_log("Diagnostics stopped")

    def skip_step(self) -> None:
        self.session.skip()

    def rumble(self, left: float, right: float, duration_ms: int) -> bool:
        return self.backend.rumble(left, right, duration_ms)

    def stop_rumble(self) -> None:
        self.backend.stop_rumble()
