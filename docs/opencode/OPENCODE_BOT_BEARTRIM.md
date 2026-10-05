# OpenCode task: bot - trim open book longs when the bear regime starts (read AGENTS.md, OPENCODE_VF_COMMON.md, docs/BOT_EXECUTION.md)
Scope: edit ONLY bot/mirror.py, bot/run.py and tests/test_bot_mirror.py. Default behaviour unchanged (all existing tests pass unchanged).
No live trading, no keys, no commits, do not touch the backend.
Gap (docs/BOT_EXECUTION.md 'Known gap'): with --bear-book the research engine (v410) halves the book LONG target in the bear regime, so the
grid trader trims existing longs toward the halved target; the bot only halves new entries / adds. Implement: when bear_book and bear, for every
open BOOK piece with side > 0 whose qty exceeds 0.5 x the qty implied by the plan's current sub-book position weight (plan weight x equity /
price), place ONE reduce-only LIMIT sell (link <piece>B<t36(bar start)>) at the current bar's plan price level used for reduce orders if the plan
has one, else at the last close x (1 + 0.001), for the excess qty, valid until the end of the current 4h bar; never trim below 0.5 x; at most one
trim per piece per bear episode (record it in the ledger piece: trimmed_bear = True; reset when the regime flips back to bull). Tests: trim
issued once in bear, not in bull, never below half, default-off identity. Run pytest on tests/test_bot_mirror.py and report.
