@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

title iReplicator Gamepad Tester - browser dev

set "PORT=8765"

echo.
echo === Gamepad Tester - browser test (no Rust/Tauri) ===
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python not found.
  goto :fail
)

where npm >nul 2>&1
if errorlevel 1 (
  echo [ERROR] npm not found.
  goto :fail
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating Python venv...
  python -m venv .venv
  if errorlevel 1 goto :fail
)

set "PY=%CD%\.venv\Scripts\python.exe"
set "PIP=%CD%\.venv\Scripts\pip.exe"

"%PIP%" install -q -r "%CD%\requirements-desktop.txt"
if errorlevel 1 goto :fail

if not exist "node_modules\" (
  call npm install
  if errorlevel 1 goto :fail
)

echo Starting Python sidecar on port %PORT%...
start "gamepad-sidecar" /b "%PY%" "%CD%\service\gamepad_service.py" --host 127.0.0.1 --port %PORT%

set "READY=0"
for /l %%i in (1,1,40) do (
  powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri 'http://127.0.0.1:%PORT%/api/health' -UseBasicParsing -TimeoutSec 2).StatusCode } catch { exit 1 }" >nul 2>&1
  if not errorlevel 1 (
    set "READY=1"
    goto :sidecar_ok
  )
  timeout /t 1 /nobreak >nul
)

:sidecar_ok
if "%READY%"=="0" (
  echo [ERROR] Sidecar did not start on port %PORT%.
  goto :fail
)

set "VITE_SERVICE_URL=http://127.0.0.1:%PORT%"
echo Sidecar: %VITE_SERVICE_URL%
echo Open:    http://localhost:5173
echo.

call npm run dev
goto :done

:fail
echo.
pause
exit /b 1

:done
endlocal
exit /b 0
