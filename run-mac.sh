#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Этот скрипт для macOS. На Linux используйте ./run.sh" >&2
  exit 1
fi

python_has_tk() {
  local py="$1"
  "$py" -c "import tkinter" >/dev/null 2>&1
}

pick_python() {
  local candidate
  for candidate in python3.12 python3.13 python3.14 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && python_has_tk "$(command -v "$candidate")"; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

if ! PYTHON="$(pick_python)"; then
  cat >&2 <<'EOF'
Не найден Python с поддержкой tkinter (GUI).

Установите tkinter для вашей версии Python, например:
  brew install python-tk@3.14

Проверка после установки:
  python3 -m tkinter

Если откроется маленькое тестовое окно — снова запустите:
  ./run-mac.sh
EOF
  exit 1
fi

echo "Python: $PYTHON ($("$PYTHON" --version))"

if [[ -d .venv ]]; then
  if ! .venv/bin/python -c "import tkinter" >/dev/null 2>&1; then
    echo "Пересоздаю .venv: в старом окружении нет tkinter"
    rm -rf .venv
  fi
fi

if [[ ! -d .venv ]]; then
  "$PYTHON" -m venv .venv
fi

.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q pygame pillow

echo "Запуск iReplicator Gamepad Tester..."
exec .venv/bin/python gamepad_tester_windows.py "$@"
