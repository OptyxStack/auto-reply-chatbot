# Open firewall ports for other machines on same network to access Docker
# Run: Right-click -> Run with PowerShell (as Administrator)
# Or: PowerShell (Admin) -> .\scripts\open-firewall-ports.ps1

$rules = @(
    @{ Name = "Docker Frontend Dev"; Port = 5173 }
    @{ Name = "Docker API"; Port = 8000 }
    @{ Name = "Docker Frontend Prod"; Port = 5174 }
)

foreach ($r in $rules) {
    $existing = netsh advfirewall firewall show rule name=$($r.Name) 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Rule '$($r.Name)' already exists" -ForegroundColor Yellow
    } else {
        netsh advfirewall firewall add rule name=$($r.Name) dir=in action=allow protocol=TCP localport=$($r.Port)
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[+] Added rule: $($r.Name) (port $($r.Port))" -ForegroundColor Green
        } else {
            Write-Host "[-] Error adding $($r.Name)" -ForegroundColor Red
        }
    }
}

Write-Host ""
Write-Host "Done! Get your machine IP:" -ForegroundColor Cyan
ipconfig | Select-String -Pattern "IPv4"
Write-Host ""
Write-Host "Other machines access: http://<IP>:5173 (dev) or http://<IP>:5174 (prod)" -ForegroundColor Cyan
