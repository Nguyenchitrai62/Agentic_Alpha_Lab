# Start the web backend on this machine (127.0.0.1:8724) and restart it if it stops.
# The Cloudflare tunnel (cloudflared Windows service) publishes it as https://api-crypto.nguyenchitrai.id.vn.
#   powershell -ExecutionPolicy Bypass -File deploy\start_backend.ps1
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = Join-Path $root ".venv\Scripts\python.exe"
$logDir = Join-Path $root "artifacts\web"
New-Item -ItemType Directory -Force $logDir | Out-Null
$port = 8724
$envFile = Join-Path $root ".env"
if (Test-Path $envFile) {
    $line = Select-String -Path $envFile -Pattern '^\s*WEB_PORT\s*=\s*(\d+)' | Select-Object -First 1
    if ($line) { $port = [int]$line.Matches[0].Groups[1].Value }
}
while ($true) {
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path (Join-Path $logDir "backend_supervisor.log") -Value "$stamp start backend on 127.0.0.1:$port"
    # cmd redirection keeps the log as plain UTF-8 text (PowerShell 5 *>> would write UTF-16 error records)
    $log = Join-Path $logDir "backend.log"
    cmd /c "`"$py`" -m uvicorn backend.server:app --host 127.0.0.1 --port $port --no-access-log --timeout-keep-alive 30 >> `"$log`" 2>&1"
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path (Join-Path $logDir "backend_supervisor.log") -Value "$stamp backend exited ($LASTEXITCODE); restarting in 10s"
    Start-Sleep -Seconds 10
}
