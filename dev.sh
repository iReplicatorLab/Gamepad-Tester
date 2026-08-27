#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

export SDL_GAMECONTROLLERCONFIG="${SDL_GAMECONTROLLERCONFIG:-0300a81c5e040000a102000000010000,X360 Wireless Controller,a:b0,b:b1,x:b2,y:b3,back:b6,guide:b8,start:b7,leftshoulder:b4,rightshoulder:b5,leftstick:b9,rightstick:b10,lefttrigger:a2,righttrigger:a5,leftx:a0,lefty:a1,rightx:a3,righty:a4,dpup:b11,dpdown:b12,dpleft:b13,dpright:b14,platform:Linux,}"

PORT="${PORT:-8765}"
VENV=".venv"

if [[ ! -d "$VENV" ]]; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q -r requirements.txt
fi

if ! command -v npm >/dev/null; then
  echo "npm is required. Install Node.js 24+ and retry." >&2
  exit 1
fi

if [[ ! -d node_modules ]]; then
  npm install
fi

cleanup() {
  [[ -n "${SIDECAR_PID:-}" ]] && kill "$SIDECAR_PID" 2>/dev/null || true
}
trap cleanup EXIT

"$VENV/bin/python3" service/gamepad_service.py --host 127.0.0.1 --port "$PORT" &
SIDECAR_PID=$!

for _ in $(seq 1 40); do
  if curl -fsS "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done

export VITE_SERVICE_URL="http://127.0.0.1:${PORT}"
echo "Sidecar: $VITE_SERVICE_URL"
echo "Open:    http://localhost:5173"
exec npm run dev
