# OpenCode task bot_hang - a paper runner hung for 14 minutes with 0 CPU (2026-10-08 11:16 UTC, paper_d17bf); find blocking waits and add guards
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. You MAY edit `bot/run.py`, `bot/paper.py` (minimal diffs) with new tests in
`tests/test_bot_hang.py`; notes in `research/diagnostics/bot_hang/`. Never touch artifacts/bot/* or running processes (12 paper runners use the
code on disk only at restart). Print progress every 10 minutes.

## Evidence
artifacts/bot/paper_d17bf/stdout.log: last line 2026-10-08 11:16:01 (dip placements), then nothing; the python process stayed alive with CPU
time frozen (blocked wait, not a loop) until the leader restarted it at 11:29. All HTTP calls in bot/ pass a timeout (grep). 12 runners share
the kline cache (kcache *.json + *.lock files, msvcrt / fcntl locks) and other shared files (plan json, feeds parquet via --k2-tilt,
state.json / actions.jsonl writes).
## Tasks
1. List every potentially unbounded blocking call in the paper cycle (file locks without timeout, parquet / json reads of files another process
   may be writing, sleeps, subprocesses, queue / thread joins), with file:line.
2. Reproduce a hang deterministically in a test where possible (e.g. a lock held by another process).
3. Fix with the smallest safe changes: bounded lock acquisition (timeout -> log op=lock_timeout, skip that refresh, continue the cycle with the
   last good data), and a cycle watchdog: if one cycle exceeds N minutes (N = 10, frozen), log op=cycle_stall and exit non-zero so the
   owner's keepalive / restart_all restarts it (state is persisted every cycle - confirm). Keep all existing behaviour and tests.
4. Report (Vietnamese 3 lines + list of changes) and say whether the running runners need a restart to get the fix.
