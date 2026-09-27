# Register a Task Scheduler entry that starts the backend (hidden) when this Windows user logs on.
# No admin rights needed. Remove with:  Unregister-ScheduledTask -TaskName AlphaLabBackend -Confirm:$false
#   powershell -ExecutionPolicy Bypass -File deploy\install_autostart.ps1
$root = Split-Path -Parent $PSScriptRoot
$script = Join-Path $root "deploy\start_backend.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`"" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName "AlphaLabBackend" -Action $action -Trigger $trigger -Settings $settings `
    -Description "Agentic Alpha Lab web backend (127.0.0.1:8724)" -Force | Out-Null
Write-Host "Registered task AlphaLabBackend. Start now with: Start-ScheduledTask -TaskName AlphaLabBackend"
