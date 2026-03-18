#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-0.0.0-dev}"
PYTHON_EXE="${PYTHON_EXE:-python3}"
DIST_DIR="${DIST_DIR:-dist}"
APP_NAME="${APP_NAME:-HOH Game}"
BUNDLE_ID="${BUNDLE_ID:-com.hkie.bme.hoh-game}"
MACOS_SIGNING_IDENTITY="${MACOS_SIGNING_IDENTITY:-}"
APPLE_ID="${APPLE_ID:-}"
APPLE_TEAM_ID="${APPLE_TEAM_ID:-}"
APPLE_APP_PASSWORD="${APPLE_APP_PASSWORD:-}"

echo "Installing release build dependencies..."
"${PYTHON_EXE}" -m pip install --upgrade pip
"${PYTHON_EXE}" -m pip install pyinstaller build

echo "Installing application runtime dependencies..."
"${PYTHON_EXE}" -m pip install .

echo "Building wheel + sdist..."
"${PYTHON_EXE}" -m build

echo "Building macOS app bundle with PyInstaller..."
"${PYTHON_EXE}" -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name "${APP_NAME}" \
  --osx-bundle-identifier "${BUNDLE_ID}" \
  --collect-submodules bleak.backends \
  --add-data "assets:assets" \
  --add-data "config:config" \
  app/__main__.py

APP_PATH="${DIST_DIR}/${APP_NAME}.app"
if [[ ! -d "${APP_PATH}" ]]; then
  echo "Expected app bundle missing at '${APP_PATH}'." >&2
  exit 1
fi

if [[ -n "${MACOS_SIGNING_IDENTITY}" ]]; then
  echo "Code-signing app bundle..."
  codesign --force --deep --options runtime --timestamp --sign "${MACOS_SIGNING_IDENTITY}" "${APP_PATH}"
  codesign --verify --deep --strict --verbose=2 "${APP_PATH}"
else
  echo "MACOS_SIGNING_IDENTITY not set; building unsigned app."
fi

ZIP_PATH="${DIST_DIR}/hoh-game-${VERSION}-macos-app.zip"
DMG_PATH="${DIST_DIR}/hoh-game-${VERSION}-macos.dmg"

echo "Creating zipped app artifact..."
rm -f "${ZIP_PATH}"
ditto -c -k --sequesterRsrc --keepParent "${APP_PATH}" "${ZIP_PATH}"
echo "App zip artifact: ${ZIP_PATH}"

echo "Creating DMG artifact..."
rm -f "${DMG_PATH}"
hdiutil create -volname "${APP_NAME}" -srcfolder "${APP_PATH}" -ov -format UDZO "${DMG_PATH}"
echo "DMG artifact: ${DMG_PATH}"

if [[ -n "${MACOS_SIGNING_IDENTITY}" && -n "${APPLE_ID}" && -n "${APPLE_TEAM_ID}" && -n "${APPLE_APP_PASSWORD}" ]]; then
  echo "Submitting DMG for notarization..."
  xcrun notarytool submit "${DMG_PATH}" \
    --apple-id "${APPLE_ID}" \
    --team-id "${APPLE_TEAM_ID}" \
    --password "${APPLE_APP_PASSWORD}" \
    --wait

  echo "Stapling notarization ticket..."
  xcrun stapler staple "${APP_PATH}"
  xcrun stapler staple "${DMG_PATH}"
else
  echo "Notarization credentials not fully set; skipping notarization."
fi
