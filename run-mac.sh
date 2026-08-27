#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Этот скрипт для macOS. На Linux используйте ./run.sh" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "Нужен python3. Установите: brew install python@3.12" >&2
  exit 1
fi

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q pygame pillow

echo "Запуск iReplicator Gamepad Tester..."
exec .venv/bin/python3 gamepad_tester_windows.py "$@"
