"""GTK4 / Libadwaita shell — диагностика, журнал, отчёт."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gdk, Gtk, Pango  # noqa: E402

from backend.linux import LinuxGamepadBackend
from core.config import DiagnosticConfig
from core.i18n import init_from_config, t
from core.status import TestStatus
from pad_common import APP_ID


SITE_URL = "https://ireplicator.com/"
from ui.linux.diagnostics_view import DiagnosticsView
from ui.linux.log_view import LogView
from ui.linux.report_view import ReportView
from ui.linux.settings_dialog import SettingsDialog
from ui.linux.styles import CSS


def _decoration_layout_without_maximize() -> str:
    settings = Gtk.Settings.get_default()
    raw = ""
    if settings is not None:
        raw = str(settings.get_property("gtk-decoration-layout") or "")
    if ":" not in raw:
        raw = ":minimize,close"

    def clean(side: str) -> str:
        return ",".join(item for item in side.split(",") if item.strip() and item.strip() != "maximize")

    start, end = raw.split(":", 1)
    return f"{clean(start)}:{clean(end)}"


class GamepadTesterApp(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID)
        self._config = DiagnosticConfig.load()
        init_from_config(self._config.locale)
        self._backend = LinuxGamepadBackend()
        self._win: Adw.ApplicationWindow | None = None
        self._stack: Gtk.Stack | None = None
        self._switcher: Gtk.StackSwitcher | None = None
        self._diagnostics: DiagnosticsView | None = None
        self._log: LogView | None = None
        self._report: ReportView | None = None
        self._last_report_done = False
        self._settings_btn: Gtk.Button | None = None
        self._header_brand: Gtk.Label | None = None
        self._header_transport: Gtk.Label | None = None
        self._header_pill: Gtk.Label | None = None

    def do_activate(self) -> None:
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)

        self._win = Adw.ApplicationWindow(application=self, title=t("app.title"))
        self._win.set_default_size(920, 720)
        self._win.add_css_class("tech-shell")

        header = Adw.HeaderBar()
        header.add_css_class("tech-header")
        header.set_decoration_layout(_decoration_layout_without_maximize())

        brand = Gtk.Label()
        brand.add_css_class("header-brand")
        brand.add_css_class("header-device")
        brand.set_ellipsize(Pango.EllipsizeMode.END)
        brand.set_max_width_chars(36)
        brand.set_valign(Gtk.Align.CENTER)
        self._header_brand = brand
        self._set_brand_link()
        header.pack_start(brand)

        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._switcher = Gtk.StackSwitcher()
        self._switcher.set_stack(self._stack)
        self._switcher.add_css_class("tech-nav")
        header.set_title_widget(self._switcher)

        conn = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        conn.set_valign(Gtk.Align.CENTER)
        transport = Gtk.Label()
        transport.add_css_class("header-transport")
        transport.set_visible(False)
        pill = Gtk.Label()
        pill.add_css_class("status-pill")
        pill.add_css_class("wait")
        conn.append(transport)
        conn.append(pill)
        self._header_transport = transport
        self._header_pill = pill

        settings_btn = Gtk.Button(icon_name="preferences-system-symbolic")
        settings_btn.set_tooltip_text(t("settings.title"))
        settings_btn.connect("clicked", self._open_settings)
        self._settings_btn = settings_btn
        header.pack_end(settings_btn)
        header.pack_end(conn)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.add_css_class("tech-shell")
        self._win.set_content(root)
        root.append(header)

        clamp = Adw.Clamp()
        clamp.set_maximum_size(980)
        clamp.set_margin_top(8)
        clamp.set_margin_bottom(10)
        clamp.set_margin_start(12)
        clamp.set_margin_end(12)
        root.append(clamp)

        self._diagnostics = DiagnosticsView(self._backend, self._config, on_open_report=self._show_report)
        self._log = LogView(self._backend)
        self._report = ReportView()

        scroll_diag = Gtk.ScrolledWindow()
        scroll_diag.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll_diag.set_child(self._diagnostics)

        self._stack.add_titled(scroll_diag, "diag", t("tab.diagnostics"))
        self._stack.add_titled(self._log, "log", t("tab.log"))
        self._stack.add_titled(self._report, "report", t("tab.report"))

        clamp.set_child(self._stack)

        self._win.present()
        self._win.connect("notify::maximized", self._block_maximize)
        self._backend.start()
        self._update_header(self._backend.get_state())
        GLib.timeout_add(30, self._poll)
        self._win.connect("close-request", self._on_close)

    def _set_brand_link(self) -> None:
        if self._header_brand is None:
            return
        title = GLib.markup_escape_text(t("app.title"))
        self._header_brand.set_markup(
            f'<a href="{SITE_URL}"><span underline="none">{title}</span></a>'
        )

    def _block_maximize(self, win, *_args) -> None:
        if win.is_maximized():
            win.unmaximize()

    def _open_settings(self, *_args) -> None:
        if self._win is None:
            return
        dialog = SettingsDialog(self._config, self._win, self._reload_ui_text)
        dialog.present()

    def _show_report(self) -> None:
        if self._stack is not None:
            self._stack.set_visible_child_name("report")

    def _reload_ui_text(self) -> None:
        if not self._stack:
            return
        if self._win is not None:
            self._win.set_title(t("app.title"))
        if self._settings_btn is not None:
            self._settings_btn.set_tooltip_text(t("settings.title"))
        if self._header_brand is not None:
            self._set_brand_link()
        for name, key in (
            ("diag", "tab.diagnostics"),
            ("log", "tab.log"),
            ("report", "tab.report"),
        ):
            child = self._stack.get_child_by_name(name)
            if child is not None:
                self._stack.get_page(child).set_title(t(key))
        if self._diagnostics:
            self._diagnostics.retranslate()
        if self._log:
            self._log.retranslate()
        if self._report:
            self._report.retranslate()
        self._update_header(self._backend.get_state())

    def _poll(self) -> bool:
        state = self._backend.get_state()
        profile = self._backend.get_axis_profile()
        self._update_header(state)
        if self._diagnostics:
            self._diagnostics.update_live(state, profile)
        if self._log:
            self._log.refresh()
        if self._diagnostics and self._report:
            session = self._diagnostics.session
            if session.is_running():
                self._last_report_done = False
            elif not self._last_report_done:
                report = session.get_results()
                if report.overall != TestStatus.NOT_TESTED:
                    self._report.set_report(report)
                    self._last_report_done = True
        return True

    def _update_header(self, state) -> None:
        if self._header_pill is None:
            return
        for cls in ("ok", "bad", "wait"):
            self._header_pill.remove_css_class(cls)
        if state.connected:
            transport = getattr(state, "transport", "") or ""
            if self._header_transport is not None:
                self._header_transport.set_label(transport)
                self._header_transport.set_visible(bool(transport))
            self._header_pill.set_label("●  " + t("status.connected_pill"))
            self._header_pill.add_css_class("ok")
        else:
            if self._header_transport is not None:
                self._header_transport.set_visible(False)
            self._header_pill.set_label("●  " + t("status.disconnected_pill"))
            self._header_pill.add_css_class("bad")

    def _on_close(self, *_args) -> bool:
        if self._diagnostics:
            self._diagnostics.session.stop()
        self._backend.stop()
        return False
