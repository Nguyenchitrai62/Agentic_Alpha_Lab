#!/bin/bash
# Dispatch an OpenCode worker and retry it when the session dies early on an OpenCode server error
# (SQLite "database is locked" in the shared opencode.db, an auto-rejected permission prompt, ...).
#
# usage: scripts/opencode_dispatch_retry.sh <tag> <ASSIGNMENT.md> [extra message]
#   RETRIES=3        maximum number of retries after an early death
#   EARLY_MIN=12     a run shorter than this many minutes that did not finish cleanly counts as an early death
#   PAUSE_S=200      wait between attempts (lets other sessions' writes drain)
# Every retry starts a NEW session (old sessions cannot be resumed) with a continuation note, so the worker reads
# its own folder first. Uses scripts/opencode_dispatch.sh unchanged.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
TAG="$1"; TASK="$2"; MSG="${3:-}"
RETRIES="${RETRIES:-3}"; EARLY_MIN="${EARLY_MIN:-12}"; PAUSE_S="${PAUSE_S:-200}"
D=artifacts/research/opencode_background
NOTE="CONTINUATION after an OpenCode server error (not your fault): first read research/tournament/$TAG/ (or your assignment's output folder) if it exists and continue from there; do not redo finished steps."
attempt=0
while :; do
  t0=$(date +%s)
  if [ "$attempt" -eq 0 ]; then bash scripts/opencode_dispatch.sh "$TAG" "$TASK" "$MSG"
  else bash scripts/opencode_dispatch.sh "$TAG" "$TASK" "$NOTE $MSG"; fi
  t1=$(date +%s)
  RUN=$(cat "$D/$TAG.current")
  mins=$(( (t1 - t0) / 60 ))
  early=0
  if [ "$mins" -lt "$EARLY_MIN" ]; then
    if grep -q "exit=1" "$D/$RUN.stderr.log" 2>/dev/null; then early=1; fi
    if grep -q "auto-rejecting" "$D/$RUN.stderr.log" 2>/dev/null; then early=1; fi
    if tail -n 3 "$D/$RUN.events.jsonl" 2>/dev/null | grep -q '"type":"error"'; then early=1; fi
  fi
  # an OpenCode server/DB error ends the session at any time: retry it too (late deaths included)
  if tail -n 3 "$D/$RUN.events.jsonl" 2>/dev/null | grep -q 'Failed to execute statement\|Unexpected server error\|database is locked'; then early=1; fi
  echo "[retry] $RUN minutes=$mins early=$early attempt=$attempt"
  if [ "$early" -eq 0 ] || [ "$attempt" -ge "$RETRIES" ]; then break; fi
  attempt=$((attempt + 1))
  sleep "$PAUSE_S"
done
