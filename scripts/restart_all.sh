#!/bin/bash
# restart_all.sh - idempotent post-reboot restore (read-only checks, never stops anything).
#
# Order: (1) backend uvicorn on 127.0.0.1:8724 (local only, NEVER the public
# tunnel/cloudflared), wait for /health + fresh plan (<1h15m); (2) advisor
# shadow loop.sh exactly once (skip if running); (3) the six paper runners
# (paper, d17bf, d13bf, d17bfg2, g2k20, d17bfg2c),
# each only if its runner.lock is free (live process check); state.json is
# backed up first and validated as JSON; (4) the hourly carry ledger loop once;
# (5) bot_health for every runner + daily_status summary.
#
# Idempotent: running twice starts nothing new. --dry-run prints the plan only
# (starts nothing, runs no health checks). --only bots|backend|carry limits the
# scope (--only backend includes the advisor loop.sh plan feed).
# NEVER sets BOT_ALLOW_LIVE, NEVER starts testnet/live (paper only).
#
# Usage:
#   bash scripts/restart_all.sh [--dry-run] [--only bots|backend|carry]
set -u

ROOT="$(cd "$(dirname "$0")/.." && (pwd -W 2>/dev/null || pwd))"  # Windows path for the venv Python (pwd -W on git-bash)
PY="$ROOT/.venv/Scripts/python.exe"
BACKEND_URL="http://127.0.0.1:8724/health"
PLAN="$ROOT/artifacts/research/advisor_shadow/trade_plan_v376.json"
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

# --- canonical commands (must match the observed live processes) ---
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
"

log() { echo "[restart_all] $*"; }

# NOTE: all process checks below are READ-ONLY (ps / Get-CimInstance); this
# script never stops a process. A runner whose command line is already present
# is skipped (its runner.lock is held); else state.json is backed up +
# JSON-validated before starting.

backend_healthy() {
  "$PY" -c "import sys,urllib.request; r=urllib.request.urlopen('$BACKEND_URL',timeout=5); sys.exit(0 if r.status==200 else 1)" 2>/dev/null
}

plan_age_ok() {
  # $1 = max age hours; 0 = fresh plan age in hours printed
  "$PY" -c "
import json,sys
from datetime import datetime,timezone
from pathlib import Path
try:
    gen=json.loads(Path(r'''$PLAN''').read_text()).get('generated_at')
    t=datetime.fromisoformat(str(gen))
    if t.tzinfo is None: t=t.replace(tzinfo=timezone.utc)
    age=(datetime.now(timezone.utc)-t).total_seconds()/3600
    print(f'{age:.2f}')
    sys.exit(0 if age < float('$1') else 1)
except Exception as e:
    print(f'unknown ({e})'); sys.exit(1)
"
}

backup_and_validate_state() {
  # $1 = state dir (relative); backup state.json, validate JSON (before start;
  # this script never stops a runner, so no post-stop validation is needed)
  d="$ROOT/$1"
  st="$d/state.json"
  [ -f "$st" ] || { log "$1: no state.json yet (fresh start)"; return 0; }
  ts="$(date -u +%Y%m%dT%H%M%SZ)"
  cp "$st" "$d/state.json.bak_$ts" && log "$1: state.json backed up -> state.json.bak_$ts"
  "$PY" -c "import json; json.load(open(r'''$st''',encoding='utf-8')); print('state.json valid JSON')" || { log "$1: state.json INVALID JSON - NOT starting"; return 1; }
}

plan_line() { echo "PLAN: $*"; }
STARTED=0; SKIPPED=0
do_backend=0; do_bots=0; do_carry=0
case "$ONLY" in all) do_backend=1; do_bots=1; do_carry=1 ;; backend) do_backend=1 ;; bots) do_bots=1 ;; carry) do_carry=1 ;; esac

# ---------- (1) backend ----------
if [ $do_backend -eq 1 ]; then
  if backend_healthy; then
    age="$(plan_age_ok 9999 2>/dev/null || echo unknown)"
    log "backend healthy (/health OK, plan age ${age}h) -> skip start (local only, no tunnel)"
    SKIPPED=$((SKIPPED+1))
  else
    if [ $DRY_RUN -eq 1 ]; then plan_line "start backend: $BACKEND_CMD (local only, never the public tunnel)"; else
      log "backend down -> starting local uvicorn (NEVER the public tunnel; never sets BOT_ALLOW_LIVE)"
      mkdir -p "$ROOT/artifacts/web"
      # shellcheck disable=SC2086
      nohup $PY $BACKEND_CMD >> "$ROOT/artifacts/web/backend.log" 2>&1 &
      log "waiting for $BACKEND_URL ..."
      ok=0
      for _ in $(seq 1 60); do sleep 2; backend_healthy && { ok=1; break; }; done
      [ $ok -eq 1 ] || { log "backend /health NOT responding after ~120s - check artifacts/web/backend.log"; exit 1; }
      log "/health OK; waiting for fresh plan (<1h15m) ..."
      ok=0
      for _ in $(seq 1 30); do plan_age_ok 1.25 >/dev/null 2>&1 && { ok=1; break; }; sleep 10; done
      [ $ok -eq 1 ] || { log "WARNING: plan still older than 1h15m - bots will only hold exits until it is fresh"; }
      STARTED=$((STARTED+1))
    fi
  fi
  # (2) advisor shadow loop.sh: RETIRED 2026-09-30 - the backend cycle runs the shadow advisors itself (backend/pipeline.py job_cycle).
  log "advisor loop.sh retired (backend runs shadow) -> not started"
fi

# ---------- (3) six paper runners (paper, d17bf, d13bf, d17bfg2, g2k20, d17bfg2c) ----------
if [ $do_bots -eq 1 ]; then
  echo "$BOTS" | grep '|' | while IFS='|' read -r tag dir args; do
    [ -n "$tag" ] || continue
    if [ "$tag" = "paper" ]; then
      running=0
      if ps -ef 2>/dev/null | grep -F "bot.run --mode paper" | grep -v grep | grep -qv -- "--tag"; then running=1; fi
      # fallback: powershell match without --tag is imprecise; process-list check above is authoritative on git-bash
    else
      running=0
      if ps -ef 2>/dev/null | grep -F "bot.run" | grep -F -- "--tag $tag" | grep -v grep >/dev/null 2>&1; then running=1; fi
    fi
    if [ "$running" = "1" ]; then
      log "bot $tag already running (runner.lock held) -> skip"
      continue
    fi
    if [ $DRY_RUN -eq 1 ]; then plan_line "start paper bot $tag: .venv/Scripts/python.exe $args (only if runner.lock free; backup+validate state.json)"; continue; fi
    backup_and_validate_state "$dir" || continue
    mkdir -p "$ROOT/$dir"
    log "starting paper bot $tag"
    # shellcheck disable=SC2086
    nohup $PY $args >> "$ROOT/$dir/stdout.log" 2>&1 &
  done
  # NOTE: `while` runs in a subshell; STARTED/SKIPPED for bots are informational only.
fi

# ---------- (4) carry ledger loop ----------
if [ $do_carry -eq 1 ]; then
  if ps -ef 2>/dev/null | grep -F "carry_paper" | grep -F -- "--tag carry" | grep -v grep >/dev/null 2>&1; then
    log "carry loop already running -> skip"
    SKIPPED=$((SKIPPED+1))
  else
    if [ $DRY_RUN -eq 1 ]; then plan_line "start carry loop once: $CARRY_CMD every 3600s (skip if running)"; else
      log "starting hourly carry ledger loop (once)"
      mkdir -p "$ROOT/artifacts/bot/paper_carry"
      nohup bash -c "while true; do .venv/Scripts/python.exe $CARRY_CMD; sleep 3600; done" >> "$ROOT/artifacts/bot/paper_carry/stdout.log" 2>&1 &
      STARTED=$((STARTED+1))
    fi
  fi
fi

# ---------- (5) health summary ----------
if [ $DRY_RUN -eq 1 ]; then
  plan_line "print health: scripts/bot_health.py for all six runners (paper, d17bf, d13bf, d17bfg2, g2k20, d17bfg2c) + scripts/daily_status.py summary"
  log "dry-run: plan only, started nothing"
  exit 0
fi
if [ $do_bots -eq 1 ]; then
  # shellcheck disable=SC2086
  "$PY" scripts/bot_health.py artifacts/bot/paper artifacts/bot/paper_d17bf artifacts/bot/paper_d13bf artifacts/bot/paper_d17bfg2 artifacts/bot/paper_g2k20 artifacts/bot/paper_d17bfg2c || true
fi
"$PY" scripts/daily_status.py || true
log "done (idempotent: a second run starts nothing new)"
