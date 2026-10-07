# OpenCode task bot_soak24 - full 24 h replay soak of the CURRENT bot code (exit fix, dust fix, paper mark fix, K2 flag) before testnet
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/diagnostics/bot_soak24/` and `docs/opencode/BOT_SOAK24_20261008.md`.
bot/ READ-ONLY; never touch artifacts/bot/* or running processes; mock / paper only.

## Tasks
1. Read tests/soak_bot.py (now with the exit-completion invariant, docs/opencode/BOT_SOAKINV_20261007.md) and the previous soak reports
   (docs/opencode/BOT_SOAK_20261006.md, BOT_SOAKFIX_20261006.md, BOT_EXITSOAK_20261007.md).
2. Run the 24 h soak on the 2025-10-10 flush day with the deployment flags (G2 + carry: --corr-size --dip-mult 1.7 --dip-gross-cap 2.0
   --bear-book --adopt-fresh --carry-f 0.25) and again with --k2-tilt pointing at a synthetic K2 parquet you create in your folder
   (multipliers 0.75 / 1.0 / 1.25 for the soak bars). Also one calm-day 24 h soak (pick a 2025 day with low volatility).
3. Report every invariant count (protection gaps, qty mismatches, exit_stuck / resend overflow, dust, cycle exceptions, carry hedge gaps),
   fills / exits, runtime; compare with the previous soak numbers. Any violation -> minimal reproduction + proposed diff (do not edit bot/).
Doc (<= 40 lines): GO / NO-GO for testnet with the current code.
