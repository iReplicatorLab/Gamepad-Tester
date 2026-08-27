# iReplicator Gamepad Tester

[![Build](https://github.com/iReplicatorLab/Gamepad-Tester/actions/workflows/build.yml/badge.svg)](https://github.com/iReplicatorLab/Gamepad-Tester/actions/workflows/build.yml)

**English** · [Русский](#русский)

Desktop app to test and diagnose **Xbox 360** and **Xbox Series / One** controllers on **Linux**, **Windows**, and **macOS**.

Connect a gamepad over USB or Bluetooth, run guided diagnostics, and get a report with stick drift, trigger range, button checks, and more. Interface is available in **English** and **Russian**.

![iReplicator Gamepad Tester — main window](assets/screenshot.png)

## Features

- **Live monitoring** — buttons, sticks, triggers, and rumble with an Xbox controller diagram
- **Guided diagnostics** — step-by-step tests for sticks, triggers, and buttons (hold, sensitivity, stickiness)
- **Stick analysis** — drift at rest, dead zone, gate shape
- **Report** — score, issues list, export to JSON / CSV
- **Profiles** — auto-detect Xbox 360 vs Xbox One / Series axis layout
- **Cross-platform** — Tauri 2 shell with a unified web UI and Python sidecar for gamepad I/O

## Architecture

```
Web UI (frontend/) → Tauri (src-tauri/) → Python sidecar (service/) → core/ + backend/
```

The Rust shell spawns a local Python service that exposes a REST API. All diagnostic logic stays in Python (`core/`, `backend/`).

## Download

Pre-built packages are attached to [GitHub Releases](https://github.com/iReplicatorLab/Gamepad-Tester/releases) (tag `v*`).

| Platform | Artifact |
|----------|----------|
| Linux x64 | `.deb` and/or `.AppImage` |
| Linux ARM64 | `.deb` and/or `.AppImage` |
| Windows x64 / ARM64 | `.msi` installer |
| macOS Apple Silicon / Intel | `.dmg` |

CI builds all six targets on every release tag (draft + prerelease until published manually).

## Linux

Install from the `.deb` in Releases, or use the AppImage.

**Input access** (read gamepad without root):

```bash
sudo ./setup-input-access.sh
# log out and back in
```

## Windows

Run the `.msi` installer from Releases.

## macOS

Open the `.dmg` from Releases and drag the app to Applications.

On first launch, macOS may block the unsigned app: **System Settings → Privacy & Security → Open Anyway**.

## Run from source

**Requirements:** Node.js 20+, Rust (stable), Python 3.10+, `pygame` / `pygame-ce`, `evdev` (Linux only).

**Linux dev dependencies:**

```bash
sudo apt install libwebkit2gtk-4.1-dev libappindicator3-dev librsvg2-dev patchelf \
  python3-evdev python3-pygame
```

**Start the app (dev):**

```bash
pip install -r requirements.txt
./run.sh
```

**Windows (PowerShell):**

```powershell
pip install -r requirements-desktop.txt
.\start.ps1
```

`run.sh` / `start.ps1` run `npm run tauri dev`, which starts the web UI, Rust shell, and Python sidecar together.

**Windows troubleshooting (dev vs MSI):**

| Step | Command | What it tests |
|------|---------|---------------|
| 1 | `pwsh .\scripts\test-sidecar.ps1` | Python + pygame + HTTP API |
| 2 | `pwsh .\dev.ps1` | Sidecar + browser UI (no Rust) |
| 3 | `.\start.ps1` | Full Tauri dev (Python sidecar) |
| 4 | `pwsh .\build\build-sidecar.ps1` then `npm run tauri build` | Same path as CI / MSI |

If step 3 works but the installed MSI does not, the bundled `gamepad-service` binary is the likely failure point (check `%TEMP%\gamepad-sidecar-err.log` when using `dev.ps1`).

**Sidecar only** (for frontend hacking):

```bash
python3 service/gamepad_service.py --host 127.0.0.1 --port 8765
VITE_SERVICE_URL=http://127.0.0.1:8765 npm run dev
```

## Build locally

```bash
# Python sidecar binary (platform-specific)
./build/build-sidecar.sh          # Linux
./build/build-sidecar-macos.sh    # macOS
pwsh ./build/build-sidecar.ps1    # Windows

# Tauri app bundle
npm ci
npm run tauri build
```

Push a version tag to build everything in GitHub Actions:

```bash
git tag v0.3.0
git push origin v0.3.0
```

## Project layout

| Path | Description |
|------|-------------|
| `frontend/` | Web UI (HTML, CSS, TypeScript) |
| `src-tauri/` | Tauri shell, sidecar lifecycle |
| `service/` | Python HTTP sidecar API |
| `core/` | Diagnostics logic, config, i18n |
| `backend/` | Linux (evdev) / Windows & macOS (pygame) input |
| `locale/` | English / Russian strings |
| `build/` | Sidecar packaging scripts |

## License

AGPL-3.0 — see [LICENSE](LICENSE).

## Links

- GitHub: [iReplicatorLab/Gamepad-Tester](https://github.com/iReplicatorLab/Gamepad-Tester)
- Site: [ireplicator.com](https://ireplicator.com/)

---

## Русский

Десктопное приложение для **тестирования и диагностики** геймпадов **Xbox 360** и **Xbox Series / One** на **Linux**, **Windows** и **macOS**.

Подключите контроллер по USB или Bluetooth, пройдите пошаговую диагностику и получите отчёт: дрифт стиков, ход триггеров, проверка кнопок и другое. Интерфейс на **русском** и **английском**.

## Возможности

- **Мониторинг в реальном времени** — кнопки, стики, триггеры, вибрация и схема геймпада
- **Пошаговая диагностика** — стики, триггеры, кнопки (удержание, чувствительность, залипание)
- **Анализ стиков** — дрифт в покое, мёртвая зона, форма зоны
- **Отчёт** — оценка, список проблем, экспорт JSON / CSV
- **Профили** — автоматическое определение раскладки Xbox 360 и Xbox One / Series
- **Кроссплатформенность** — единый интерфейс Tauri + Web, Python sidecar для ввода

## Скачать

Готовые сборки — в [релизах на GitHub](https://github.com/iReplicatorLab/Gamepad-Tester/releases) (тег `v*`).

| Платформа | Файл |
|-----------|------|
| Linux x64 / ARM64 | `.deb`, `.AppImage` |
| Windows x64 / ARM64 | `.msi` |
| macOS Apple Silicon / Intel | `.dmg` |

## Linux

Установите `.deb` из релиза или используйте AppImage.

**Доступ к вводу** (чтение геймпада без root):

```bash
sudo ./setup-input-access.sh
# перезайдите в систему
```

## Windows

Установите `.msi` из релиза.

## macOS

Откройте `.dmg` из релиза и перетащите приложение в «Программы».

При первом запуске macOS может заблокировать неподписанное приложение: **Системные настройки → Конфиденциальность и безопасность → Всё равно открыть**.

## Запуск из исходников

**Зависимости:** Node.js 20+, Rust (stable), Python 3.10+, `pygame` / `pygame-ce`, `evdev` (только Linux).

```bash
sudo apt install libwebkit2gtk-4.1-dev libappindicator3-dev librsvg2-dev patchelf \
  python3-evdev python3-pygame
pip install -r requirements.txt
./run.sh
```

**Windows:** запустите `run-dev.bat` (или `dev.bat` для теста в браузере).

Диагностика: `pwsh .\scripts\test-sidecar.ps1` → `dev.bat` → `run-dev.bat`. Если dev работает, а MSI — нет, пересоберите sidecar: `pwsh .\build\build-sidecar.ps1`.

## Локальная сборка

```bash
./build/build-sidecar.sh
npm ci
npm run tauri build
```

Сборка в GitHub Actions по тегу:

```bash
git tag v0.3.0
git push origin v0.3.0
```

## Лицензия

AGPL-3.0 — см. [LICENSE](LICENSE).

## Ссылки

- GitHub: [iReplicatorLab/Gamepad-Tester](https://github.com/iReplicatorLab/Gamepad-Tester)
- Сайт: [ireplicator.com](https://ireplicator.com/)
