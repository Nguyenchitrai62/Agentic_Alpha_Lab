# Local frontend at http://localhost:5500 (no Google login on this machine: the backend treats local requests as admin).
#   .\run_frontend.ps1              serve in THIS terminal (request log visible), open the browser; Ctrl+C stops it
#   .\run_frontend.ps1 -Background  serve hidden
#   .\run_frontend.ps1 -Stop        stop a background server
#   .\run_frontend.ps1 -NoOpen      do not open the browser
param([switch]$Background, [switch]$Stop, [switch]$NoOpen, [int]$Port = 5500)

$root = $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
$url = "http://localhost:$Port"
$front = Join-Path $root "frontend"
function Get-Servers { @(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq "python.exe" -and $_.CommandLine -match "http\.server $Port" -and $_.CommandLine -match "frontend" }) }

if ($Stop) { Get-Servers | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; Write-Host "Stopped the local frontend server."; return }

try { $be = (Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8724/health" -TimeoutSec 3).StatusCode -eq 200 } catch { $be = $false }
if (-not $be) { Write-Host "Backend 127.0.0.1:8724 is not running - start it with .\run_backend.ps1 in another terminal." -ForegroundColor Yellow }
Get-Servers | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

if ($Background) {
    Start-Process $py -WindowStyle Hidden -WorkingDirectory $root -ArgumentList "-m", "http.server", "$Port", "--bind", "127.0.0.1", "--directory", $front
    Start-Sleep -Seconds 1
    if (-not $NoOpen) { Start-Process $url }
    Write-Host "Frontend (background): $url  - stop with .\run_frontend.ps1 -Stop"
    return
}

Write-Host "Frontend: $url  (Ctrl+C to stop)" -ForegroundColor Green
if (-not $NoOpen) { Start-Job -ScriptBlock { param($u) Start-Sleep -Seconds 1; Start-Process $u } -ArgumentList $url | Out-Null }
& $py -m http.server $Port --bind 127.0.0.1 --directory $front
