# OpenCode task ops_restartstraddle - include the straddle paper ledger in the restart scripts
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. EXCEPTION (leader-assigned): you may edit `scripts/restart_all.ps1`,
`scripts/restart_all.sh` and their existing tests (find them: grep -l restart_all tests/*.py) and add `tests/test_ops_restartstraddle.py`.
Never start / stop any process yourself (only -DryRun / --dry-run runs are allowed).

## Task
The prospective straddle ledger (scripts/straddle_paper.py, doc docs/opencode/STRADDLEPAPER_20261007.md) runs as a self-looping process:
`.venv/Scripts/python.exe scripts/straddle_paper.py --equity 20000 --f 0.25 --tag straddle --interval 600`, stdout appended to
`artifacts/bot/paper_straddle/stdout.log`. Add it to restart_all.ps1 exactly like the carry loop is handled (detect "already running" by
command-line match `straddle_paper.*--tag straddle`, skip if running, else start detached with the same launch method the script uses for bots;
include it in `-Only carry` scope OR a new `-Only straddle` scope - pick the one that keeps register_keepalive.ps1 working: it calls
`restart_all.ps1 -Only bots` and `-Only carry`, so the simplest is to start the straddle loop in the carry scope; document it).
Mirror the plan line in restart_all.sh --dry-run output. Update/extend tests (dry-run prints the straddle plan line; idempotence: running
when the process exists prints "already running -> skip"). Run `-DryRun` once and paste the output into your test doc lines. All tests touching
restart_all must pass.
