@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title iReplicator Gamepad Tester - dev

echo.
echo === iReplicator Gamepad Tester (source dev) ===
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python not found. Install Python 3.10+ and add it to PATH.
  goto :fail
)

where npm >nul 2>&1
if errorlevel 1 (
  echo [ERROR] npm not found. Install Node.js 20+ from https://nodejs.org/
  goto :fail
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating Python venv...
  python -m venv .venv
  if errorlevel 1 goto :fail
)

set "PY=%CD%\.venv\Scripts\python.exe"
set "PIP=%CD%\.venv\Scripts\pip.exe"

"%PY%" -c "import pygame" >nul 2>&1
if errorlevel 1 (
  echo Installing Python sidecar dependencies...
  "%PIP%" install -r requirements-desktop.txt
  if errorlevel 1 goto :fail
)

if not exist "node_modules\" (
  echo Installing npm dependencies...
  call npm install
  if errorlevel 1 goto :fail
)

set "PATH=%CD%\.venv\Scripts;%PATH%"

echo.
echo Starting desktop app (Tauri dev)...
echo Close this window to stop the app.
echo.

call npm run tauri dev
if errorlevel 1 goto :fail

endlocal
exit /b 0

:fail
echo.
echo Dev launch failed. See errors above.
pause
endlocal
exit /b 1
