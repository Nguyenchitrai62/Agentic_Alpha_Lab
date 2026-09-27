# Serve the frontend locally at http://localhost:5500 and open it in the browser.
# On this machine the backend signs you in as the local admin (no Google login); start it first with run_backend.ps1.
#   .\run_frontend.ps1           start (if not running) and open the browser
#   .\run_frontend.ps1 -NoOpen   start only
#   .\run_frontend.ps1 -Stop     stop the local frontend server
param([switch]$Stop, [switch]$NoOpen, [int]$Port = 5500)

$root = $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
$url = "http://localhost:$Port"
$servers = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq "python.exe" -and $_.CommandLine -match "http\.server $Port" -and $_.CommandLine -match "frontend" }

if ($Stop) {
    $servers | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Write-Host "Stopped the local frontend server."
    return
}

if (-not $servers) {
    Start-Process $py -WindowStyle Hidden -WorkingDirectory $root `
        -ArgumentList "-m", "http.server", "$Port", "--bind", "127.0.0.1", "--directory", (Join-Path $root "frontend")
    Write-Host "Frontend: starting on $url ..."
} else { Write-Host "Frontend: already running on $url." }

$ok = $false
for ($i = 0; $i -lt 15 -and -not $ok; $i++) {
    try { $ok = (Invoke-WebRequest -UseBasicParsing "$url/" -TimeoutSec 3).StatusCode -eq 200 } catch { Start-Sleep -Seconds 1 }
}
Write-Host ("Frontend {0} : {1}" -f $url, $(if ($ok) { "OK" } else { "NOT RESPONDING" }))
try { $be = (Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8724/health" -TimeoutSec 5).StatusCode -eq 200 } catch { $be = $false }
if (-not $be) { Write-Host "Backend 127.0.0.1:8724 is not running - start it with run_backend.bat" -ForegroundColor Yellow }
if ($ok -and -not $NoOpen) { Start-Process $url }
