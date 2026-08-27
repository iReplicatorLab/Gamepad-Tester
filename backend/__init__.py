"""Backend package."""

from __future__ import annotations

import sys

from backend.protocol import PadState

__all__ = ["PadState"]

if sys.platform.startswith("linux"):
    from backend.linux import LinuxGamepadBackend

    __all__ += ["LinuxGamepadBackend"]
elif sys.platform in ("win32", "darwin"):
    from backend.windows import WindowsGamepadBackend

    __all__ += ["WindowsGamepadBackend"]
