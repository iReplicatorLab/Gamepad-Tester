# Browser-only dev: Python sidecar + Vite (no Tauri/Rust needed)
param(
  [int]$Port = 8765
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Venv = Join-Path $Root ".venv"
if (-not (Test-Path $Venv)) {
  Write-Host "Creating Python venv..."
  python -m venv $Venv
}

$Python = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $Python)) {
  throw "Python venv is broken. Delete .venv and run again."
}

& $Python -m pip install -q -r (Join-Path $Root "requirements-desktop.txt")

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
  throw "npm is required. Install Node.js 20+ and retry."
}
if (-not (Test-Path "$Root\node_modules")) {
  npm install
}

$Sidecar = Start-Process -FilePath $Python `
  -ArgumentList @(
    (Join-Path $Root "service\gamepad_service.py"),
    "--host", "127.0.0.1",
    "--port", "$Port"
  ) `
  -PassThru `
  -NoNewWindow `
  -RedirectStandardOutput (Join-Path $env:TEMP "gamepad-sidecar-out.log") `
  -RedirectStandardError (Join-Path $env:TEMP "gamepad-sidecar-err.log")

try {
  $ready = $false
  for ($i = 0; $i -lt 40; $i++) {
    try {
      $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/health" -UseBasicParsing -TimeoutSec 2
      if ($resp.StatusCode -eq 200) {
        $ready = $true
        break
      }
    } catch {
      Start-Sleep -Milliseconds 250
    }
  }

  if (-not $ready) {
    $err = Get-Content (Join-Path $env:TEMP "gamepad-sidecar-err.log") -ErrorAction SilentlyContinue
    throw "Sidecar did not start on port $Port.`nStderr:`n$err"
  }

  $env:VITE_SERVICE_URL = "http://127.0.0.1:$Port"
  Write-Host "Sidecar: $env:VITE_SERVICE_URL"
  Write-Host "Open:    http://localhost:5173"
  Write-Host "Sidecar logs: $env:TEMP\gamepad-sidecar-err.log"
  npm run dev
} finally {
  if ($Sidecar -and -not $Sidecar.HasExited) {
    Stop-Process -Id $Sidecar.Id -Force -ErrorAction SilentlyContinue
  }
}
