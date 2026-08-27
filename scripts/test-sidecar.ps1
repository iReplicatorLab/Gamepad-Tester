# Quick check: can the Python sidecar start and see a gamepad?
param(
  [int]$Port = 8765,
  [int]$Seconds = 10
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "=== Gamepad sidecar smoke test ==="
Write-Host "Project: $Root"
Write-Host ""

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
  Write-Host "[FAIL] python not found in PATH"
  exit 1
}
Write-Host "[OK]   python: $($py.Source)"
& python --version

$pygameOk = $false
try {
  python -c "import pygame; print('pygame', pygame.version.ver)"
  $pygameOk = $LASTEXITCODE -eq 0
} catch {}
if (-not $pygameOk) {
  Write-Host "[FAIL] pygame not installed. Run: pip install pygame-ce"
  exit 1
}
Write-Host "[OK]   pygame import"

$proc = Start-Process -FilePath python `
  -ArgumentList @("service\gamepad_service.py", "--host", "127.0.0.1", "--port", "$Port") `
  -PassThru -NoNewWindow `
  -RedirectStandardOutput "$env:TEMP\gpt-sidecar-out.txt" `
  -RedirectStandardError "$env:TEMP\gpt-sidecar-err.txt"

try {
  Start-Sleep -Seconds 2

  try {
    $health = Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -TimeoutSec 3
    Write-Host "[OK]   /api/health -> $($health | ConvertTo-Json -Compress)"
  } catch {
    Write-Host "[FAIL] sidecar HTTP not reachable on port $Port"
    Write-Host "stdout:"
    Get-Content "$env:TEMP\gpt-sidecar-out.txt" -ErrorAction SilentlyContinue
    Write-Host "stderr:"
    Get-Content "$env:TEMP\gpt-sidecar-err.txt" -ErrorAction SilentlyContinue
    exit 1
  }

  try {
    $state = Invoke-RestMethod "http://127.0.0.1:$Port/api/state" -TimeoutSec 3
    Write-Host "[INFO] pad connected=$($state.connected) name=$($state.name)"
    if (-not $state.connected) {
      Write-Host "[WARN] No gamepad detected. Plug in an Xbox controller and re-run."
    }
  } catch {
    Write-Host "[FAIL] /api/state error: $_"
    exit 1
  }

  Write-Host ""
  Write-Host "Listening for $Seconds seconds (move sticks / press buttons)..."
  Start-Sleep -Seconds $Seconds

  Write-Host "[DONE] Sidecar works. If MSI fails but this passes, rebuild sidecar:"
  Write-Host "       pwsh .\build\build-sidecar.ps1"
} finally {
  if ($proc -and -not $proc.HasExited) {
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
  }
}
