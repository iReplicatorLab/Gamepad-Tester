#!/usr/bin/env bash
# Сборка iReplicator Gamepad Tester для macOS (x64 / arm64)
set -euo pipefail

ARCH="${1:-arm64}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VERSION="0.2.1"
APP_NAME="iReplicator Gamepad Tester"
OUT_DIR="$ROOT/build/dist/macos-$ARCH"

cd "$ROOT"

python3 -m pip install --upgrade pip
python3 -m pip install pyinstaller pygame pillow

PY_ARGS=(
  --noconfirm
  --clean
  --windowed
  --name "$APP_NAME"
  --distpath "$OUT_DIR"
  --workpath "$ROOT/build/pyinstaller/work-macos-$ARCH"
  --specpath "$ROOT/build/pyinstaller"
  --hidden-import pygame
  --hidden-import pygame.joystick
  --hidden-import PIL._tkinter_finder
  --collect-submodules PIL
  --collect-submodules core
  --collect-submodules backend
  --collect-submodules ui
  --add-data "$ROOT/locale:locale"
  --add-data "$ROOT/assets:assets"
  gamepad_tester_windows.py
)

case "$ARCH" in
  arm64)
    PY_ARGS+=(--target-architecture arm64)
    ;;
  x64)
    PY_ARGS+=(--target-architecture x86_64)
    ;;
  *)
    echo "Unsupported arch: $ARCH (use arm64 or x64)" >&2
    exit 1
    ;;
esac

python3 -m PyInstaller "${PY_ARGS[@]}"

APP_BUNDLE="$OUT_DIR/$APP_NAME.app"
if [[ ! -d "$APP_BUNDLE" ]]; then
  echo "Build failed: $APP_BUNDLE not found" >&2
  exit 1
fi

ZIP="$ROOT/build/dist/ireplicator-gamepad-tester_${VERSION}_mac-${ARCH}.zip"
rm -f "$ZIP"
ditto -c -k --sequesterRsrc --keepParent "$APP_BUNDLE" "$ZIP"

echo "OK: $APP_BUNDLE"
echo "ZIP: $ZIP"
