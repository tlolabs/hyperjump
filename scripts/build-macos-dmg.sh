#!/usr/bin/env bash

set -euo pipefail

APP_NAME="Hyper Jump"
DIST_DIR="${DIST_DIR:-dist}"
APP_BUNDLE_PATH="${APP_BUNDLE_PATH:-${DIST_DIR}/${APP_NAME}.app}"
STAGING_DIR="${STAGING_DIR:-${DIST_DIR}/dmg-root}"
DMG_NAME="${DMG_NAME:-${APP_NAME}-macOS-$(uname -m).dmg}"
DMG_PATH="${DMG_PATH:-${DIST_DIR}/${DMG_NAME}}"
VOLUME_NAME="${VOLUME_NAME:-${APP_NAME}}"

if [[ ! -d "${APP_BUNDLE_PATH}" ]]; then
  echo "App bundle not found at ${APP_BUNDLE_PATH}" >&2
  exit 1
fi

rm -rf "${STAGING_DIR}"
mkdir -p "${STAGING_DIR}"
cp -R "${APP_BUNDLE_PATH}" "${STAGING_DIR}/"
ln -s /Applications "${STAGING_DIR}/Applications"
rm -f "${DMG_PATH}"

hdiutil create \
  -volname "${VOLUME_NAME}" \
  -srcfolder "${STAGING_DIR}" \
  -ov \
  -format UDZO \
  "${DMG_PATH}"

echo "Created ${DMG_PATH}"
