# OpenCode task bot_resilience
Read AGENTS.md, docs/BOT_EXECUTION.md, bot/*.py, tests/test_bot_mirror.py. Write ONLY bot/run.py, bot/paper.py, bot/mirror.py (minimal fixes), tests/test_bot_resilience.py (new) and a short "Failure modes" section in docs/BOT_EXECUTION.md. No commits, no live / testnet orders, no network in tests, no credentials, never touch .env. Paper bots run from this code: keep default behaviour identical unless a test proves a bug (then fix + say so). All existing tests must still pass.
Write failure-mode tests with a fake exchange (subclass / stub of the PaperExchange interface) and fix any real bug you find:
1. Restart mid-position: state.json + exchange with an open dip piece and its stop/TP -> a new Runner must adopt it without duplicate entries, keep protection, not re-place filled rungs.
2. Partial fill of a dip entry: protection orders sized to the filled qty, remaining qty still resting, budget accounting uses the filled part.
3. Exchange error on placing a stop after a fill (API error / timeout): the bot must retry next cycle and, if the position stays unprotected for > 2 cycles, close it at market (reduce-only) and log op=unprotected_close.
4. Rejected order (min notional / qty step): logged, skipped, no infinite retry storm (at most one attempt per cycle per link).
5. Clock skew / late cycle (cycle runs 20 min late): time exits and stale-plan logic still correct; no entry fills inside the first 5 minutes after a 4h close.
6. Plan file missing / corrupt JSON: keep protection, place no new entries, log op=plan_error, no crash.
7. Duplicate fill events (same execId twice): applied once.
Report at the end of your answer (<= 15 lines): bugs found and fixed, tests added, pytest summary of tests/test_bot_mirror.py and tests/test_bot_resilience.py.
