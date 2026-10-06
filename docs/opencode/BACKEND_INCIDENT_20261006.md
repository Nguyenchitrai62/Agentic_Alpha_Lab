# Backend incident 2026-10-06: backend + tunnel connector both at 0 processes (~14:15 UTC), ~4 h on a stale plan

Read-only diagnosis (no process started/stopped, no state touched, git untouched).
Sources: `run_backend.ps1`, `deploy/start_backend.ps1`, `backend/server.py` (scheduler/heartbeat),
`backend/pipeline.py`, `backend/config.py`, `artifacts/backend_logs/uvicorn_local.log`,
`artifacts/web/backend_local.log`, `artifacts/web/backend_supervisor.log`,
`artifacts/web/cloudflared_api.log`, `artifacts/web/app.db` (jobs table),
`artifacts/research/advisor_shadow/trade_plan_*.json`, `docs/opencode/PAPER_DAY4_20261006.md`,
Application log (last 12 h, python/uvicorn keywords) + System log (sleep/wake/reboot/update) via
`Get-WinEvent` (read-only), Task Scheduler tasks, process list. Times UTC unless noted (local = +07:00).

## 1. Summary

- The stack was running as **foreground console runs** (`.\run_backend.ps1` default mode: uvicorn streams
  to that terminal, tunnel hidden child). The background supervisor was **not** in use
  (`backend_supervisor.log` untouched since 2026-10-03) and the `AlphaLabBackendWatchdog`
  scheduled task (`run_backend.ps1 -Ensure`) is **Disabled** (last run Oct 2, 612 missed runs).
- Three foreground launches are fingerprinted by tunnel-start + backend-startup pairs seconds apart:
  (A) ~17:40 UTC Oct 5, (B) 02:11:14Z tunnel / 02:11:18 backend (jobs id 972 `check/startup`),
  (C) 10:32:10Z tunnel / 10:32:16–17 backend (jobs id 982 `check/startup`, "nothing missing").
- Run C is the incident: last sign of life **10:32:17 UTC**, then nothing (no 15-min refresh plan
  rewrite ~10:47, no hourly phase plan ~11:01, no 12:01 UTC 4h cycle) until the leader's local restart
  at **14:16:27 UTC** (`uvicorn_local.log`, jobs 983/984). Death window: **10:32:17–~10:47 UTC**.
- At ~14:15 UTC: 0 backend + 0 tunnel-connector processes. Plans on disk frozen at generation
  **10:18–10:23 UTC for decision_bar 08:00 UTC**; the **12:00 UTC cycle never ran** → paper ran ~4 h
  on the 08:00-bar plan. **Most likely cause: run C's console window was closed (or Ctrl+C'd/stopped
  by whoever launched it at 10:32)** — same silent signature as run A's end at 02:01 UTC (log stops
  mid-stream, no shutdown/crash line). No evidence of crash traceback, OOM, worker action, or
  Windows update/sleep/reboot (all checked, see §4).

## 2. Timeline (UTC; local +07:00 in brackets)

| time (UTC) | event (evidence) |
| --- | --- |
| Oct 5 17:40 (00:40+1 local) | Run A starts in a console redirected to `backend_local.log` ("backend up", scheduler ON). |
| Oct 6 00:01–02:01 (07:01–09:01) | Run A healthy: 4h cycles, 15-min refreshes, hourly phase plans (log + jobs 969–971). |
| 02:01 (09:01) | Run A ends: `backend_local.log` stops right after a phase-plan line — **no exit/shutdown line** (console closed/killed, not graceful Ctrl+C which logs shutdown). |
| 02:11:14 / 02:11:18 (09:11) | Tunnel "Starting tunnel" + backend jobs-972 `check/startup` → **run B launched in foreground** (4 s apart = `run_backend.ps1` Stop-All → Start-Tunnel → uvicorn). |
| 02:11–10:23 | Run B healthy: cycles (04:02, 08:01 UTC), hourly phase plans, plan files rewritten (v376_s2 10:01:43Z; catalog plans 10:18–10:23Z for **decision_bar 08:00 UTC**). PAPER_DAY4 (10:27 UTC) still sees a fresh plan (10:01:28Z, 0.4 h). |
| 10:32:10 / 10:32:16–17 (17:32) | Tunnel "Starting tunnel" + jobs-982 `check/startup` "nothing missing" → **run C launched in foreground** (6 s apart, same signature; watchdog task Disabled so this was manual). |
| 10:32:17–~10:47 | **Run C dies silently.** No further jobs rows, plan files untouched after 10:18–10:23Z, no hourly phase plan ~11:01. |
| 11:01, 12:01, 13:01, 14:01 | Hourly v376 phase plans missed; **12:01 UTC 4h cycle (for the 12:00-bar plans) missed**. |
| ~14:15 (21:15) | Found: 0 backend + 0 connector processes; plans ~4 h stale (08:00-bar plan past the missed 12:00-bar due). |
| 14:16:25–27 (21:16) | Leader restarts backend locally (`uvicorn_local.log` pid 15544; startup check repairs 10 candle gaps, starts catch-up cycle, jobs 983/984). |

## 3. What was affected

- **All 9 catalog trade plans** (`trade_plan_v321/v301/v295/v367/v362/v342/v376/v340/v315` + v376
  sub-phase plans): stuck at decision_bar 08:00 UTC (generated 10:18–10:23Z); 12:00-bar plans never built.
- **Paper bots** (`paper`, `paper_d17bf`, `paper_d13bf`, `paper_d17bfg2`, `paper_g2k20`, `paper_d17bfg2c`
  per PAPER_DAY4): separate processes, kept trading ~10:32–14:16 UTC on the stale 08:00-bar plan
  (fills/orders in that window need verification from bot logs/state — not covered here, read-only scope).
- **Dashboard/API**: local `/health` down (backend gone); public `api-crypto…/health` down (0 connector
  processes; note: a `cloudflared.exe` PID 19276 exists *now* but wrote no startup lines after 10:32:14Z
  and its start/cmdline is unreadable — likely the SYSTEM service, not the `run_backend.ps1` connector
  the 0-count refers to; owner to confirm).
- **Follow-up flag (new)**: two uvicorns are bound/trying port 8724 right now — pid 13968 (`.venv`) and
  pid 15544 (system Python 3.11), both started 14:16:25 UTC. One must be failing to bind; keep exactly
  one and check which one serves `/health`.

## 4. Cause analysis (most → least likely)

1. **Console window closed (or Ctrl+C / host-terminal killed) on run C — most likely.** Foreground runs
   die with their console and leave no trace by design; run A shows the identical signature the same day
   (log ends mid-stream, no "backend exited"/shutdown line); supervisor unused since Oct 3, so nothing
   resurrected C. The 10:32 launch-then-silence within minutes fits a human opening a terminal, starting
   the stack, then closing/stopping it.
2. **Manual Ctrl+C stop by the 10:32 launcher** (variant of 1; `finally` in `run_backend.ps1` also kills
   the tunnel child — consistent with 0+0 at 14:15; a bare window-close would more likely orphan the
   hidden tunnel).
3. **Python crash / OOM — possible but zero surviving evidence.** Any traceback went to C's console
   buffer (lost with the window); Application log last-12 h has **0 errors and 0 python/uvicorn hits**;
   the backend is light (no heavy work in-process; heavy jobs go through `heavy_slot.py`).
4. **Killed by another process (`-Stop` / second launcher's Stop-All) — unlikely as the terminal cause:**
   a stop is normally followed by a new backend starting; none started until 14:16.
5. **A worker's actions — no evidence.** Workers are git-read-only, have no process-control tooling, and
   `heavy_slot.py` never touches the backend; nothing in any backend log implicates them.
6. **Windows update / sleep / reboot — ruled out.** Uptime since Oct 4 23:39 local; System log last 12 h:
   no sleep/wake/reboot/update events (only NTP time-sync + uptime notice); `server.py: _keep_awake()`
   blocks sleep while the backend runs.

## 5. Prevention (concrete; owner decisions marked ★)

- ★ Run the backend **only** via `.\run_backend.ps1 -Background` (supervisor loop in
  `deploy/start_backend.ps1` auto-restarts a dead backend; logs to `artifacts/web/backend.log` +
  `backend_supervisor.log`). Foreground runs are for live debugging only — never leave paper depending
  on a console window.
- ★ Re-enable the `AlphaLabBackendWatchdog` Task Scheduler task (`run_backend.ps1 -Ensure`; Disabled,
  last run Oct 2) so boot/reboot and periodic checks resurrect a down backend or a missing connector.
- Add a **plan-staleness alert** (extend `alert_watch`/`bot_health`): if `due_slot(now)` (pipeline.py) is
  past any `plan_status_<p>.completed_slot`, or any catalog plan's `generated_at` is older than ~30 min
  after a 4h close, page the owner. `/health` already returns **503 on stale scheduler heartbeat
  (>40 min)** — monitor it from outside (bot host or a second machine), not from this host alone.
- Keep the tunnel and backend fate linked and visible: after any manual launch, run
  `.\run_backend.ps1 -Status` and confirm one uvicorn on 8724 (today's duplicate 13968/15544 must be
  resolved to exactly one).

## 6. What to check first next time (ordered, all read-only)

1. `.\run_backend.ps1 -Status` (backend + tunnel counts, local + public `/health`).
2. Jobs tail: `SELECT id,kind,status,triggered_by,started_at,finished_at FROM jobs ORDER BY id DESC LIMIT 5`
   (+ `db.kv_get("data_check")`); a `check/startup` row dates the last (re)start.
3. Plan freshness: mtimes + `decision_bar`/`generated_at` of `artifacts/research/advisor_shadow/trade_plan_*.json`
   vs `due_slot(now)`; hourly `trade_plan_v376_s*.json`.
4. `artifacts/web/backend_supervisor.log` (background restarts), `artifacts/backend_logs/uvicorn_local.log`
   + `artifacts/web/backend_local.log` tails (foreground runs; an abrupt end with no shutdown line =
   console killed), `cloudflared_api.log` tail (connector starts/errors).
5. `Get-Process`/CIM for duplicate uvicorns or missing connector; Application/System event logs for the
   window; scheduled-task last-runs only if foul play by automation is suspected.
