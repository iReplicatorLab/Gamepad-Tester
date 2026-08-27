# Сборка iReplicator Gamepad Tester для Windows (x64 или ARM64)
param(
    [ValidateSet("x64", "arm64")]
    [string]$Arch = "x64"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$Version = "0.2.0"
$AppName = "iReplicator Gamepad Tester"
$OutDir = Join-Path $Root "build\dist\windows-$Arch"

Set-Location $Root

python -m pip install --upgrade pip
python -m pip install pyinstaller pygame

$PyArgs = @(
    "--noconfirm",
    "--clean",
    "--onefile",
    "--windowed",
    "--name", $AppName,
    "--distpath", $OutDir,
    "--workpath", (Join-Path $Root "build\pyinstaller\work-$Arch"),
    "--specpath", (Join-Path $Root "build\pyinstaller"),
    "--hidden-import", "pygame",
    "--hidden-import", "pygame.joystick",
    "--collect-submodules", "core",
    "--collect-submodules", "backend",
    "--collect-submodules", "ui",
    "--add-data", (Join-Path $Root "locale;locale"),
    "--add-data", (Join-Path $Root "assets;assets"),
    "gamepad_tester_windows.py"
)

if ($Arch -eq "arm64") {
    if ($env:PROCESSOR_ARCHITECTURE -notmatch "ARM") {
        Write-Warning "ARM64 exe лучше собирать на Windows ARM64. Пробуем PyInstaller..."
    }
    $PyArgs += @("--target-architecture", "arm64")
}

python -m PyInstaller @PyArgs

$Exe = Join-Path $OutDir "$AppName.exe"
if (-not (Test-Path $Exe)) {
    throw "Сборка не удалась: $Exe не найден"
}

$Zip = Join-Path $Root "build\dist\ireplicator-gamepad-tester_${Version}_win-${Arch}.zip"
if (Test-Path $Zip) { Remove-Item $Zip }
Compress-Archive -Path $Exe -DestinationPath $Zip -Force

Write-Host "OK: $Exe"
Write-Host "ZIP: $Zip"
