"""SDL/pygame environment for headless joystick input (Windows / macOS)."""

from __future__ import annotations

import os
import sys


def configure_sdl_env() -> None:
    """Set SDL env vars before pygame is imported."""
    if sys.platform in ("win32", "linux"):
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


def prepare_pygame_before_tk() -> None:
    """Initialize pygame/SDL before tkinter (required on macOS)."""
    configure_sdl_env()
    import pygame

    if pygame.get_init():
        return
    pygame.init()
    if not pygame.joystick.get_init():
        pygame.joystick.init()
