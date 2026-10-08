# OpenCode task oc_oos2w - replay the frozen candidates on the POST-FREEZE data (2026-09-24 .. latest), the only truly unseen period
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/diagnostics/oc_oos2w/` and `tests/test_oc_oos2w.py`.
Print progress every 10 minutes. Public market-data GETs only (Binance / Bybit klines, funding). Heavy work via heavy_slot.

## Why
Every research number stops at 2026-09-23. research/diagnostics/oc_bookoos and oc_oos12d already score the deployed book on the weeks after
(data/raw/majors_1m_oos_20261006 + score_oos.py --fetch / --run, read them). The candidates C2, B7 and B7xC2 have frozen rules and live feeds;
replaying them on the post-freeze window is clean out-of-sample evidence (short, but untouched by any choice).
## Task
1. Extend the OOS 1m data through the latest fully closed day with the existing fetch path (do not change its logic; record the window).
2. Replay on that window with the frozen engine rules (4 clocks, gate costs): G2 (R2B1D17BFG2 with its frozen 2025 models / the plan history
   the OOS scorer uses - say which), G2 + C2 (multipliers from the frozen anchor-2026 fit, research/tournament/bot_c2shadow/fit_2026.json, on
   Chronos features computed for the window with the pinned model - reuse scripts/chronos_shadow.py backfill), G2 + B7 (cascade flags from
   scripts/cascade_shadow.py backfill), G2 + B7xC2; on Binance AND Bybit prices.
3. Report per row: return, DD (4h close and 1m marked), number of dip / book fills, TP / stop / time exits, and the per-day equity; compare
   with the live paper runners over the overlapping days (artifacts/bot/paper_d17bfg2*, read-only) as a sanity check.
Be explicit that ~2 weeks is far too short for a verdict: report it as an evidence log entry, not a selection. Vietnamese 3-line summary.
