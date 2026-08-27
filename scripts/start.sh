#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export SDL_GAMECONTROLLERCONFIG="${SDL_GAMECONTROLLERCONFIG:-0300a81c5e040000a102000000010000,X360 Wireless Controller,a:b0,b:b1,x:b2,y:b3,back:b6,guide:b8,start:b7,leftshoulder:b4,rightshoulder:b5,leftstick:b9,rightstick:b10,lefttrigger:a2,righttrigger:a5,leftx:a0,lefty:a1,rightx:a3,righty:a4,dpup:b11,dpdown:b12,dpleft:b13,dpright:b14,platform:Linux,}"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/start.sh            Run desktop app from sources (Tauri dev)
  ./scripts/start.sh --release  Run pre-built release binary
  ./scripts/start.sh --help     Show this help

Desktop app opens in a native window. Python sidecar starts automatically.
EOF
}

ensure_node() {
  if ! command -v npm >/dev/null; then
    echo "npm is required. Install Node.js 20+ and retry." >&2
    exit 1
  fi
  if [[ ! -d node_modules ]]; then
    echo "Installing npm dependencies..."
    npm install
  fi
}

ensure_python_sidecar_deps() {
  local venv="$ROOT/.venv"
  if [[ ! -d "$venv" ]]; then
    echo "Creating Python venv..."
    python3 -m venv "$venv"
  fi
  if ! "$venv/bin/python" -c "import pygame" >/dev/null 2>&1; then
    echo "Installing Python sidecar dependencies..."
    "$venv/bin/pip" install -q -r "$ROOT/requirements.txt" pyinstaller
  fi
  export PATH="$venv/bin:$PATH"
}

run_dev() {
  ensure_node
  ensure_python_sidecar_deps
  echo "Starting desktop app (Tauri dev)..."
  exec npm run tauri dev
}

run_release() {
  local bin="$ROOT/src-tauri/target/release/ireplicator-gamepad-tester"
  if [[ ! -x "$bin" ]]; then
    echo "Release binary not found: $bin" >&2
    echo "Build it first: npm run tauri build" >&2
    exit 1
  fi
  echo "Starting desktop app (release)..."
  exec "$bin"
}

case "${1:-}" in
  --help|-h)
    usage
    ;;
  --release|-r)
    run_release
    ;;
  "")
    run_dev
    ;;
  *)
    echo "Unknown option: $1" >&2
    usage >&2
    exit 1
    ;;
esac
