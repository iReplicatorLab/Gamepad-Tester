#!/usr/bin/env bash
# Запуск .app из терминала macOS — показывает stderr/stdout при падении.
set -euo pipefail

APP="${1:-}"
if [[ -z "$APP" ]]; then
  ROOT="$(cd "$(dirname "$0")/.." && pwd)"
  for candidate in \
    "$ROOT/build/dist/macos-arm64/iReplicator Gamepad Tester.app" \
    "$ROOT/build/dist/macos-x64/iReplicator Gamepad Tester.app" \
    "./iReplicator Gamepad Tester.app"; do
    if [[ -d "$candidate" ]]; then
      APP="$candidate"
      break
    fi
  done
fi

if [[ -z "$APP" || ! -d "$APP" ]]; then
  echo "Usage: $0 [/path/to/iReplicator Gamepad Tester.app]" >&2
  exit 1
fi

BIN="$APP/Contents/MacOS/iReplicator Gamepad Tester"
if [[ ! -x "$BIN" ]]; then
  echo "Executable not found: $BIN" >&2
  exit 1
fi

echo "Launching: $BIN"
echo "Press Ctrl+C to stop."
exec "$BIN" 2>&1
