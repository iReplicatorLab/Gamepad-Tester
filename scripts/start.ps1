# iReplicator Gamepad Tester — run from source on Windows
param(
  [switch]$Release,
  [switch]$Help
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Show-Usage {
  @"
Usage:
  .\scripts\start.ps1            Run desktop app from sources (Tauri dev)
  .\scripts\start.ps1 -Release   Run pre-built release binary
  .\scripts\start.ps1 -Help      Show this help

Dev mode starts the Python sidecar automatically (no PyInstaller build needed).
If dev works but the MSI installer does not, the problem is likely in the bundled sidecar.
"@
}

if ($Help) {
  Show-Usage
  exit 0
}

function Ensure-Node {
  if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm is required. Install Node.js 20+ from https://nodejs.org/ and retry."
  }
  if (-not (Test-Path "$Root\node_modules")) {
    Write-Host "Installing npm dependencies..."
    npm install
  }
}

function Ensure-PythonSidecarDeps {
  $Venv = Join-Path $Root ".venv"
  if (-not (Test-Path $Venv)) {
    Write-Host "Creating Python venv..."
    python -m venv $Venv
  }
  $Python = Join-Path $Venv "Scripts\python.exe"
  if (-not (Test-Path $Python)) {
    throw "Python venv is broken. Delete .venv and run again."
  }
  $ok = & $Python -c "import pygame" 2>$null
  if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing Python sidecar dependencies..."
    & $Python -m pip install -q -r (Join-Path $Root "requirements-desktop.txt")
  }
  $env:PATH = "$(Split-Path $Python -Parent);$env:PATH"
}

function Start-Dev {
  Ensure-Node
  Ensure-PythonSidecarDeps
  Write-Host "Starting desktop app (Tauri dev)..."
  Write-Host "Tip: browser-only test: .\scripts\dev.ps1"
  npm run tauri dev
}

function Start-Release {
  $Bin = Join-Path $Root "src-tauri\target\release\ireplicator-gamepad-tester.exe"
  if (-not (Test-Path $Bin)) {
    throw @"
Release binary not found: $Bin
Build it first:
  pwsh .\build\build-sidecar.ps1
  npm ci
  npm run tauri build
"@
  }
  Write-Host "Starting desktop app (release)..."
  & $Bin
}

if ($Release) {
  Start-Release
} else {
  Start-Dev
}
