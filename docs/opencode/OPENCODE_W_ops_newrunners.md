# OpenCode task ops_newrunners - verify the new paper runners (C2, B7, B7xC2) behave exactly as researched (first hours of live data)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/diagnostics/ops_newrunners/` and `docs/opencode/NEWRUNNERS_20261008.md`.
artifacts/* READ-ONLY; never touch running processes. Print progress every 10 minutes.

## Runners (started 2026-10-08 ~04:52 UTC on bot fix 83a466a; 8 older runners restarted 04:50 UTC on the same code)
artifacts/bot/paper_d17bfg2ch (feed artifacts/research/chronos_shadow/chronos_features_live.parquet), paper_d17bfg2b7
(artifacts/research/cascade_shadow/b7_live.parquet), paper_d17bfg2b7c2 (b7c2_live.parquet); twin artifacts/bot/paper_d17bfg2.
## Checks (cite actions.jsonl lines)
1. Every dip rung placed by a tilted runner carries the multiplier of its (coin, phase, bar) from the feed (op k2_mult logged; recompute
   size_frac x mult vs the twin's rung size for the same rung id); rows missing in the feed -> 1.0 and op k2_missing.
2. B7 runners: during an active cascade window the rungs are x1.5 (or x1.5 x c2) and the dip gross cap 2.0 still binds (compare total dip
   gross vs equity); outside windows they equal the twin.
3. No exit_completion / protection / dust violations since the restart (op exit_wait counts, market_exit sends per piece <= 2, every open
   piece protected); compare with the pre-fix behaviour of 2026-10-07.
4. Data quality: feed rows lag (logged_at - T), prospective share, any stale_plan periods, runner cycle times.
NEWRUNNERS_20261008.md (<= 30 lines): PASS / issues with minimal reproductions; Vietnamese 3-line summary.
