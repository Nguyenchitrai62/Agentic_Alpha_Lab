# Start the web backend (127.0.0.1:8724) and the Cloudflare tunnel connector (api-crypto.nguyenchitrai.id.vn).
#   .\run_backend.ps1          start whatever is not running yet, then check local + public health
#   .\run_backend.ps1 -Stop    stop both
#   .\run_backend.ps1 -Status  show status only
# The tunnel token is read from CLOUDFLARE_TUNNEL_TOKEN in the local .env (gitignored; never commit it).
param([switch]$Stop, [switch]$Status)

$root = $PSScriptRoot
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
$procs = Get-CimInstance Win32_Process
$supervisors = $procs | Where-Object { $_.Name -eq "powershell.exe" -and $_.CommandLine -match "start_backend\.ps1" }
$servers = $procs | Where-Object { $_.Name -eq "python.exe" -and $_.CommandLine -match ("backend" + "\.server:app") }
$tunnels = $procs | Where-Object { $_.Name -eq "cloudflared.exe" -and $_.CommandLine -match "cloudflared_api\.log" }

function Test-Local {
    try { return (Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$port/health" -TimeoutSec 5).StatusCode -eq 200 } catch { return $false }
}
function Test-Public {
    try { return (Invoke-WebRequest -UseBasicParsing $publicUrl -TimeoutSec 15).StatusCode -eq 200 } catch { return $false }
}

if ($Stop) {
    @(@($supervisors) + @($servers) + @($tunnels)) | Where-Object { $_ } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Write-Host "Stopped backend and tunnel connector."
    return
}

if (-not $Status) {
    if (-not $supervisors) {
        if ($servers) { $servers | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } }
        Start-Process powershell.exe -WindowStyle Hidden -WorkingDirectory $root `
            -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $root "deploy\start_backend.ps1")
        Write-Host "Backend: starting on 127.0.0.1:$port ..."
    } else { Write-Host "Backend: already running." }

    if (-not $tunnels) {
        $token = Get-EnvValue "CLOUDFLARE_TUNNEL_TOKEN"
        $exe = (Get-Command cloudflared.exe -ErrorAction SilentlyContinue).Source
        if (-not $exe) { $exe = "C:\Program Files (x86)\cloudflared\cloudflared.exe" }
        if (-not $token) {
            Write-Host "Tunnel: CLOUDFLARE_TUNNEL_TOKEN is not set in .env - skipped." -ForegroundColor Yellow
        } elseif (-not (Test-Path $exe)) {
            Write-Host "Tunnel: cloudflared.exe not found - install it from Cloudflare first." -ForegroundColor Yellow
        } else {
            Start-Process $exe -WindowStyle Hidden -ArgumentList "tunnel", "--no-autoupdate", "--logfile", $cfLog, "run", "--token", $token
            Write-Host "Tunnel: connector starting ..."
        }
    } else { Write-Host "Tunnel: already running." }
}

$ok = $false
for ($i = 0; $i -lt 20 -and -not $ok; $i++) { $ok = Test-Local; if (-not $ok) { Start-Sleep -Seconds 2 } }
Write-Host ("Local  http://127.0.0.1:{0}/health : {1}" -f $port, $(if ($ok) { "OK" } else { "NOT RESPONDING (see artifacts\web\backend.log)" }))
$pub = $false
for ($i = 0; $i -lt 6 -and -not $pub; $i++) { $pub = Test-Public; if (-not $pub) { Start-Sleep -Seconds 3 } }
Write-Host ("Public {0} : {1}" -f $publicUrl, $(if ($pub) { "OK" } else { "NOT REACHABLE (see artifacts\web\cloudflared_api.log)" }))
