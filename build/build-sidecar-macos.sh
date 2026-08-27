#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ARCH="${1:-$(uname -m)}"
case "$ARCH" in
  x86_64|amd64) TRIPLE="x86_64-apple-darwin" ;;
  aarch64|arm64) TRIPLE="aarch64-apple-darwin" ;;
  *) echo "Unsupported arch: $ARCH" >&2; exit 1 ;;
esac

VENV="$ROOT/.venv"
if [[ ! -d "$VENV" ]]; then
  python3 -m venv "$VENV"
fi

"$VENV/bin/python" -m pip install --upgrade pip >/dev/null
"$VENV/bin/python" -m pip install pyinstaller -r "$ROOT/requirements-desktop.txt" >/dev/null

"$VENV/bin/python" -m PyInstaller --noconfirm --clean --onefile \
  --name gamepad-service \
  --paths "$ROOT" \
  --hidden-import pygame \
  --collect-submodules backend \
  --collect-submodules core \
  "$ROOT/service/gamepad_service.py"

mkdir -p "$ROOT/src-tauri/binaries"
cp "$ROOT/dist/gamepad-service" "$ROOT/src-tauri/binaries/gamepad-service-${TRIPLE}"
chmod +x "$ROOT/src-tauri/binaries/gamepad-service-${TRIPLE}"
echo "Built src-tauri/binaries/gamepad-service-${TRIPLE}"
