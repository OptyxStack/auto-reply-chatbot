#!/bin/sh
set -e
# Ensure Chromium revision always matches current Playwright package.
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/ms-playwright}"
mkdir -p "$PLAYWRIGHT_BROWSERS_PATH"

NORMALIZER_MODE="generic_default"
if [ -n "${NORMALIZER_DOMAIN_TERMS:-}" ] || [ "${NORMALIZER_QUERY_EXPANSION:-false}" = "true" ] || [ "${NORMALIZER_SLOTS_ENABLED:-false}" = "true" ]; then
  NORMALIZER_MODE="legacy_compat"
fi
echo "Hybrid normalizer mode: $NORMALIZER_MODE"

echo "Ensuring Playwright Chromium is installed in $PLAYWRIGHT_BROWSERS_PATH ..."
python -m playwright install chromium
exec "$@"
