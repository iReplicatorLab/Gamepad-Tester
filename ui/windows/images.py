"""Загрузка PNG для tkinter (Windows / macOS)."""

from __future__ import annotations

from pathlib import Path

import tkinter as tk
from PIL import Image, ImageTk


def load_png_photo(path: Path, max_width: int = 520) -> tk.PhotoImage:
    image = Image.open(path)
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA")
    if image.width > max_width:
        ratio = max_width / image.width
        size = (max_width, max(1, int(image.height * ratio)))
        image = image.resize(size, Image.Resampling.LANCZOS)
    return ImageTk.PhotoImage(image)
