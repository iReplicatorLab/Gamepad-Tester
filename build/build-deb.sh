#!/usr/bin/env bash
# Сборка .deb для Linux (amd64 / arm64 — all для Python-пакета)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="0.2.0"
ARCH="${1:-amd64}"
PKG_NAME="ireplicator-gamepad-tester"
STAGING="$ROOT/build/staging/${PKG_NAME}_${VERSION}_${ARCH}"
DIST="$ROOT/build/dist"
APP_DIR="$STAGING/usr/share/ireplicator-gamepad-tester"

rm -rf "$STAGING"
mkdir -p "$STAGING/DEBIAN"
mkdir -p "$STAGING/usr/bin"
mkdir -p "$APP_DIR"
mkdir -p "$STAGING/usr/share/applications"
mkdir -p "$STAGING/usr/share/icons/hicolor/scalable/apps"

install -m 644 "$ROOT/gamepad_tester.py" "$APP_DIR/"
install -m 644 "$ROOT/pad_common.py" "$APP_DIR/"
install -m 755 "$ROOT/setup-input-access.sh" "$APP_DIR/"
for pkg in core backend ui locale assets; do
  cp -a "$ROOT/$pkg" "$APP_DIR/"
done
find "$APP_DIR" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

install -m 755 "$ROOT/build/linux/ireplicator-gamepad-tester.wrapper" "$STAGING/usr/bin/ireplicator-gamepad-tester"
install -m 644 "$ROOT/build/linux/com.ireplicator.gamepad-tester.desktop" "$STAGING/usr/share/applications/"
install -m 644 "$ROOT/build/icons/com.ireplicator.gamepad-tester.svg" "$STAGING/usr/share/icons/hicolor/scalable/apps/"

INSTALLED_SIZE="$(du -sk "$STAGING/usr" | cut -f1)"

cat > "$STAGING/DEBIAN/control" <<EOF
Package: ${PKG_NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Maintainer: iReplicator <noreply@local>
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1, python3-evdev, python3-pygame
Description: iReplicator Gamepad Tester
 Test and diagnose Xbox 360 / Series controllers: monitoring, sticks, triggers, export.
EOF

cat > "$STAGING/DEBIAN/postinst" <<'EOF'
#!/bin/bash
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q /usr/share/icons/hicolor || true
fi
EOF
chmod 755 "$STAGING/DEBIAN/postinst"

echo "Installed-Size: ${INSTALLED_SIZE}" >> "$STAGING/DEBIAN/control"

mkdir -p "$DIST"
OUT="$DIST/${PKG_NAME}_${VERSION}_${ARCH}.deb"
fakeroot dpkg-deb --build --root-owner-group "$STAGING" "$OUT"
echo "Built: $OUT"
ls -lh "$OUT"
