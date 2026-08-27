#!/usr/bin/env bash
# Локальная сборка Linux .deb (amd64 + arm64 metadata)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

chmod +x build/build-deb.sh build/linux/ireplicator-gamepad-tester.wrapper

echo "=== iReplicator Gamepad Tester v0.2.0 ==="
echo "=== Linux amd64 .deb ==="
build/build-deb.sh amd64

echo "=== Linux arm64 .deb (Python, all architectures) ==="
build/build-deb.sh arm64

echo
echo "Готово:"
ls -lh build/dist/*.deb 2>/dev/null || true
echo
echo "Windows x64 / ARM64:"
echo "  На Windows: powershell -ExecutionPolicy Bypass -File build\\windows\\build.ps1 -Arch x64"
echo "  На Windows ARM: powershell -ExecutionPolicy Bypass -File build\\windows\\build.ps1 -Arch arm64"
echo
echo "macOS arm64 / x64:"
echo "  На macOS: ./build/macos/build.sh arm64"
echo "  На macOS Intel: ./build/macos/build.sh x64"
echo "  Или push в GitHub — workflow .github/workflows/build.yml соберёт всё в CI."
