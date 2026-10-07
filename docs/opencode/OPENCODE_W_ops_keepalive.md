# OpenCode task ops_keepalive - owner-run script that registers Windows scheduled tasks keeping backend + paper runners alive
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. EXCEPTION to the common write scope (leader-assigned): you may CREATE
`scripts/register_keepalive.ps1`, `tests/test_ops_keepalive.py` and `docs/opencode/KEEPALIVE_20261007.md`. You must NOT run the
registration (creating scheduled tasks is the OWNER's decision), must not start / stop any process, must not edit restart_all.ps1,
run_backend.ps1, bot/ or backend/.

## Why
Paper runners died silently three times (2026-10-06 11:55 and 15:09 UTC, 2026-10-07 03:24 UTC: all seven + the carry loop in the same
second, no error in stdout.log; see docs/opencode/OOS_WEEK2_20261007.md and docs/opencode/BACKEND_INCIDENT_20261006.md). Each time hours of
prospective evidence were lost. Processes started from an agent's shell die with that shell; the owner's console is the only reliable parent,
and the scheduled task `AlphaLabBackendWatchdog` exists but is Disabled. `scripts/restart_all.ps1` is idempotent (skips anything already
running, backs up state.json) and `run_backend.ps1 -Ensure` restarts the backend only if it is down.

## Implement `scripts/register_keepalive.ps1` (owner runs it once from an elevated or normal PowerShell)
- Parameters: `-Register` (create / update), `-Unregister`, `-Status` (default: print what it WOULD do, change nothing), `-EveryMinutes 10`.
- Registers (current user, run whether or not a window is open is NOT required - use "run only when user is logged on", hidden window,
  no stored password) two tasks:
  * `AlphaLabRunnersKeepAlive`: every N minutes, `powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File
    <repo>\scripts\restart_all.ps1 -Only bots` (and a second action or task for `-Only carry`), working directory = repo root,
    "do not start a new instance if already running", execution time limit 5 minutes (restart_all only launches detached processes; check
    that the launched bots are NOT children that the task scheduler kills when the 5-minute limit ends - read restart_all.ps1's launch path
    and explain in the doc; if they would be killed, use a launch method whose children survive, e.g. `Start-Process` with -WindowStyle Hidden
    from a task configured with no execution limit, and document the choice).
  * Enable the existing `AlphaLabBackendWatchdog` if present (print its current definition first), otherwise create
    `AlphaLabBackendKeepAlive` running `run_backend.ps1 -Ensure` every N minutes.
- Never sets BOT_ALLOW_LIVE, never passes testnet / live flags (paper only). Idempotent. Prints a summary.
- Tests (tests/test_ops_keepalive.py): static checks only (the script contains no live / testnet flags, uses -Only bots / carry, default
  mode changes nothing; parse with powershell -NoProfile -Command "[ScriptBlock]::Create((Get-Content ... -Raw))" to prove it parses).
- Doc (Vietnamese, <= 40 lines): exact owner commands (`.\scripts\register_keepalive.ps1 -Status`, then `-Register`), what each task does,
  how to verify (Get-ScheduledTask ..., scripts/bot_health.py), how to remove.
