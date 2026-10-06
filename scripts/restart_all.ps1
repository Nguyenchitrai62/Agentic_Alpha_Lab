# restart_all.ps1 - idempotent post-reboot restore (same logic as scripts/restart_all.sh).
#
# Order: (1) backend uvicorn on 127.0.0.1:8724 (local only, NEVER the public
# tunnel/cloudflared), wait for /health + fresh plan (<1h15m); (2) advisor
# shadow loop.sh exactly once (skip if running); (3) the six paper runners
# (paper, d17bf, d13bf, d17bfg2, g2k20, d17bfg2c),
# each only if its runner.lock is free (live process check); state.json is
# backed up first and validated as JSON; (4) the hourly carry ledger loop once;
# (5) bot_health for every runner + daily_status summary.
#
# Idempotent: running twice starts nothing new. -DryRun prints the plan only
# (starts nothing, runs no health checks). -Only bots|backend|carry limits scope
# (-Only backend includes the advisor loop.sh plan feed).
# NEVER sets BOT_ALLOW_LIVE, NEVER starts testnet/live (paper only).
# READ-ONLY process checks (Get-CimInstance); this script never stops a process.
#
# Usage:
#   .\scripts\restart_all.ps1 [-DryRun] [-Only bots|backend|carry]
param([switch]$DryRun, [string]$Only = "all")

$ErrorActionPreference = "Continue"
$root = $PSScriptRoot | Split-Path -Parent
$py = Join-Path $root ".venv\Scripts\python.exe"
$backendUrl = "http://127.0.0.1:8724/health"
$planPath = Join-Path $root "artifacts\research\advisor_shadow\trade_plan_v376.json"
if (@("all", "bots", "backend", "carry") -notcontains $Only) { Write-Error "bad -Only: $Only (bots|backend|carry)"; exit 2 }

# --- canonical commands (must match scripts/restart_all.sh and the live processes) ---
$backendArgs = @("-m", "uvicorn", "backend.server:app", "--host", "127.0.0.1", "--port", "8724", "--timeout-keep-alive", "30", "--no-access-log")
$backendCmdLine = ".venv/Scripts/python.exe -m uvicorn backend.server:app --host 127.0.0.1 --port 8724 --timeout-keep-alive 30 --no-access-log"
$loopCmdLine = "bash artifacts/research/advisor_shadow/loop.sh"
$carryCmdLine = ".venv/Scripts/python.exe scripts/carry_paper.py --once --equity 5000 --f 0.5 --tag carry"
# tag | state dir | bot args (paper = R2-4P, no tag; --interval 25 as observed 2026-10-06)
$bots = @(
  @{ tag = "paper"; dir = "artifacts/bot/paper"; args = @("-m", "bot.run", "--mode", "paper", "--equity", "5000", "--interval", "25") },
  @{ tag = "d17bf"; dir = "artifacts/bot/paper_d17bf"; args = @("-m", "bot.run", "--mode", "paper", "--equity", "5000", "--corr-size", "--dip-mult", "1.7", "--bear-book", "--interval", "25", "--tag", "d17bf") },
  @{ tag = "d13bf"; dir = "artifacts/bot/paper_d13bf"; args = @("-m", "bot.run", "--mode", "paper", "--equity", "5000", "--corr-size", "--dip-mult", "1.3", "--bear-book", "--interval", "25", "--tag", "d13bf") },
  @{ tag = "d17bfg2"; dir = "artifacts/bot/paper_d17bfg2"; args = @("-m", "bot.run", "--mode", "paper", "--equity", "5000", "--corr-size", "--dip-mult", "1.7", "--dip-gross-cap", "2.0", "--bear-book", "--adopt-fresh", "--interval", "25", "--tag", "d17bfg2") },
  @{ tag = "g2k20"; dir = "artifacts/bot/paper_g2k20"; args = @("-m", "bot.run", "--mode", "paper", "--equity", "5000", "--corr-size", "--dip-mult", "2.0", "--dip-gross-cap", "2.0", "--bear-book", "--adopt-fresh", "--interval", "25", "--tag", "g2k20") }
  @{ tag = "d17bfg2c"; dir = "artifacts/bot/paper_d17bfg2c"; args = @("-m", "bot.run", "--mode", "paper", "--equity", "5000", "--corr-size", "--dip-mult", "1.7", "--dip-gross-cap", "2.0", "--bear-book", "--adopt-fresh", "--carry-f", "0.25", "--interval", "25", "--tag", "d17bfg2c") }
  @{ tag = "g2k20c"; dir = "artifacts/bot/paper_g2k20c"; args = @("-m", "bot.run", "--mode", "paper", "--equity", "5000", "--corr-size", "--dip-mult", "2.0", "--dip-gross-cap", "2.0", "--bear-book", "--adopt-fresh", "--carry-f", "0.25", "--interval", "25", "--tag", "g2k20c") }
)

function Log([string]$m) { Write-Host "[restart_all] $m" }
function Plan([string]$m) { Write-Host "PLAN: $m" }

function Find-Procs([string]$pattern) {
  # READ-ONLY: never stops anything
  @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match $pattern })
}

function Test-BackendHealthy {
  try { return (Invoke-WebRequest -UseBasicParsing $backendUrl -TimeoutSec 5).StatusCode -eq 200 } catch { return $false }
}

function Get-PlanAgeH {
  try {
    $p = Get-Content $planPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $t = [datetime]::Parse($p.generated_at, $null, [System.Globalization.DateTimeStyles]::RoundtripKind)
    return ((Get-Date).ToUniversalTime() - $t.ToUniversalTime()).TotalHours
  } catch { return $null }
}

function Backup-ValidateState([string]$dirRel) {
  $d = Join-Path $root $dirRel
  $st = Join-Path $d "state.json"
  if (-not (Test-Path $st)) { Log "$dirRel : no state.json yet (fresh start)"; return $true }
  $ts = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
  Copy-Item $st (Join-Path $d "state.json.bak_$ts") -Force
  Log "$dirRel : state.json backed up -> state.json.bak_$ts"
  try { Get-Content $st -Raw -Encoding UTF8 | ConvertFrom-Json | Out-Null; Write-Host "state.json valid JSON"; return $true }
  catch { Log "$dirRel : state.json INVALID JSON - NOT starting"; return $false }
}

function Start-Detached([string]$exe, [string[]]$argv, [string]$logRel) {
  $logAbs = Join-Path $root $logRel
  New-Item -ItemType Directory -Force (Split-Path $logAbs) | Out-Null
  # append stdout+stderr to the log, detached (no new window, no waiting)
  $cmd = '"{0}" {1} >> "{2}" 2>&1' -f $exe, ($argv -join ' '), $logAbs
  # Start-Process from the OWNER's console: independent hidden process. (2026-10-06: WMI-created bots died ~30 min
  # later with the WMI host; agent tool shells kill their children - agents start runners with nohup instead.)
  Start-Process cmd.exe -WindowStyle Hidden -ArgumentList '/c', $cmd | Out-Null
}

$doBackend = ($Only -eq "all" -or $Only -eq "backend")
$doBots = ($Only -eq "all" -or $Only -eq "bots")
$doCarry = ($Only -eq "all" -or $Only -eq "carry")

# ---------- (1) backend + (2) advisor loop ----------
if ($doBackend) {
  if (Test-BackendHealthy) {
    $age = Get-PlanAgeH
    Log "backend healthy (/health OK, plan age ${age}h) -> skip start (local only, no tunnel)"
  } elseif ($DryRun) {
    Plan "start backend: $backendCmdLine (local only, never the public tunnel)"
  } else {
    Log "backend down -> starting local uvicorn (NEVER the public tunnel; never sets BOT_ALLOW_LIVE)"
    Start-Detached $py $backendArgs "artifacts/web/backend.log"
    $ok = $false
    for ($i = 0; $i -lt 60 -and -not $ok; $i++) { Start-Sleep -Seconds 2; $ok = Test-BackendHealthy }
    if (-not $ok) { Log "backend /health NOT responding after ~120s - check artifacts/web/backend.log"; exit 1 }
    Log "/health OK; waiting for fresh plan (<1h15m) ..."
    $ok = $false
    for ($i = 0; $i -lt 30 -and -not $ok; $i++) { $a = Get-PlanAgeH; if ($a -ne $null -and $a -lt 1.25) { $ok = $true } else { Start-Sleep -Seconds 10 } }
    if (-not $ok) { Log "WARNING: plan still older than 1h15m - bots will only hold exits until it is fresh" }
  }
  # advisor shadow loop.sh: RETIRED 2026-09-30 - the backend cycle runs the shadow advisors itself.
  Log "advisor loop.sh retired (backend runs shadow) -> not started"
}

# ---------- (3) six paper runners (paper, d17bf, d13bf, d17bfg2, g2k20, d17bfg2c) ----------
if ($doBots) {
  foreach ($b in $bots) {
    $procs = if ($b.tag -eq "paper") {
      # paper has no --tag: a live untagged paper runner (exclude the tagged ones)
      @(Find-Procs 'bot\.run' | Where-Object { $_.CommandLine -match '--mode paper' -and $_.CommandLine -notmatch '--tag' })
    } else {
      Find-Procs ('bot\.run.*--tag ' + $b.tag + '( |$|")')
    }
    if ($procs.Count -gt 0) { Log "bot $($b.tag) already running (runner.lock held) -> skip"; continue }
    if ($DryRun) { Plan "start paper bot $($b.tag): .venv/Scripts/python.exe $($b.args -join ' ') (only if runner.lock free; backup+validate state.json)"; continue }
    if (-not (Backup-ValidateState $b.dir)) { continue }
    New-Item -ItemType Directory -Force (Join-Path $root $b.dir) | Out-Null
    Log "starting paper bot $($b.tag)"
    Start-Detached $py $b.args "$($b.dir)/stdout.log"
  }
}

# ---------- (4) carry ledger loop ----------
if ($doCarry) {
  $c = Find-Procs 'carry_paper.*--tag carry'
  if ($c.Count -gt 0) {
    Log "carry loop already running -> skip"
  } elseif ($DryRun) {
    Plan "start carry loop once: $carryCmdLine every 3600s (skip if running)"
  } else {
    Log "starting hourly carry ledger loop (once)"
    New-Item -ItemType Directory -Force (Join-Path $root "artifacts\bot\paper_carry") | Out-Null
    $loopBody = "while (1) { & `"$py`" scripts/carry_paper.py --once --equity 5000 --f 0.5 --tag carry; Start-Sleep -Seconds 3600 }"
    Start-Process powershell.exe -WindowStyle Hidden -ArgumentList @("-NoProfile", "-Command", $loopBody) -RedirectStandardOutput (Join-Path $root "artifacts\bot\paper_carry\stdout.log") | Out-Null
  }
}

# ---------- (5) health summary ----------
if ($DryRun) {
  Plan "print health: scripts/bot_health.py for all six runners (paper, d17bf, d13bf, d17bfg2, g2k20, d17bfg2c) + scripts/daily_status.py summary"
  Log "dry-run: plan only, started nothing"
  exit 0
}
if ($doBots) { & $py "scripts/bot_health.py" "artifacts/bot/paper" "artifacts/bot/paper_d17bf" "artifacts/bot/paper_d13bf" "artifacts/bot/paper_d17bfg2" "artifacts/bot/paper_g2k20" "artifacts/bot/paper_d17bfg2c" "artifacts/bot/paper_g2k20c"; }
& $py "scripts/daily_status.py"
Log "done (idempotent: a second run starts nothing new)"
