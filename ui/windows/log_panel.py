"""Windows — вкладка «Журнал»."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, scrolledtext

from core.i18n import t


class LogPanel(ttk.Frame):
    def __init__(self, master, backend, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self._backend = backend
        self._text = scrolledtext.ScrolledText(self, height=24, state="disabled", font=("Consolas", 9))
        self._text.pack(fill="both", expand=True, padx=8, pady=8)

    def refresh(self) -> None:
        events = self._backend.logger.recent_events(200)
        samples = self._backend.logger.recent_samples(50)
        lines = []
        for e in events[-100:]:
            lines.append(f"[{e.timestamp_ns}] {e.event_type} {e.code}={e.value}")
        for s in samples[-20:]:
            lines.append(f"[sample] { {k: round(v, 3) for k, v in s.axes.items()} }")
        text = "\n".join(lines) if lines else t("log.empty")
        self._text.configure(state="normal")
        self._text.delete("1.0", tk.END)
        self._text.insert(tk.END, text)
        self._text.configure(state="disabled")
