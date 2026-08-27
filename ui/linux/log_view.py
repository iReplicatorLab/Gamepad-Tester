"""Вкладка «Журнал»."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from core.i18n import t


class LogView(Gtk.Box):
    def __init__(self, backend) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._backend = backend
        self._buffer = Gtk.TextBuffer()
        view = Gtk.TextView(buffer=self._buffer, editable=False, monospace=True)
        view.add_css_class("telem-mono")
        view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        scroll.set_min_content_height(300)
        scroll.set_child(view)
        group = Adw.PreferencesGroup(title=t("tab.log"))
        self._group = group
        group.add(scroll)
        self.append(group)

    def retranslate(self) -> None:
        self._group.set_title(t("tab.log"))
        self.refresh()

    def refresh(self) -> None:
        events = self._backend.logger.recent_events(200)
        samples = self._backend.logger.recent_samples(50)
        lines = []
        for e in events[-100:]:
            lines.append(f"[{e.timestamp_ns}] {e.event_type} {e.code}={e.value}")
        for s in samples[-20:]:
            lines.append(f"[sample] axes={ {k: round(v, 3) for k, v in s.axes.items()} }")
        text = "\n".join(lines) if lines else t("log.empty")
        self._buffer.set_text(text)
