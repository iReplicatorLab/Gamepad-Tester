"""SDL/pygame environment for headless joystick input (Windows / macOS)."""

from __future__ import annotations

import os
import sys


def configure_sdl_env() -> None:
    """Set SDL env vars before pygame is imported."""
    # Dummy drivers keep SDL from registering NSApplication on macOS,
    # which would break tkinter (SDLApplication vs Tcl/Tk).
    if sys.platform in ("win32", "linux", "darwin"):
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    if sys.platform == "darwin":
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
