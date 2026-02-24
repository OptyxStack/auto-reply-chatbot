# Setup venv và cài package cho script đăng nhập WHMCS (chạy trên máy local)
# Chạy từ thư mục project: .\scripts\setup_login.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "Tạo venv..." -ForegroundColor Cyan
python -m venv .venv-login

$pip = Join-Path $ProjectRoot ".venv-login\Scripts\pip.exe"
$python = Join-Path $ProjectRoot ".venv-login\Scripts\python.exe"

Write-Host "Cài package..." -ForegroundColor Cyan
& $pip install -r scripts/requirements-login.txt
& $python -m playwright install chromium

Write-Host ""
Write-Host "Xong. Chạy script:" -ForegroundColor Green
Write-Host "  .\.venv-login\Scripts\Activate.ps1" -ForegroundColor Yellow
Write-Host "  python scripts/whmcs_login_browser.py --api-url http://localhost:8000/v1 --api-key dev-key" -ForegroundColor Yellow
