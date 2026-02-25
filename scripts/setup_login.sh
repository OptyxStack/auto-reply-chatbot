#!/bin/bash
# Setup venv and install packages for WHMCS login script (run on local machine)
# Run: bash scripts/setup_login.sh

set -e
cd "$(dirname "$0")/.."

echo "Creating venv..."
python3 -m venv .venv-login

echo "Activating venv and installing packages..."
source .venv-login/bin/activate
pip install -r scripts/requirements-login.txt
python -m playwright install chromium

echo ""
echo "Done. Run script:"
echo "  source .venv-login/bin/activate"
echo "  python scripts/whmcs_login_browser.py --api-url http://localhost:8000/v1 --api-key dev-key"
