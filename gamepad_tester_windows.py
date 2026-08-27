#!/usr/bin/env python3
"""iReplicator Gamepad Tester — Windows / macOS entry point."""

from __future__ import annotations

import sys
import traceback

from backend.sdl_env import configure_sdl_env, prepare_pygame_before_tk

configure_sdl_env()


def main() -> int:
    try:
        if sys.platform == "darwin":
            prepare_pygame_before_tk()

        import tkinter as tk

        from ui.windows.app import GamepadTesterApp

        root = tk.Tk()
        GamepadTesterApp(root)
        root.mainloop()
        return 0
    except Exception:
        text = traceback.format_exc()
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("iReplicator Gamepad Tester", text)
            root.destroy()
        except Exception:
            sys.stderr.write(text)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
