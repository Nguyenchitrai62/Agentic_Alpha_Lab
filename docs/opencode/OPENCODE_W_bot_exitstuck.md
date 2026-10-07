# OpenCode task bot_exitstuck - time-exit market orders re-sent for hours without filling (soak) / for 30 min (paper): root cause + fix
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. You MAY edit `bot/run.py`, `bot/paper.py` and `tests/soak_bot.py` (minimal diffs, every
change covered by a new test in `tests/test_bot_exitstuck.py`); write `research/diagnostics/bot_exitstuck/` and `docs/opencode/BOT_EXITSTUCK_20261008.md`.
Never touch artifacts/bot/* or running processes (8 paper runners use the code on disk only at restart). Mock / paper only. Print progress every 10 minutes.
RAM is tight on this host: run one soak at a time via scripts/heavy_slot.py.

## Evidence (leader)
1. 24 h replay soak with the current code (research/diagnostics/bot_soak24/, worker died before analysing; its run scripts are in tmp/):
   soak_flush_base/soak_result_soak24base.json has 3532 `exit_completion` violations (exit_resend_overflow) - pieces d0..d3ETH25hgr50
   (qty 0.11 each): entry filled 15:31, TP + SL placed, at the 19:00 time exit the bot sends a reduceOnly Market sell, then every 2 minutes
   cancels the previous X-link and re-sends a new one; NONE fills until the window ends (5 h). Same in soak_flush_k2. Actions log:
   soak_flush_base/artifacts/bot/testnet_soak24base/actions.jsonl (grep d0ETH25hgr50).
   Also: the same piece logs `dust_skip ... entry_protection_below_minimum` every cycle although its 0.11 TP / SL were placed (ETH min qty 0.01).
2. Live paper runner artifacts/bot/paper_d17bfg2/actions.jsonl (read-only): piece d3SOL25hrwmc time exit at 2026-10-07 03:00, runner was dead
   03:24-07:00, after restart market_exit re-sent every ~2 min from 07:03 to 07:31, filled 07:33 (27 sends). 18-20 pieces per runner have > 2 sends.

## Tasks
1. Root cause (code-cited): why the mock / paper exchange does not fill these reduceOnly market exits (position size vs total reduce-only qty of
   the 4 pieces? cancel-before-fill livelock of the resend loop? kline / fill timing in the mock or bot/paper.py? hedge-mode positionIdx?) and why
   the dust_skip message fires for a 0.11 ETH piece. Build a minimal deterministic reproduction (test) first.
2. Fix with the smallest diff that is also correct on the REAL exchange (Bybit V5 semantics: a market order fills immediately or is rejected;
   never cancel a market exit that may already be filled - check the order status / position before re-sending). Keep the exit-completion
   invariant, exit-cancel fix (cb14cb7) and dust fix (b5f12b0) behaviour; all existing bot tests must pass.
3. Re-run the 2025-10-10 flush soak (deployment flags, as bot_soak24's tmp/run_flush_base.py) and one calm-day 24 h soak (pick a low-vol 2025 day):
   report every invariant count, fills / exits, runtime vs the previous soaks.
4. BOT_EXITSTUCK_20261008.md (<= 40 lines): cause, fix, soak numbers, GO / NO-GO for testnet; what the paper runners need (restart after the fix).
Vietnamese 3-line summary.
