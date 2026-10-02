# Web backend (127.0.0.1:8724) + Cloudflare tunnel connector (api-crypto.nguyenchitrai.id.vn).
#
#   .\run_backend.ps1              run in THIS terminal: logs stream here (VS Code terminal works), Ctrl+C stops the backend
#                                  and the tunnel. The scheduler inside the backend runs the pipeline after every 4h close
#                                  (+8 min) and refreshes candles every 15 min - watch the "job ..." / "scheduler" lines.
#   .\run_backend.ps1 -AccessLog   same, also print every HTTP request
#   .\run_backend.ps1 -Background  run hidden (auto-restart on crash), logs in artifacts\web\backend.log
#   .\run_backend.ps1 -Status      show what is running and check local + public /health
#   .\run_backend.ps1 -Stop        stop the backend (foreground or background) and the tunnel connector
# The tunnel token is read from CLOUDFLARE_TUNNEL_TOKEN in the local .env (gitignored; never commit it).
param([switch]$Background, [switch]$Stop, [switch]$Status, [switch]$AccessLog, [switch]$Ensure)

$root = $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
$logDir = Join-Path $root "artifacts\web"
New-Item -ItemType Directory -Force $logDir | Out-Null
$cfLog = Join-Path $logDir "cloudflared_api.log"
$publicUrl = "https://api-crypto.nguyenchitrai.id.vn/health"

function Get-EnvValue([string]$name, [string]$default = "") {
    $f = Join-Path $root ".env"
    if (Test-Path $f) {
        $m = Select-String -Path $f -Pattern "^\s*$name\s*=\s*(.*)$" | Select-Object -First 1
        if ($m) { return $m.Matches[0].Groups[1].Value.Trim().Trim('"').Trim("'") }
    }
    return $default
}
$port = [int](Get-EnvValue "WEB_PORT" "8724")

function Get-Procs {
    $all = Get-CimInstance Win32_Process
    [pscustomobject]@{
        Supervisors = @($all | Where-Object { $_.Name -eq "powershell.exe" -and $_.CommandLine -match "start_backend\.ps1" })
        Servers     = @($all | Where-Object { $_.Name -eq "python.exe" -and $_.CommandLine -match ("backend" + "\.server:app") })
        Tunnels     = @($all | Where-Object { $_.Name -eq "cloudflared.exe" -and $_.CommandLine -match "cloudflared_api\.log" })
    }
}
function Stop-All {
    $p = Get-Procs
    @($p.Supervisors + $p.Servers + $p.Tunnels) | Where-Object { $_ } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}
function Test-Url([string]$url, [int]$timeout = 5) {
    try { return (Invoke-WebRequest -UseBasicParsing $url -TimeoutSec $timeout).StatusCode -eq 200 } catch { return $false }
}
function Start-Tunnel {
    $token = Get-EnvValue "CLOUDFLARE_TUNNEL_TOKEN"
    $exe = (Get-Command cloudflared.exe -ErrorAction SilentlyContinue).Source
    if (-not $exe) { $exe = "C:\Program Files (x86)\cloudflared\cloudflared.exe" }
    if (-not $token) { Write-Host "Tunnel: CLOUDFLARE_TUNNEL_TOKEN is not set in .env - skipped (local only)." -ForegroundColor Yellow; return $null }
    if (-not (Test-Path $exe)) { Write-Host "Tunnel: cloudflared.exe not found - skipped." -ForegroundColor Yellow; return $null }
    Write-Host "Tunnel: connecting api-crypto.nguyenchitrai.id.vn -> 127.0.0.1:$port (log: artifacts\web\cloudflared_api.log)"
    return Start-Process $exe -WindowStyle Hidden -PassThru -ArgumentList "tunnel", "--no-autoupdate", "--logfile", $cfLog, "run", "--token", $token
}

if ($Stop) { Stop-All; Write-Host "Stopped backend and tunnel connector."; return }

if ($Status) {
    $p = Get-Procs
    Write-Host ("Backend processes: {0} (background supervisor: {1}) | tunnel connectors: {2}" -f $p.Servers.Count, $p.Supervisors.Count, $p.Tunnels.Count)
    try { $h = Invoke-RestMethod "http://127.0.0.1:$port/health" -TimeoutSec 5; Write-Host ("Local health: {0}. Đăng nhập dashboard để xem chi tiết scheduler." -f $h.status) }
    catch { Write-Host "Local  http://127.0.0.1:$port/health : NOT RESPONDING" -ForegroundColor Red }
    Write-Host ("Public {0} : {1}" -f $publicUrl, $(if (Test-Url $publicUrl 15) { "OK" } else { "NOT REACHABLE" }))
    return
}

if ($Ensure) {
    $ensureLog = Join-Path $logDir "watchdog.log"
    $healthy = $false
    try {
        $h = Invoke-RestMethod "http://127.0.0.1:$port/health" -TimeoutSec 10
        $healthy = $h.status -eq "ok" # BE returns 503 if the scheduler heartbeat is stale (>40 minutes).
    } catch { $healthy = $false }
    if (-not $healthy) {
        Add-Content $ensureLog ("{0}  backend down or scheduler stale -> restarting" -f (Get-Date -Format s))
        $Background = $true
    } elseif ((Get-Procs).Tunnels.Count -eq 0) {
        Add-Content $ensureLog ("{0}  tunnel connector missing -> starting it" -f (Get-Date -Format s))
        Start-Tunnel | Out-Null
        return
    } else { return }
}

if ($Background) {
    Stop-All
    Start-Process powershell.exe -WindowStyle Hidden -WorkingDirectory $root `
        -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $root "deploy\start_backend.ps1")
    Start-Tunnel | Out-Null
    $ok = $false; for ($i = 0; $i -lt 20 -and -not $ok; $i++) { Start-Sleep -Seconds 2; $ok = Test-Url "http://127.0.0.1:$port/health" }
    Write-Host ("Backend (background): {0}. Logs: artifacts\web\backend.log. Stop with .\run_backend.ps1 -Stop" -f $(if ($ok) { "OK" } else { "NOT RESPONDING" }))
    return
}

# ---------------- foreground (default)
Stop-All   # one instance only: replaces a background or older run
Set-Location $root
$env:PYTHONUTF8 = "1"
$tunnel = Start-Tunnel
Write-Host "Backend: http://127.0.0.1:$port  (Ctrl+C to stop backend + tunnel)" -ForegroundColor Green
$uv = @("-m", "uvicorn", "backend.server:app", "--host", "127.0.0.1", "--port", "$port", "--timeout-keep-alive", "30")
if (-not $AccessLog) { $uv += "--no-access-log" }
try {
    & $py @uv
}
finally {
    if ($tunnel) { Stop-Process -Id $tunnel.Id -Force -ErrorAction SilentlyContinue }
    Write-Host "Backend and tunnel stopped." -ForegroundColor Yellow
}
