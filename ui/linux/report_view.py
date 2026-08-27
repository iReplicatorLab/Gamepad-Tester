"""Вкладка «Отчёт» и экспорт."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from core.export import export_csv, export_json
from core.i18n import t
from core.report import DiagnosticReport, result_lines
from core.status import TestStatus


class ReportView(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self._report: DiagnosticReport | None = None
        self._score = Gtk.Label(xalign=0)
        self._score.add_css_class("score-badge")
        self._score.set_visible(False)
        self.append(self._score)
        self._text = Gtk.TextView(editable=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_min_content_height(320)
        scroll.set_child(self._text)
        group = Adw.PreferencesGroup(title=t("tab.report"))
        group.add(scroll)
        self._group = group
        self.append(group)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._json_btn = Gtk.Button(label=t("report.export_json"))
        self._json_btn.connect("clicked", self._export_json)
        self._csv_btn = Gtk.Button(label=t("report.export_csv"))
        self._csv_btn.connect("clicked", self._export_csv)
        actions.append(self._json_btn)
        actions.append(self._csv_btn)
        self.append(actions)

        self.set_report(None)

    def set_report(self, report: DiagnosticReport | None) -> None:
        self._report = report
        buf = self._text.get_buffer()
        if report is None or report.overall == TestStatus.NOT_TESTED:
            self._score.set_visible(False)
            buf.set_text(t("report.empty") + "\n\n" + t("report.disclaimer"))
            return
        for cls in ("score-good", "score-ok", "score-bad"):
            self._score.remove_css_class(cls)
        self._score.add_css_class(report.score_css_class())
        self._score.set_label(t("diag.score", score=report.score))
        self._score.set_visible(True)
        lines = [
            f"{t('diag.result_title')}: {t(report.status_label_key())}",
            t("diag.score_hint"),
            f"{t('report.device')}: {report.device_name}",
            f"{t('report.profile')}: {report.axis_profile}",
            f"{t('report.duration')}: {report.duration_seconds:.1f}s",
            "",
        ]
        lines.extend(result_lines(report)[1:])
        lines.extend(["", t("report.disclaimer")])
        buf.set_text("\n".join(lines))

    def _export_json(self, *_args) -> None:
        if not self._report:
            return
        dialog = Gtk.FileChooserNative(
            title=t("report.export_json"),
            action=Gtk.FileChooserAction.SAVE,
        )
        dialog.set_current_name("gamepad-report.json")

        def on_response(d, response):
            if response == Gtk.ResponseType.ACCEPT:
                export_json(self._report, __import__("pathlib").Path(d.get_file().get_path()))
            d.destroy()

        dialog.connect("response", on_response)
        dialog.show()

    def _export_csv(self, *_args) -> None:
        if not self._report:
            return
        dialog = Gtk.FileChooserNative(
            title=t("report.export_csv"),
            action=Gtk.FileChooserAction.SAVE,
        )
        dialog.set_current_name("gamepad-report.csv")

        def on_response(d, response):
            if response == Gtk.ResponseType.ACCEPT:
                export_csv(self._report, __import__("pathlib").Path(d.get_file().get_path()))
            d.destroy()

        dialog.connect("response", on_response)
        dialog.show()

    def retranslate(self) -> None:
        self._group.set_title(t("tab.report"))
        self._json_btn.set_label(t("report.export_json"))
        self._csv_btn.set_label(t("report.export_csv"))
        self.set_report(self._report)
