#!/bin/bash
# Dispatch one bounded task to an OpenCode worker (opencode-go/muse-spark-1.3-contributor) in the background.
#
# usage: scripts/opencode_dispatch.sh <tag> <ASSIGNMENT.md> [extra message]
#   COMMON=docs/opencode/OPENCODE_VF_COMMON.md   shared worker rules file (default below)
#   OPENCODE_EXE=...                path to opencode.exe (default: the npx cache install on this host)
#   OPENCODE_MODEL=...              model id (default opencode-go/muse-spark-1.3-contributor)
# Each call starts a NEW OpenCode session (resuming old sessions returns HTTP 400). Output goes to
# artifacts/research/opencode_background/<tag>_<UTC>.events.jsonl and .stderr.log (gitignored); the stderr log ends with
# "exit=N" when the worker stops, and <tag>.current holds the latest run name (use it in a Monitor until-loop).
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
EXE="${OPENCODE_EXE:-C:/Users/trait/AppData/Local/npm-cache/_npx/6af377548a73126e/node_modules/opencode-ai/bin/opencode.exe}"
MODEL="${OPENCODE_MODEL:-opencode-go/muse-spark-1.3-contributor}"
COMMON="${COMMON:-docs/opencode/OPENCODE_VF_COMMON.md}"
D=artifacts/research/opencode_background
mkdir -p "$D"
RUN="$1_$(date -u +%Y%m%dT%H%M%SZ)"
echo "$RUN" > "$D/$1.current"
"$EXE" run -m "$MODEL" --title "$1" --dir "$ROOT" --format json \
  "Read AGENTS.md, $COMMON and $2 (paths relative to the workspace root) and execute the assignment exactly. ${3:-} Stop when done." \
  < /dev/null > "$D/$RUN.events.jsonl" 2> "$D/$RUN.stderr.log"
echo "exit=$?" >> "$D/$RUN.stderr.log"
