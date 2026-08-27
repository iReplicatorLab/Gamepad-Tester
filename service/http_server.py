"""HTTP API for the gamepad sidecar."""

from __future__ import annotations

import json
import mimetypes
import tempfile
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

from core.export import export_csv, export_json
from core.paths import asset_path, locale_dir
from service.serialize import config_dict

if TYPE_CHECKING:
    from service.state import GamepadService


class ApiHandler(BaseHTTPRequestHandler):
    service: GamepadService

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _send_json(self, payload: object, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else {}

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path)
        parts = [p for p in path.path.split("/") if p]

        if parts == ["api", "health"]:
            self._send_json({"ok": True})
            return

        if parts == ["api", "state"]:
            self.service.refresh_log()
            self._send_json(self.service.get_state_payload())
            return

        if parts == ["api", "config"]:
            self._send_json(config_dict(self.service.config))
            return

        if parts == ["api", "diagnostics", "status"]:
            self._send_json(self.service.get_diagnostics_payload())
            return

        if parts == ["api", "report"]:
            self._send_json(self.service.get_report_payload())
            return

        if parts == ["api", "log"]:
            since = int(parse_qs(path.query).get("since", ["0"])[0])
            self._send_json(self.service.get_log(since))
            return

        if len(parts) == 3 and parts[0] == "api" and parts[1] == "locale":
            locale_file = locale_dir() / f"{parts[2]}.json"
            if locale_file.is_file():
                self._send_json(json.loads(locale_file.read_text(encoding="utf-8")))
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
            return

        if len(parts) == 3 and parts[0] == "api" and parts[1] == "assets":
            asset = asset_path(parts[2])
            if asset.is_file():
                data = asset.read_bytes()
                mime, _ = mimetypes.guess_type(str(asset))
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", mime or "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
            return

        if parts == ["api", "export", "json"]:
            report = self.service.session.get_results()
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
                export_json(report, Path(fh.name))
                text = Path(fh.name).read_text(encoding="utf-8")
            self._send_json({"content": text})
            return

        if parts == ["api", "export", "csv"]:
            report = self.service.session.get_results()
            with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8", newline="") as fh:
                export_csv(report, Path(fh.name))
                text = Path(fh.name).read_text(encoding="utf-8")
            self._send_json({"content": text})
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_PUT(self) -> None:  # noqa: N802
        path = urlparse(self.path).path.strip("/").split("/")
        if path == ["api", "config"]:
            updated = self.service.update_config(self._read_json())
            self._send_json(updated)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path.strip("/").split("/")
        body = self._read_json()

        if path == ["api", "diagnostics", "start"]:
            tests = body.get("tests")
            if tests is not None and not isinstance(tests, list):
                tests = None
            self.service.start_diagnostics(tests)
            self._send_json({"ok": True})
            return

        if path == ["api", "diagnostics", "stop"]:
            self.service.stop_diagnostics()
            self._send_json({"ok": True})
            return

        if path == ["api", "diagnostics", "skip"]:
            self.service.skip_step()
            self._send_json({"ok": True})
            return

        if path == ["api", "rumble"]:
            ok = self.service.rumble(
                float(body.get("left", 0)),
                float(body.get("right", 0)),
                int(body.get("duration_ms", 500)),
            )
            self._send_json({"ok": ok})
            return

        if path == ["api", "rumble", "stop"]:
            self.service.stop_rumble()
            self._send_json({"ok": True})
            return

        self.send_error(HTTPStatus.NOT_FOUND)


def start_http_server(service: GamepadService, host: str, port: int) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (ApiHandler,), {})
    handler.service = service
    server = ThreadingHTTPServer((host, port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
