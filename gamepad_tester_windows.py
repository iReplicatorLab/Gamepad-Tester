#!/usr/bin/env python3
"""iReplicator Gamepad Tester — Windows / macOS entry point."""

from __future__ import annotations

import sys
import traceback


def main() -> int:
    try:
        import tkinter as tk
        from tkinter import messagebox

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
