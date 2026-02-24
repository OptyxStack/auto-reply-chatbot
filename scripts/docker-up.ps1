# Run full stack with Docker Compose
# Usage: .\scripts\docker-up.ps1
# Or for dev (with hot reload): .\scripts\docker-up.ps1 -Dev

param(
    [switch]$Dev
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

if ($Dev) {
    Write-Host "Starting dev stack (frontend + api + worker + infra)..." -ForegroundColor Cyan
    docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres redis opensearch qdrant minio
    Start-Sleep -Seconds 5
    docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
} else {
    Write-Host "Starting full stack..." -ForegroundColor Cyan
    docker compose up -d
}

Write-Host ""
Write-Host "Services:" -ForegroundColor Green
Write-Host "  API:      http://localhost:8000"
Write-Host "  Frontend: http://localhost:5174 (prod) or http://localhost:5173 (dev)"
Write-Host "  Docs:     http://localhost:8000/docs"
Write-Host ""
