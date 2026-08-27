#!/usr/bin/env python3
"""iReplicator Gamepad Tester — Python sidecar HTTP service."""

from __future__ import annotations

import argparse
import atexit
import signal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from service.http_server import start_http_server  # noqa: E402
from service.state import GamepadService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Gamepad tester sidecar API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()

    service = GamepadService()
    server = start_http_server(service, args.host, args.port)
    host, port = server.server_address

    print(f"SERVICE_URL=http://{host}:{port}", flush=True)

    def shutdown() -> None:
        server.shutdown()
        service.shutdown()

    atexit.register(shutdown)

    def handle_signal(signum: int, _frame) -> None:
        shutdown()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    try:
        signal.pause()
    except AttributeError:
        import time

        while True:
            time.sleep(3600)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
