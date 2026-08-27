"""Windows — вкладка «Диагностика»."""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk

from core.config import DiagnosticConfig
from core.i18n import t
from core.report import DiagnosticReport, result_lines, score_tone
from core.session import DiagnosticSession
from core.status import TestStatus


class DiagnosticsPanel(ttk.Frame):
    def __init__(self, master, backend, config: DiagnosticConfig, on_update, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self._backend = backend
        self._config = config
        self._on_update = on_update
        self._session = DiagnosticSession(config, backend)
        self._session.set_update_callback(self._schedule_refresh)
        self.device_var = tk.StringVar(value="—")
        self.step_var = tk.StringVar(value="")
        self.progress_var = tk.DoubleVar(value=0)
        self.result_text = tk.Text(self, height=14, wrap="word")
        self.result_text.tag_configure("score_good", foreground="#107c10", font=("Segoe UI", 16, "bold"))
        self.result_text.tag_configure("score_ok", foreground="#c19c00", font=("Segoe UI", 16, "bold"))
        self.result_text.tag_configure("score_bad", foreground="#c42b1c", font=("Segoe UI", 16, "bold"))
        self._build()

    def _build(self) -> None:
        pad = {"padx": 8, "pady": 4}
        top = ttk.Frame(self)
        top.pack(fill="x", **pad)
        ttk.Label(top, text=t("monitor.connection") + ":").pack(side="left")
        ttk.Label(top, textvariable=self.device_var).pack(side="left", padx=8)

        actions = ttk.Frame(self)
        actions.pack(fill="x", **pad)
        ttk.Button(actions, text=t("diag.run_full"), command=lambda: self._start(["sticks", "triggers", "buttons"])).pack(
            side="left", padx=2
        )
        ttk.Button(actions, text=t("diag.sticks"), command=lambda: self._start(["sticks"])).pack(side="left", padx=2)
        ttk.Button(actions, text=t("diag.triggers"), command=lambda: self._start(["triggers"])).pack(
            side="left", padx=2
        )
        ttk.Button(actions, text=t("diag.buttons"), command=lambda: self._start(["buttons"])).pack(
            side="left", padx=2
        )
        for key in ("diag.rumble", "diag.stress"):
            btn = ttk.Button(actions, text=t(key))
            btn.state(["disabled"])
            btn.pack(side="left", padx=2)
        ttk.Button(actions, text=t("diag.stop"), command=self._session.stop).pack(side="left", padx=8)
        self._skip_btn = ttk.Button(actions, text=t("diag.skip"), command=self._session.skip)
        self._skip_btn.pack(side="left", padx=2)
        self._skip_btn.state(["disabled"])

        ttk.Progressbar(self, variable=self.progress_var, maximum=1.0).pack(fill="x", **pad)
        ttk.Label(self, textvariable=self.step_var, wraplength=800).pack(fill="x", **pad)
        self.timer_var = tk.StringVar(value="")
        self._timer_label = ttk.Label(self, textvariable=self.timer_var, font=("Segoe UI", 48, "bold"), anchor="center")
        self._timer_label.pack(fill="x", **pad)
        self.result_text.pack(fill="both", expand=True, **pad)
        ttk.Label(self, text=t("report.disclaimer"), wraplength=800).pack(fill="x", **pad)

    def _start(self, tests: list[str]) -> None:
        if not self._backend.is_connected():
            self.step_var.set(t("status.disconnected"))
            return
        self.device_var.set(self._backend.get_device_name())
        self._session.start(tests)

    def _schedule_refresh(self) -> None:
        self.after(0, self._refresh)

    def _refresh(self) -> None:
        self.progress_var.set(self._session.get_progress())
        self.step_var.set(self._session.get_current_step())
        timer = self._session.get_hold_timer()
        if timer is None or timer[0] <= 0:
            self.timer_var.set("")
        else:
            remaining, _total = timer
            self.timer_var.set(str(max(1, math.ceil(remaining - 1e-6))))
        report = self._session.get_results()
        if self._session.can_skip():
            self._skip_btn.state(["!disabled"])
        else:
            self._skip_btn.state(["disabled"])
        self._update_result(report)
        self._on_update(report, self._session.is_running())

    def _update_result(self, report: DiagnosticReport) -> None:
        if report.overall == TestStatus.NOT_TESTED and self._session.is_running():
            return
        if report.overall == TestStatus.NOT_TESTED:
            self.result_text.delete("1.0", tk.END)
            self.result_text.insert(tk.END, t("report.empty"))
            return
        lines = result_lines(report)
        self.result_text.delete("1.0", tk.END)
        tag = f"score_{score_tone(report.score)}"
        self.result_text.insert(tk.END, lines[0] + "\n", tag)
        self.result_text.insert(tk.END, t("diag.score_hint") + "\n\n")
        self.result_text.insert(tk.END, "\n".join(lines[1:]))

    @property
    def session(self) -> DiagnosticSession:
        return self._session
