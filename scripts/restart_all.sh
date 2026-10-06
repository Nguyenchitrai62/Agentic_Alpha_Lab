#!/bin/bash
# restart_all.sh - idempotent post-reboot restore (delegates detached launches to restart_all.ps1).
#
# Order: (1) backend uvicorn on 127.0.0.1:8724 (local only, never the public tunnel),
# wait for /health + fresh plan (<1h15m); (2) advisor shadow loop.sh retired
# 2026-09-30 (the backend cycle runs the shadow advisors itself - not started);
# (3) the paper runners (paper, d17bf, d13bf, d17bfg2, g2k20, d17bfg2c, g2k20c),
# each only if its runner.lock is free (live process check); state.json is
# backed up first (state.json.bak_<ts>) and validated as JSON; (4) the hourly
# carry ledger loop once (every 3600s); (5) bot_health for every runner +
# daily_status summary.
#
# Incident 2026-10-06: runners started with nohup from a time-limited shell died
# when that shell ended. restart_all.ps1 now starts processes via WMI
# (Invoke-CimMethod Win32_Process Create), parented to the WMI host so bots
# survive the launching console. This script performs NO direct launches
# (no nohup children of this shell): the real starts are delegated to
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/restart_all.ps1 [-Only X] [-DryRun]
# so both entry points share one detached-launch path.
#
# Idempotent: running twice starts nothing new (a component already running is
# skipped - "already running (runner.lock held) -> skip"). --dry-run prints the
# plan AND the exact powershell delegation command, starts nothing, runs no
# health checks. --only bots|backend|carry limits the scope (--only backend
# includes the advisor loop.sh plan feed note).
# NEVER sets BOT_ALLOW_LIVE, NEVER starts testnet or live modes (paper only).
#
# Usage:
#   bash scripts/restart_all.sh [--dry-run] [--only bots|backend|carry]
#   bash scripts/restart_all.sh --dry-run --only bots
#   bash scripts/restart_all.sh --dry-run --only=bots
#   bash scripts/restart_all.sh --dry-run bots   # bare scope also accepted
set -u

ROOT="$(cd "$(dirname "$0")/.." && (pwd -W 2>/dev/null || pwd))"
DRY_RUN=0
ONLY=all
# single-pass parser (leader fix 2026-10-06: the old two-loop parser exited on '--only <value>')
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --only) shift; [ $# -gt 0 ] || { echo "usage: $0 [--dry-run] [--only bots|backend|carry]" >&2; exit 2; }; ONLY="$1" ;;
    --only=*) ONLY="${1#--only=}" ;;
    bots|backend|carry) ONLY="$1" ;;
    --only-bots) ONLY=bots ;;
    --only-backend) ONLY=backend ;;
    --only-carry) ONLY=carry ;;
    -h|--help) echo "usage: $0 [--dry-run] [--only bots|backend|carry]"; exit 0 ;;
    *) echo "unknown arg: $1 (usage: $0 [--dry-run] [--only bots|backend|carry])" >&2; exit 2 ;;
  esac
  shift
done
case "$ONLY" in all|bots|backend|carry) ;; *) echo "bad --only: $ONLY (bots|backend|carry)" >&2; exit 2 ;; esac

# --- canonical commands (reference; must match restart_all.ps1 and the live processes) ---
BACKEND_CMD='.venv/Scripts/python.exe -m uvicorn backend.server:app --host 127.0.0.1 --port 8724 --timeout-keep-alive 30 --no-access-log'
LOOP_CMD='bash artifacts/research/advisor_shadow/loop.sh'
CARRY_CMD='.venv/Scripts/python.exe scripts/carry_paper.py --once --equity 5000 --f 0.5 --tag carry'
# tag|state_dir|bot args (paper = R2-4P, no tag; d13bf/d17bf/d17bfg2/g2k20 as observed 2026-10-06 incl. --interval 25)
BOTS="
paper|artifacts/bot/paper|-m bot.run --mode paper --equity 5000 --interval 25
d17bf|artifacts/bot/paper_d17bf|-m bot.run --mode paper --equity 5000 --corr-size --dip-mult 1.7 --bear-book --interval 25 --tag d17bf
d13bf|artifacts/bot/paper_d13bf|-m bot.run --mode paper --equity 5000 --corr-size --dip-mult 1.3 --bear-book --interval 25 --tag d13bf
d17bfg2|artifacts/bot/paper_d17bfg2|-m bot.run --mode paper --equity 5000 --corr-size --dip-mult 1.7 --dip-gross-cap 2.0 --bear-book --adopt-fresh --interval 25 --tag d17bfg2
g2k20|artifacts/bot/paper_g2k20|-m bot.run --mode paper --equity 5000 --corr-size --dip-mult 2.0 --dip-gross-cap 2.0 --bear-book --adopt-fresh --interval 25 --tag g2k20
d17bfg2c|artifacts/bot/paper_d17bfg2c|-m bot.run --mode paper --equity 5000 --corr-size --dip-mult 1.7 --dip-gross-cap 2.0 --bear-book --adopt-fresh --carry-f 0.25 --interval 25 --tag d17bfg2c
g2k20c|artifacts/bot/paper_g2k20c|-m bot.run --mode paper --equity 5000 --corr-size --dip-mult 2.0 --dip-gross-cap 2.0 --bear-book --adopt-fresh --carry-f 0.25 --interval 25 --tag g2k20c
"

log() { echo "[restart_all] $*"; }
plan_line() { echo "PLAN: $*"; }

# --- delegation command (single detached-launch path via WMI in restart_all.ps1) ---
PS_BASE="powershell -NoProfile -ExecutionPolicy Bypass -File scripts/restart_all.ps1"
PS_DELEGATE="$PS_BASE"
if [ "$ONLY" != "all" ]; then PS_DELEGATE="$PS_DELEGATE -Only $ONLY"; fi
if [ $DRY_RUN -eq 1 ]; then PS_DELEGATE="$PS_DELEGATE -DryRun"; fi

if [ $DRY_RUN -eq 1 ]; then
  echo "POWERSHELL: $PS_DELEGATE"
  case "$ONLY" in all|backend) plan_line "start backend: $BACKEND_CMD (local only, never the public tunnel)" ;; esac
  case "$ONLY" in all|backend) plan_line "advisor loop.sh retired (backend runs shadow) -> not started: $LOOP_CMD" ;; esac
  case "$ONLY" in all|bots)
    echo "$BOTS" | grep '|' | while IFS='|' read -r tag dir args; do
      [ -n "$tag" ] || continue
      plan_line "start paper bot $tag: .venv/Scripts/python.exe $args (only if runner.lock free; backup+validate state.json; skip when already running)"
    done
    ;;
  esac
  case "$ONLY" in all|carry) plan_line "start carry loop once: $CARRY_CMD every 3600s (skip if running; skip when already running)" ;; esac
  plan_line "print health: scripts/bot_health.py for all runners (paper, d17bf, d13bf, d17bfg2, g2k20, d17bfg2c, g2k20c) + scripts/daily_status.py summary"
  log "dry-run: plan only, started nothing (real starts delegate to restart_all.ps1 via WMI Win32_Process)"
  exit 0
fi

# Real starts: delegate to restart_all.ps1 (WMI Win32_Process detached path).
# This shell starts nothing itself and stops nothing (read-only from here on).
log "delegating real starts to restart_all.ps1 (WMI detached-launch path; this shell starts nothing itself)"
echo "POWERSHELL: $PS_DELEGATE"
if [ "$ONLY" = "all" ]; then
  powershell -NoProfile -ExecutionPolicy Bypass -File "$ROOT/scripts/restart_all.ps1"
else
  powershell -NoProfile -ExecutionPolicy Bypass -File "$ROOT/scripts/restart_all.ps1" -Only "$ONLY"
fi
rc=$?
exit $rc
