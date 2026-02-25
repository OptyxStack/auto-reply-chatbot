# Setup venv and install packages for WHMCS login script (run on local machine)
# Run from project folder: .\scripts\setup_login.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "Creating venv..." -ForegroundColor Cyan
python -m venv .venv-login

$pip = Join-Path $ProjectRoot ".venv-login\Scripts\pip.exe"
$python = Join-Path $ProjectRoot ".venv-login\Scripts\python.exe"

Write-Host "Installing packages..." -ForegroundColor Cyan
& $pip install -r scripts/requirements-login.txt
& $python -m playwright install chromium

Write-Host ""
Write-Host "Done. Run script:" -ForegroundColor Green
Write-Host "  .\.venv-login\Scripts\Activate.ps1" -ForegroundColor Yellow
Write-Host "  python scripts/whmcs_login_browser.py --api-url http://localhost:8000/v1 --api-key dev-key" -ForegroundColor Yellow
