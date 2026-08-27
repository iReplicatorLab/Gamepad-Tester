#!/usr/bin/env python3
"""iReplicator Gamepad Tester — Windows entry point."""

from __future__ import annotations

import sys
import tkinter as tk

from ui.windows.app import GamepadTesterApp


def main() -> int:
    root = tk.Tk()
    GamepadTesterApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
