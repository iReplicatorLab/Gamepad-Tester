"""Окно настроек диагностики."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from core.config import DiagnosticConfig, save_config
from core.i18n import get_locale, set_locale, t


class SettingsDialog(Adw.PreferencesWindow):
    def __init__(self, config: DiagnosticConfig, parent, on_saved) -> None:
        super().__init__(transient_for=parent, modal=True)
        self._config = config
        self._on_saved = on_saved
        self._updating_locale = False

        page = Adw.PreferencesPage()
        self._general = Adw.PreferencesGroup()

        self._locale_row = Adw.ActionRow()
        locale_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._locale_ru = Gtk.ToggleButton(label="RU")
        self._locale_en = Gtk.ToggleButton(label="EN")
        self._locale_en.set_group(self._locale_ru)
        if get_locale() == "en":
            self._locale_en.set_active(True)
        else:
            self._locale_ru.set_active(True)
        locale_box.append(self._locale_ru)
        locale_box.append(self._locale_en)
        self._locale_row.add_suffix(locale_box)
        self._general.add(self._locale_row)

        self._thresholds = Adw.PreferencesGroup()
        self._drift_warn, self._drift_warn_row = self._spin_row(
            self._thresholds, config.stick_drift_warn * 100, 1, 20
        )
        self._drift_fail, self._drift_fail_row = self._spin_row(
            self._thresholds, config.stick_drift_fail * 100, 1, 30
        )
        self._rest_seconds, self._rest_seconds_row = self._spin_row(
            self._thresholds, config.rest_test_seconds, 3, 15, step=0.5
        )
        self._left_dz, self._left_dz_row = self._spin_row(
            self._thresholds, config.left_stick_deadzone * 100, 0, 20
        )
        self._right_dz, self._right_dz_row = self._spin_row(
            self._thresholds, config.right_stick_deadzone * 100, 0, 20
        )
        self._hold_row = Adw.ComboRow()
        hold_model = Gtk.StringList.new([str(i) for i in range(1, 16)])
        self._hold_row.set_model(hold_model)
        self._hold_row.set_selected(max(0, min(14, config.hold_seconds() - 1)))
        self._thresholds.add(self._hold_row)

        self._tests = Adw.PreferencesGroup()
        self._sticky_switch, self._sticky_row = self._switch_row(self._tests, config.test_stickiness)
        self._hold_test_switch, self._hold_test_row = self._switch_row(self._tests, config.test_hold)
        self._sens_switch, self._sens_row = self._switch_row(self._tests, config.test_sensitivity)

        self._reset_btn = Gtk.Button()
        self._reset_btn.connect("clicked", self._on_reset)
        self._reset_row = Adw.ActionRow()
        self._reset_row.add_suffix(self._reset_btn)
        self._thresholds.add(self._reset_row)

        self._save_btn = Gtk.Button()
        self._save_btn.add_css_class("suggested-action")
        self._save_btn.connect("clicked", self._on_save)
        save_row = Adw.ActionRow()
        save_row.add_suffix(self._save_btn)
        self._thresholds.add(save_row)

        page.add(self._general)
        page.add(self._tests)
        page.add(self._thresholds)
        self.add(page)

        self._locale_ru.connect("toggled", self._on_locale_toggled)
        self._locale_en.connect("toggled", self._on_locale_toggled)
        self.retranslate()

    @staticmethod
    def _spin_row(group, value: float, low: float, high: float, step: float = 0.5):
        spin = Gtk.SpinButton.new_with_range(low, high, step)
        spin.set_digits(1 if step < 1 else 0)
        spin.set_value(value)
        row = Adw.ActionRow()
        row.add_suffix(spin)
        group.add(row)
        return spin, row

    @staticmethod
    def _switch_row(group, active: bool):
        switch = Gtk.Switch()
        switch.set_active(bool(active))
        switch.set_valign(Gtk.Align.CENTER)
        row = Adw.ActionRow()
        row.add_suffix(switch)
        row.set_activatable_widget(switch)
        group.add(row)
        return switch, row

    def retranslate(self) -> None:
        self.set_title(t("settings.title"))
        self._general.set_title(t("settings.title"))
        self._locale_row.set_title(t("settings.locale"))
        self._drift_warn_row.set_title(t("settings.drift_warn"))
        self._drift_fail_row.set_title(t("settings.drift_fail"))
        self._rest_seconds_row.set_title(t("settings.rest_seconds"))
        self._left_dz_row.set_title(t("settings.left_dz"))
        self._right_dz_row.set_title(t("settings.right_dz"))
        self._hold_row.set_title(t("settings.button_hold"))
        self._tests.set_title(t("settings.button_tests"))
        self._sticky_row.set_title(t("settings.test_stickiness"))
        self._sticky_row.set_subtitle(t("settings.test_stickiness_sub"))
        self._hold_test_row.set_title(t("settings.test_hold"))
        self._hold_test_row.set_subtitle(t("settings.test_hold_sub"))
        self._sens_row.set_title(t("settings.test_sensitivity"))
        self._sens_row.set_subtitle(t("settings.test_sensitivity_sub"))
        self._reset_btn.set_label(t("settings.reset"))
        self._reset_row.set_title(t("settings.reset"))
        self._save_btn.set_label(t("settings.save"))

    def _on_locale_toggled(self, btn: Gtk.ToggleButton) -> None:
        if self._updating_locale or not btn.get_active():
            return
        code = "en" if btn is self._locale_en else "ru"
        if get_locale() == code:
            return
        set_locale(code)
        self._config.locale = code
        save_config(self._config)
        self.retranslate()
        if self._on_saved:
            self._on_saved()

    def _on_reset(self, *_args) -> None:
        defaults = DiagnosticConfig()
        self._drift_warn.set_value(defaults.stick_drift_warn * 100)
        self._drift_fail.set_value(defaults.stick_drift_fail * 100)
        self._rest_seconds.set_value(defaults.rest_test_seconds)
        self._left_dz.set_value(defaults.left_stick_deadzone * 100)
        self._right_dz.set_value(defaults.right_stick_deadzone * 100)
        self._hold_row.set_selected(max(0, min(14, defaults.hold_seconds() - 1)))
        self._sticky_switch.set_active(defaults.test_stickiness)
        self._hold_test_switch.set_active(defaults.test_hold)
        self._sens_switch.set_active(defaults.test_sensitivity)
        self._updating_locale = True
        self._locale_ru.set_active(True)
        self._updating_locale = False
        set_locale("ru")
        self._config.locale = "ru"
        save_config(self._config)
        self.retranslate()
        if self._on_saved:
            self._on_saved()

    def _on_save(self, *_args) -> None:
        self._config.stick_drift_warn = self._drift_warn.get_value() / 100.0
        self._config.stick_drift_fail = self._drift_fail.get_value() / 100.0
        self._config.rest_test_seconds = self._rest_seconds.get_value()
        self._config.left_stick_deadzone = self._left_dz.get_value() / 100.0
        self._config.right_stick_deadzone = self._right_dz.get_value() / 100.0
        self._config.button_hold_seconds = int(self._hold_row.get_selected()) + 1
        self._config.test_stickiness = bool(self._sticky_switch.get_active())
        self._config.test_hold = bool(self._hold_test_switch.get_active())
        self._config.test_sensitivity = bool(self._sens_switch.get_active())
        self._config.locale = "en" if self._locale_en.get_active() else "ru"
        save_config(self._config)
        set_locale(self._config.locale)
        self.retranslate()
        self._on_saved()
        self.close()
