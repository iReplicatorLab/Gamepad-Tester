#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

usage() {
  cat <<'EOF'
Usage:
  ./start.sh            Run desktop app from sources (Tauri dev)
  ./start.sh --release  Run pre-built release binary
  ./start.sh --help     Show this help

Desktop app opens in a native window.
EOF
}

ensure_node() {
  if ! command -v npm >/dev/null; then
    echo "npm is required. Install Node.js 24+ and retry." >&2
    exit 1
  fi
  if [[ ! -d node_modules ]]; then
    echo "Installing npm dependencies..."
    npm install
  fi
}

run_dev() {
  ensure_node
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
