"""Windows — вкладка «Отчёт» и экспорт."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk

from core.export import export_csv, export_json
from core.i18n import t
from core.report import DiagnosticReport, result_lines, score_tone
from core.status import TestStatus


class ReportPanel(ttk.Frame):
    def __init__(self, master, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self._report: DiagnosticReport | None = None
        self._text = scrolledtext.ScrolledText(self, height=20, wrap="word")
        self._text.pack(fill="both", expand=True, padx=8, pady=8)
        actions = ttk.Frame(self)
        actions.pack(fill="x", padx=8, pady=4)
        ttk.Button(actions, text=t("report.export_json"), command=self._export_json).pack(side="left", padx=4)
        ttk.Button(actions, text=t("report.export_csv"), command=self._export_csv).pack(side="left", padx=4)
        self.set_report(None)

    def set_report(self, report: DiagnosticReport | None) -> None:
        self._report = report
        self._text.delete("1.0", tk.END)
        if report is None or report.overall == TestStatus.NOT_TESTED:
            self._text.insert(tk.END, t("report.empty") + "\n\n" + t("report.disclaimer"))
            return
        self._text.tag_configure("score_good", foreground="#107c10", font=("Segoe UI", 16, "bold"))
        self._text.tag_configure("score_ok", foreground="#c19c00", font=("Segoe UI", 16, "bold"))
        self._text.tag_configure("score_bad", foreground="#c42b1c", font=("Segoe UI", 16, "bold"))
        lines = result_lines(report)
        self._text.insert(tk.END, lines[0] + "\n", f"score_{score_tone(report.score)}")
        extra = [
            t("diag.score_hint"),
            f"{t('diag.result_title')}: {t(report.status_label_key())}",
            f"{t('report.device')}: {report.device_name}",
            f"{t('report.profile')}: {report.axis_profile}",
            f"{t('report.duration')}: {report.duration_seconds:.1f}s",
            "",
        ]
        self._text.insert(tk.END, "\n".join(extra) + "\n")
        self._text.insert(tk.END, "\n".join(lines[1:]) + "\n\n" + t("report.disclaimer"))

    def _export_json(self) -> None:
        if not self._report:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            initialfile="gamepad-report.json",
        )
        if path:
            export_json(self._report, __import__("pathlib").Path(path))

    def _export_csv(self) -> None:
        if not self._report:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile="gamepad-report.csv",
        )
        if path:
            export_csv(self._report, __import__("pathlib").Path(path))
