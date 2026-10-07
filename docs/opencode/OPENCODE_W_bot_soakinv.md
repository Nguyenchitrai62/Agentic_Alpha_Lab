# OpenCode task bot_soakinv - exit-completion invariant in the 24h bot soak (proposal P2 of BOT_EXITSOAK_20261007)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. EXCEPTION to the common write scope (leader-assigned): you may edit
`tests/soak_bot.py` and write `tests/test_bot_soakinv.py` and `docs/opencode/BOT_SOAKINV_20261007.md`. bot/ stays READ-ONLY; never touch
artifacts/bot/* or running processes; paper / mock only.

## Why
docs/opencode/BOT_EXITSOAK_20261007.md: the 24h soak (tests/soak_bot.py, check_invariants) exempts every piece whose exit_sent is < 2 min old,
and the exit-cancel bug (fixed in cb14cb7) re-sent the exit every 2 min, so an exiting piece was perpetually exempt while its stop / TP were
cancelled. No assertion on exit COMPLETION exists.

## Implement
1. In `check_invariants` (or a new invariant called from the same place): track market_exit sends per piece (from the runner's action log or
   state); flag a VIOLATION when a piece has qty > 0, its first market_exit for the current exit attempt is older than 3 x
   mirror.EXIT_INFLIGHT_MIN, and its exit link is neither resting on the exchange nor filled (exactly the bug's signature), and also when the
   same piece accumulates more than 3 market_exit sends without a fill. Count violations in the soak summary like the existing ones.
2. Prove it: with the current bot/ the soak (use its shortest configuration that produces at least one time exit and one close5 stop - read
   tests/test_bot_soak_smoke.py and tests/soak_bot.py; if no existing window produces them, add a window that does, e.g. a slice around the
   2025-10-10 flush that crosses a 4h boundary) reports 0 violations; with the pre-fix module (copy `git show HEAD~2:bot/run.py`, i.e. before
   cb14cb7 - check with `git log --oneline -3 -- bot/run.py` - into tests' tmp scratch under research/diagnostics/bot_soakinv/tmp/, never into
   bot/) the new invariant fires. Put the fast part (<= 2 min runtime) in tests/test_bot_soakinv.py; the long run is a manual command
   documented in the doc.
3. Run `.venv/Scripts/python.exe -m pytest tests -q -k "bot"`; everything must pass. Write the doc (<= 40 lines): what the invariant checks,
   with / without fix counts, runtime.
