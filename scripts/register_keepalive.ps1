# register_keepalive.ps1 - owner-run keepalive registration (paper only).
#
# OWNER runs once from a normal PowerShell (no elevation required):
#   .\scripts\register_keepalive.ps1 -Status                 (default: print plan, change nothing)
#   .\scripts\register_keepalive.ps1 -Register               (create/update tasks)
#   .\scripts\register_keepalive.ps1 -Unregister             (remove the two tasks below)
#   .\scripts\register_keepalive.ps1 -Register -EveryMinutes 10
#
# Tasks (current user, run only when logged on, hidden, no stored password):
#   AlphaLabRunnersKeepAlive - every N min: restart_all.ps1 -Only bots
#     plus a second action for restart_all.ps1 -Only carry; working dir = repo
#     root; Parallel instances (leader 2026-10-07: with IgnoreNew a task whose detached bot children keep it "Running" would never re-trigger; restart_all is idempotent so overlapping runs are harmless); NO execution time limit
#     (see below why); paper only.
#   Backend: enable existing AlphaLabBackendWatchdog if present (its definition
#     is printed first); otherwise create AlphaLabBackendKeepAlive running
#     run_backend.ps1 -Ensure every N min.
#
# Survival note: restart_all.ps1 Start-Detached launches each bot via
#   Start-Process cmd.exe /c '"py" args >> log 2>&1' (the cmd wrapper stays up
#   for the bot lifetime) and the carry loop via Start-Process powershell.exe
#   with redirected output; run_backend.ps1 -Ensure launches the supervisor
#   deploy\start_backend.ps1 the same way. Start-Process children survive a
#   normal parent exit, but a Task Scheduler execution time limit kills through
#   the job object and could take the bots/supervisor with it. Hence both tasks
#   use ExecutionTimeLimit = 0 (no limit); restart_all/-Ensure themselves finish
#   in seconds when healthy, so no limit is safe. Idempotent. Prints a summary.
#   This script never starts/stops any process itself.
param(
  [switch]$Register,
  [switch]$Unregister,
  [switch]$Status,
  [int]$EveryMinutes = 10
)

$ErrorActionPreference = "Continue"
$root = $PSScriptRoot | Split-Path -Parent
$runnerTask = "AlphaLabRunnersKeepAlive"
$backendTask = "AlphaLabBackendKeepAlive"
$watchdogTask = "AlphaLabBackendWatchdog"
$restartScript = Join-Path $root "scripts\restart_all.ps1"
$backendScript = Join-Path $root "run_backend.ps1"

function Show-Status {
  Write-Host "KEEPALIVE STATUS (no changes made)"
  Write-Host ("  repo root : {0}" -f $root)
  Write-Host ("  interval  : every {0} minutes" -f $EveryMinutes)
  Write-Host ("  runner task : {0}" -f $runnerTask)
  Write-Host ("    action 1  : powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"{0}`" -Only bots" -f $restartScript)
  Write-Host ("    action 2  : powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"{0}`" -Only carry" -f $restartScript)
  Write-Host "    principal : current user, run only when logged on, hidden, no stored password"
  Write-Host "    instances : Parallel (restart_all is idempotent; IgnoreNew could stall if children keep the task Running); time limit: none (children survive)"
  $t = Get-ScheduledTask -TaskName $runnerTask -ErrorAction SilentlyContinue
  if ($t) { Write-Host ("  {0} : PRESENT state={1}" -f $runnerTask, $t.State) } else { Write-Host ("  {0} : ABSENT (would be created on -Register)" -f $runnerTask) }
  $w = Get-ScheduledTask -TaskName $watchdogTask -ErrorAction SilentlyContinue
  if ($w) {
    Write-Host ("  {0} : PRESENT state={1} (would be enabled on -Register; definition:)" -f $watchdogTask, $w.State)
    $w | Format-List TaskName, State, Author, Description | Out-String | Write-Host
    Get-ScheduledTaskInfo -TaskName $watchdogTask | Format-List | Out-String | Write-Host
  } else {
    Write-Host ("  {0} : ABSENT" -f $watchdogTask)
    $b = Get-ScheduledTask -TaskName $backendTask -ErrorAction SilentlyContinue
    if ($b) { Write-Host ("  {0} : PRESENT state={1}" -f $backendTask, $b.State) } else { Write-Host ("  {0} : ABSENT (would be created on -Register)" -f $backendTask) }
    Write-Host ("    action    : powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"{0}`" -Ensure" -f $backendScript)
  }
  Write-Host "Run with -Register to create/update, -Unregister to remove. Registration is the OWNER's decision."
}

function New-KeepAliveParts([string]$kind) {
  $at = (Get-Date).AddMinutes(1)
  $trigger = New-ScheduledTaskTrigger -Once -At $at -RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes) -RepetitionDuration ([TimeSpan]::MaxValue)
  $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
  $settings = New-ScheduledTaskSettingsSet -MultipleInstances Parallel -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
  if ($kind -eq "runner") {
    $a1 = New-ScheduledTaskAction -Execute "powershell.exe" -Argument ("-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"{0}`" -Only bots" -f $restartScript) -WorkingDirectory $root
    $a2 = New-ScheduledTaskAction -Execute "powershell.exe" -Argument ("-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"{0}`" -Only carry" -f $restartScript) -WorkingDirectory $root
    return @{ Trigger = $trigger; Principal = $principal; Settings = $settings; Actions = @($a1, $a2) }
  }
  $a = New-ScheduledTaskAction -Execute "powershell.exe" -Argument ("-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"{0}`" -Ensure" -f $backendScript) -WorkingDirectory $root
  return @{ Trigger = $trigger; Principal = $principal; Settings = $settings; Actions = @($a) }
}

function Register-KeepAlive {
  Write-Host ("KEEPALIVE REGISTER every {0} min (paper only; idempotent)" -f $EveryMinutes)
  $parts = New-KeepAliveParts "runner"
  $existing = Get-ScheduledTask -TaskName $runnerTask -ErrorAction SilentlyContinue
  if ($existing) {
    Set-ScheduledTask -TaskName $runnerTask -Action $parts.Actions -Trigger $parts.Trigger -Principal $parts.Principal -Settings $parts.Settings | Out-Null
    Write-Host ("  {0} : updated" -f $runnerTask)
  } else {
    Register-ScheduledTask -TaskName $runnerTask -Action $parts.Actions -Trigger $parts.Trigger -Principal $parts.Principal -Settings $parts.Settings -Description "AlphaLab paper runners keepalive (restart_all -Only bots + -Only carry)" | Out-Null
    Write-Host ("  {0} : created" -f $runnerTask)
  }
  $w = Get-ScheduledTask -TaskName $watchdogTask -ErrorAction SilentlyContinue
  if ($w) {
    Write-Host ("  {0} : PRESENT state={1}; current definition:" -f $watchdogTask, $w.State)
    $w | Format-List TaskName, State, Author, Description | Out-String | Write-Host
    Get-ScheduledTaskInfo -TaskName $watchdogTask | Format-List | Out-String | Write-Host
    Enable-ScheduledTask -TaskName $watchdogTask | Out-Null
    Write-Host ("  {0} : enabled" -f $watchdogTask)
  } else {
    $bp = New-KeepAliveParts "backend"
    $bExisting = Get-ScheduledTask -TaskName $backendTask -ErrorAction SilentlyContinue
    if ($bExisting) {
      Set-ScheduledTask -TaskName $backendTask -Action $bp.Actions -Trigger $bp.Trigger -Principal $bp.Principal -Settings $bp.Settings | Out-Null
      Write-Host ("  {0} : updated (no {1} present)" -f $backendTask, $watchdogTask)
    } else {
      Register-ScheduledTask -TaskName $backendTask -Action $bp.Actions -Trigger $bp.Trigger -Principal $bp.Principal -Settings $bp.Settings -Description "AlphaLab backend keepalive (run_backend -Ensure)" | Out-Null
      Write-Host ("  {0} : created (no {1} present)" -f $backendTask, $watchdogTask)
    }
  }
  Write-Host "Summary: runner keepalive + backend watchdog/keepalive registered. Verify with Get-ScheduledTask and scripts/bot_health.py."
}

function Unregister-KeepAlive {
  Write-Host "KEEPALIVE UNREGISTER (removes tasks created by -Register; watchdog left untouched)"
  foreach ($name in @($runnerTask, $backendTask)) {
    $t = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($t) { Unregister-ScheduledTask -TaskName $name -Confirm:$false; Write-Host ("  {0} : removed" -f $name) }
    else { Write-Host ("  {0} : absent (nothing to do)" -f $name) }
  }
  $w = Get-ScheduledTask -TaskName $watchdogTask -ErrorAction SilentlyContinue
  if ($w) { Write-Host ("  {0} : kept as-is state={1} (use Task Scheduler to disable if needed)" -f $watchdogTask, $w.State) }
  Write-Host "Summary: keepalive tasks removed."
}

if ($Register -and $Unregister) { Write-Error "use only one of -Register / -Unregister"; exit 2 }
elseif ($Unregister) { Unregister-KeepAlive }
elseif ($Register) { Register-KeepAlive }
else { Show-Status }
