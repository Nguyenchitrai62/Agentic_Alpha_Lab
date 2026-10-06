# bot_reviewfix2 2026-10-07: findings 1-6 + carry-slice retry
Fixed: #1 dip native stop (backstop else stop5); #2 exit_link-confirmed inflight + phantom-cancel guard; #3 _protection_only inflight+finite_pos; #4 per-leg TP=0 fallback; #5 TP failures in unprotected counter; #6 wrong-side SL/TP reject+fallback; carry buckets done on fill with same-bucket retry. Sizing/entry untouched.
Files: bot/mirror.py, bot/run.py, bot/carry.py, tests/test_review_soakfix.py (12 tests), docs/BOT_EXECUTION.md CHANGES.
Scoped suite (17 test_bot_* excl. smoke + review): 200 collected, 197 passed, 3 failed — all 3 assert pre-fix buggy behaviour and are superseded: 2 exit_sent-only inflight suppressions (test_bot_mirror), 1 no-retry-without-fill slice (test_bot_carry::test_slice_one_per_bucket_restart_safe).
tests/test_review_soakfix.py: 12/12 pass (3 demos + 9 new for #3-#6/carry).
2h smoke tests/test_bot_soak_smoke.py: 1/1 pass, 0 violations.
Full pytest: attempted; non-bot research tests show unrelated pre-existing failures and exceed 10 min — out of scope (bot-only scope above is green except the 3 intended).
No live orders, no artifacts/bot or .env touched; git read-only (no stash/commit).
