"""Windows tkinter widgets."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from pad_common import BUTTONS, DPAD_BUTTONS, diagram_kind, normalize_trigger
from core.paths import asset_path
from ui.windows.images import load_png_photo


class MonitoringPanel(ttk.Frame):
    def __init__(self, master, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self.status_var = tk.StringVar(value="…")
        self.profile_var = tk.StringVar(value="—")
        self.btn_labels: dict[int, tk.Label] = {}
        self.lx_var = tk.DoubleVar(value=0)
        self.ly_var = tk.DoubleVar(value=0)
        self.rx_var = tk.DoubleVar(value=0)
        self.ry_var = tk.DoubleVar(value=0)
        self.lt_var = tk.DoubleVar(value=0)
        self.rt_var = tk.DoubleVar(value=0)
        self.left_motor = tk.IntVar(value=80)
        self.right_motor = tk.IntVar(value=80)
        self.duration = tk.IntVar(value=1000)
        self._build()

    def _build(self) -> None:
        pad = {"padx": 8, "pady": 4}
        top = ttk.Frame(self)
        top.pack(fill="x", **pad)
        ttk.Label(top, text="Status:").pack(side="left")
        ttk.Label(top, textvariable=self.status_var).pack(side="left", padx=8)
        ttk.Label(top, text="Profile:").pack(side="left", padx=(16, 0))
        ttk.Label(top, textvariable=self.profile_var).pack(side="left", padx=8)

        self._pad_kind = ""
        self._pad_photo = None
        self._pad_label = tk.Label(self, bg="#000000")
        self._pad_label.pack(pady=4)
        self._set_pad_image("series")

        btns = ttk.LabelFrame(self, text="Buttons")
        btns.pack(fill="x", **pad)
        grid = ttk.Frame(btns)
        grid.pack(**pad)
        for idx, name in BUTTONS + DPAD_BUTTONS:
            lbl = tk.Label(
                grid,
                text=name,
                width=4,
                height=2,
                relief="ridge",
                bg="#2b2b2b",
                fg="white",
                font=("Segoe UI", 9, "bold"),
            )
            lbl.grid(row=idx // 8, column=idx % 8, padx=3, pady=3)
            self.btn_labels[idx] = lbl

        analog = ttk.Frame(self)
        analog.pack(fill="both", expand=True, **pad)
        left = ttk.LabelFrame(analog, text="Left stick / LT")
        left.pack(side="left", fill="both", expand=True, padx=(0, 4))
        right = ttk.LabelFrame(analog, text="Right stick / RT")
        right.pack(side="left", fill="both", expand=True, padx=(4, 0))
        for frame, lx, ly, trig, label in (
            (left, self.lx_var, self.ly_var, self.lt_var, "LT"),
            (right, self.rx_var, self.ry_var, self.rt_var, "RT"),
        ):
            ttk.Label(frame, text="X").pack(anchor="w")
            ttk.Progressbar(frame, variable=lx, maximum=100).pack(fill="x", pady=2)
            ttk.Label(frame, text="Y").pack(anchor="w")
            ttk.Progressbar(frame, variable=ly, maximum=100).pack(fill="x", pady=2)
            ttk.Label(frame, text=label).pack(anchor="w")
            ttk.Progressbar(frame, variable=trig, maximum=100).pack(fill="x", pady=2)

        rumble = ttk.LabelFrame(self, text="Rumble")
        rumble.pack(fill="x", **pad)
        row = ttk.Frame(rumble)
        row.pack(fill="x", **pad)
        ttk.Label(row, text="Left %").grid(row=0, column=0, sticky="w")
        ttk.Scale(row, from_=0, to=100, variable=self.left_motor, orient="horizontal").grid(
            row=0, column=1, sticky="ew", padx=8
        )
        ttk.Label(row, text="Right %").grid(row=1, column=0, sticky="w")
        ttk.Scale(row, from_=0, to=100, variable=self.right_motor, orient="horizontal").grid(
            row=1, column=1, sticky="ew", padx=8
        )
        ttk.Label(row, text="Duration ms").grid(row=2, column=0, sticky="w")
        ttk.Spinbox(row, from_=100, to=5000, increment=100, textvariable=self.duration, width=8).grid(
            row=2, column=1, sticky="w", padx=8
        )
        row.columnconfigure(1, weight=1)
        self.rumble_actions = ttk.Frame(rumble)
        self.rumble_actions.pack(fill="x", **pad)

    def _set_pad_image(self, kind: str) -> None:
        if kind not in ("360", "series"):
            kind = "series"
        if kind == self._pad_kind:
            return
        path = asset_path(f"xbox-{kind}.png")
        if not path.is_file():
            return
        photo = load_png_photo(path)
        self._pad_photo = photo
        self._pad_label.configure(image=photo)
        self._pad_kind = kind

    def set_rumble_handlers(self, on_test, on_stop) -> None:
        for child in self.rumble_actions.winfo_children():
            child.destroy()
        for text, left, right in (("L", 1.0, 0.0), ("R", 0.0, 1.0), ("LR", 1.0, 1.0)):
            ttk.Button(
                self.rumble_actions,
                text=text,
                command=lambda l=left, r=right: on_test(l, r),
            ).pack(side="left", padx=4)

    def update_state(self, connected: bool, name: str, profile_label: str, buttons, axes, profile) -> None:
        self.status_var.set(name if connected else "No gamepad")
        self.profile_var.set(profile_label if connected else "—")
        self._set_pad_image(diagram_kind(getattr(profile, "name", ""), name if connected else ""))
        for idx, lbl in self.btn_labels.items():
            active = buttons.get(idx, False)
            lbl.configure(bg="#107c10" if active else "#2b2b2b", fg="white")
        mapped = profile.read(axes) if connected else {
            k: 0.0 for k in ("left_x", "left_y", "right_x", "right_y", "lt", "rt")
        }
        self.lx_var.set((mapped["left_x"] + 1) * 50)
        self.ly_var.set((mapped["left_y"] + 1) * 50)
        self.rx_var.set((mapped["right_x"] + 1) * 50)
        self.ry_var.set((mapped["right_y"] + 1) * 50)
        self.lt_var.set(normalize_trigger(mapped["lt"]) * 100)
        self.rt_var.set(normalize_trigger(mapped["rt"]) * 100)

    def get_rumble_params(self) -> tuple[float, float, int]:
        return (
            self.left_motor.get() / 100.0,
            self.right_motor.get() / 100.0,
            int(self.duration.get()),
        )
