# Mở port firewall để máy khác cùng mạng truy cập Docker
# Chạy: Right-click -> Run with PowerShell (as Administrator)
# Hoặc: PowerShell (Admin) -> .\scripts\open-firewall-ports.ps1

$rules = @(
    @{ Name = "Docker Frontend Dev"; Port = 5173 }
    @{ Name = "Docker API"; Port = 8000 }
    @{ Name = "Docker Frontend Prod"; Port = 5174 }
)

foreach ($r in $rules) {
    $existing = netsh advfirewall firewall show rule name=$($r.Name) 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Rule '$($r.Name)' da ton tai" -ForegroundColor Yellow
    } else {
        netsh advfirewall firewall add rule name=$($r.Name) dir=in action=allow protocol=TCP localport=$($r.Port)
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[+] Da them rule: $($r.Name) (port $($r.Port))" -ForegroundColor Green
        } else {
            Write-Host "[-] Loi khi them $($r.Name)" -ForegroundColor Red
        }
    }
}

Write-Host ""
Write-Host "Xong! Lay IP may cua ban:" -ForegroundColor Cyan
ipconfig | Select-String -Pattern "IPv4"
Write-Host ""
Write-Host "May khac truy cap: http://<IP>:5173 (dev) hoac http://<IP>:5174 (prod)" -ForegroundColor Cyan
