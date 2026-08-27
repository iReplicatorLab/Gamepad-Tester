#!/usr/bin/env python3
"""iReplicator Gamepad Tester — Linux entry point."""

from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw  # noqa: E402

from ui.linux.app import GamepadTesterApp  # noqa: E402


def main() -> int:
    Adw.init()
    app = GamepadTesterApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
