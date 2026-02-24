#!/bin/sh
set -e
# Ensure Chromium revision always matches current Playwright package.
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/ms-playwright}"
mkdir -p "$PLAYWRIGHT_BROWSERS_PATH"
echo "Ensuring Playwright Chromium is installed in $PLAYWRIGHT_BROWSERS_PATH ..."
python -m playwright install chromium
exec "$@"
