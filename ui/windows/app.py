"""Windows tkinter shell — 4 вкладки."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from backend.windows import WindowsGamepadBackend
from core.config import DiagnosticConfig
from core.i18n import init_from_config, t
from core.status import TestStatus
from pad_common import APP_NAME, VERSION
from ui.windows.diagnostics_panel import DiagnosticsPanel
from ui.windows.log_panel import LogPanel
from ui.windows.report_panel import ReportPanel
from ui.windows.settings_dialog import SettingsDialog
from ui.windows.widgets import MonitoringPanel


class GamepadTesterApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self._config = DiagnosticConfig.load()
        init_from_config(self._config.locale)
        self._backend = WindowsGamepadBackend()
        self._last_report_done = False
        self._tab_labels: dict[int, str] = {}

        root.title(f"{APP_NAME}  v{VERSION}")
        root.geometry("940x760")
        root.minsize(820, 640)

        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")

        toolbar = ttk.Frame(root)
        toolbar.pack(fill="x", padx=8, pady=4)
        ttk.Button(toolbar, text=t("settings.title"), command=self._open_settings).pack(side="right")

        self._notebook = ttk.Notebook(root)
        self._notebook.pack(fill="both", expand=True, padx=8, pady=4)

        self._monitoring = MonitoringPanel(self._notebook)
        self._diagnostics = DiagnosticsPanel(
            self._notebook,
            self._backend,
            self._config,
            self._on_diag_update,
        )
        self._log = LogPanel(self._notebook, self._backend)
        self._report = ReportPanel(self._notebook)

        self._add_tab(self._monitoring, "tab.monitoring")
        self._add_tab(self._diagnostics, "tab.diagnostics")
        self._add_tab(self._log, "tab.log")
        self._add_tab(self._report, "tab.report")

        self._monitoring.set_rumble_handlers(self._on_rumble_test, self._backend.stop_rumble)

        self._backend.start()
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._poll()

    def _add_tab(self, widget, key: str) -> None:
        idx = self._notebook.index("end")
        self._notebook.add(widget, text=t(key))
        self._tab_labels[idx] = key

    def _reload_tabs(self) -> None:
        for idx, key in self._tab_labels.items():
            self._notebook.tab(idx, text=t(key))

    def _open_settings(self) -> None:
        SettingsDialog(self.root, self._config, self._reload_tabs)

    def _on_rumble_test(self, left: float, right: float) -> None:
        l, r, duration = self._monitoring.get_rumble_params()
        if not self._backend.rumble(l * left, r * right, duration):
            self._monitoring.status_var.set("Rumble unavailable")

    def _on_diag_update(self, report, running: bool) -> None:
        if running:
            self._last_report_done = False
        elif not self._last_report_done and report.overall != TestStatus.NOT_TESTED:
            self._report.set_report(report)
            self._last_report_done = True

    def _poll(self) -> None:
        state = self._backend.get_state()
        profile = self._backend.get_axis_profile()
        self._monitoring.update_state(
            state.connected,
            state.name,
            state.axis_profile,
            state.buttons,
            state.axes,
            profile,
        )
        self._log.refresh()
        self.root.after(30, self._poll)

    def _on_close(self) -> None:
        self._diagnostics.session.stop()
        self._backend.stop()
        self.root.destroy()
