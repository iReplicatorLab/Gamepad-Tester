param(
  [ValidateSet("x64", "arm64")]
  [string]$Arch = "x64"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Triple = if ($Arch -eq "arm64") { "aarch64-pc-windows-msvc" } else { "x86_64-pc-windows-msvc" }

$Venv = Join-Path $Root ".venv"
if (-not (Test-Path $Venv)) {
  python -m venv $Venv
}

$Pip = Join-Path $Venv "Scripts\pip.exe"
$PyInstaller = Join-Path $Venv "Scripts\pyinstaller.exe"

& $Pip install --upgrade pip pyinstaller pygame-ce | Out-Null

& $PyInstaller --noconfirm --clean --onefile `
  --name gamepad-service `
  --paths $Root `
  --hidden-import pygame `
  --collect-submodules backend `
  --collect-submodules core `
  "$Root\service\gamepad_service.py"

$DestDir = Join-Path $Root "src-tauri\binaries"
New-Item -ItemType Directory -Force -Path $DestDir | Out-Null
$Dest = Join-Path $DestDir "gamepad-service-$Triple.exe"
Copy-Item -Force (Join-Path $Root "dist\gamepad-service.exe") $Dest
Write-Host "Built $Dest"
