#!/usr/bin/env bash
# Доступ к /dev/input/* для чтения геймпада без root.
set -euo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Запустите: sudo $0"
  exit 1
fi

TARGET_USER="${SUDO_USER:-$USER}"
usermod -aG input "$TARGET_USER"
echo "Пользователь $TARGET_USER добавлен в группу input."
echo "Перезайдите в систему (или перезагрузите ПК), затем запустите ./run.sh"
