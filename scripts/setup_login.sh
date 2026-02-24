#!/bin/bash
# Setup venv và cài package cho script đăng nhập WHMCS (chạy trên máy local)
# Chạy: bash scripts/setup_login.sh

set -e
cd "$(dirname "$0")/.."

echo "Tạo venv..."
python3 -m venv .venv-login

echo "Kích hoạt venv và cài package..."
source .venv-login/bin/activate
pip install -r scripts/requirements-login.txt
python -m playwright install chromium

echo ""
echo "Xong. Chạy script:"
echo "  source .venv-login/bin/activate"
echo "  python scripts/whmcs_login_browser.py --api-url http://localhost:8000/v1 --api-key dev-key"
