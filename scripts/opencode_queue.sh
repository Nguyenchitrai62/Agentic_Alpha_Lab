#!/bin/bash
# Feed a queue of OpenCode assignments to scripts/opencode_dispatch_retry.sh, keeping at most MAX concurrent OpenCode sessions
# (the shared opencode.db returns "database is locked" when many sessions start or write at once).
#
# usage: scripts/opencode_queue.sh <queue file>
#   queue file: one task per line "tag|docs/opencode/OPENCODE_W_<tag>.md|optional extra message"; blank lines and # comments skipped
#   MAX=5        concurrent opencode.exe processes allowed (counts every OpenCode session on this host)
#   STAGGER_S=240  pause after each launch so session start-up writes do not collide
# Waits for all launched workers before exiting; each worker's log is artifacts/research/opencode_background/<tag>_<UTC>.*
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
MAX="${MAX:-5}"; STAGGER_S="${STAGGER_S:-240}"
running() { tasklist //FI "IMAGENAME eq opencode.exe" 2>/dev/null | grep -ci "opencode.exe"; }
while IFS='|' read -r tag task msg; do
  case "$tag" in ''|\#*) continue ;; esac
  while [ "$(running)" -ge "$MAX" ]; do sleep 60; done
  echo "[queue] $(date -u +%H:%M:%S) launching $tag (running=$(running))"
  bash scripts/opencode_dispatch_retry.sh "$tag" "$task" "${msg:-}" > "artifacts/research/opencode_background/$tag.queue.log" 2>&1 &
  sleep "$STAGGER_S"
done < "$1"
wait
echo "[queue] $(date -u +%H:%M:%S) all launched workers finished"
