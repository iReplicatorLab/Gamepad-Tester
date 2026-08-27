"""Windows — настройки диагностики."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from core.config import DiagnosticConfig, save_config
from core.i18n import get_locale, set_locale, t


class SettingsDialog(tk.Toplevel):
    def __init__(self, master, config: DiagnosticConfig, on_saved) -> None:
        super().__init__(master)
        self._config = config
        self._on_saved = on_saved
        self.title(t("settings.title"))
        self.geometry("460x520")
        self.transient(master)
        self.grab_set()

        pad = {"padx": 10, "pady": 6}
        ttk.Label(self, text=t("settings.locale")).grid(row=0, column=0, sticky="w", **pad)
        self.locale_var = tk.StringVar(value=get_locale())
        locale_frame = ttk.Frame(self)
        locale_frame.grid(row=0, column=1, sticky="w", **pad)
        ttk.Radiobutton(locale_frame, text="RU", variable=self.locale_var, value="ru").pack(side="left")
        ttk.Radiobutton(locale_frame, text="EN", variable=self.locale_var, value="en").pack(side="left")

        self.drift_warn = tk.DoubleVar(value=config.stick_drift_warn * 100)
        self.drift_fail = tk.DoubleVar(value=config.stick_drift_fail * 100)
        self.rest_seconds = tk.DoubleVar(value=config.rest_test_seconds)
        self.left_dz = tk.DoubleVar(value=config.left_stick_deadzone * 100)
        self.right_dz = tk.DoubleVar(value=config.right_stick_deadzone * 100)
        self.hold_seconds = tk.StringVar(value=str(config.hold_seconds()))
        self.test_stickiness = tk.BooleanVar(value=config.test_stickiness)
        self.test_hold = tk.BooleanVar(value=config.test_hold)
        self.test_sensitivity = tk.BooleanVar(value=config.test_sensitivity)

        for row, (label, var, lo, hi) in enumerate(
            (
                (t("settings.drift_warn"), self.drift_warn, 1, 20),
                (t("settings.drift_fail"), self.drift_fail, 1, 30),
                (t("settings.rest_seconds"), self.rest_seconds, 3, 15),
                (t("settings.left_dz"), self.left_dz, 0, 20),
                (t("settings.right_dz"), self.right_dz, 0, 20),
            ),
            start=1,
        ):
            ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", **pad)
            ttk.Spinbox(self, from_=lo, to=hi, textvariable=var, width=8).grid(row=row, column=1, sticky="w", **pad)

        ttk.Label(self, text=t("settings.button_hold")).grid(row=6, column=0, sticky="w", **pad)
        ttk.Combobox(
            self,
            textvariable=self.hold_seconds,
            values=[str(i) for i in range(1, 16)],
            state="readonly",
            width=6,
        ).grid(row=6, column=1, sticky="w", **pad)

        ttk.Checkbutton(self, text=t("settings.test_stickiness"), variable=self.test_stickiness).grid(
            row=7, column=0, columnspan=2, sticky="w", **pad
        )
        ttk.Checkbutton(self, text=t("settings.test_hold"), variable=self.test_hold).grid(
            row=8, column=0, columnspan=2, sticky="w", **pad
        )
        ttk.Checkbutton(self, text=t("settings.test_sensitivity"), variable=self.test_sensitivity).grid(
            row=9, column=0, columnspan=2, sticky="w", **pad
        )

        btn_row = ttk.Frame(self)
        btn_row.grid(row=10, column=0, columnspan=2, pady=12)
        ttk.Button(btn_row, text=t("settings.reset"), command=self._reset).pack(side="left", padx=6)
        ttk.Button(btn_row, text="OK", command=self._save).pack(side="left", padx=6)
        ttk.Button(btn_row, text="Cancel", command=self.destroy).pack(side="left", padx=6)

    def _reset(self) -> None:
        defaults = DiagnosticConfig()
        self.drift_warn.set(defaults.stick_drift_warn * 100)
        self.drift_fail.set(defaults.stick_drift_fail * 100)
        self.rest_seconds.set(defaults.rest_test_seconds)
        self.left_dz.set(defaults.left_stick_deadzone * 100)
        self.right_dz.set(defaults.right_stick_deadzone * 100)
        self.hold_seconds.set(str(defaults.hold_seconds()))
        self.test_stickiness.set(defaults.test_stickiness)
        self.test_hold.set(defaults.test_hold)
        self.test_sensitivity.set(defaults.test_sensitivity)
        self.locale_var.set("ru")

    def _save(self) -> None:
        self._config.stick_drift_warn = self.drift_warn.get() / 100.0
        self._config.stick_drift_fail = self.drift_fail.get() / 100.0
        self._config.rest_test_seconds = self.rest_seconds.get()
        self._config.left_stick_deadzone = self.left_dz.get() / 100.0
        self._config.right_stick_deadzone = self.right_dz.get() / 100.0
        try:
            self._config.button_hold_seconds = max(1, min(15, int(self.hold_seconds.get())))
        except ValueError:
            self._config.button_hold_seconds = 3
        self._config.test_stickiness = bool(self.test_stickiness.get())
        self._config.test_hold = bool(self.test_hold.get())
        self._config.test_sensitivity = bool(self.test_sensitivity.get())
        self._config.locale = self.locale_var.get()
        save_config(self._config)
        set_locale(self._config.locale)
        self._on_saved()
        self.destroy()
