# mj W15: relative value between majors (read OPENCODE_VF_COMMON.md first)
Files: `src/agentic_alpha_lab/patterns/pairs.py`, `tests/test_mj_pairs.py`, `research/mj/pairs_study.py`,
`artifacts/research/mj/pairs/*`. Prefix `pr_`.
Assets: BTC (data/raw/ma_ribbon_20260924 via common.load_bars), ETH, SOL, BNB, XRP
(data/raw/xasset_20260924/{SYM}_{4h,1d}.parquet). Pairs: ETH/BTC, SOL/BTC, SOL/ETH, BNB/BTC, XRP/BTC.
For each pair ratio R = close_A / close_B (as-of aligned on close_time):
compute(): log-ratio z-score vs 20/60/120 bars, ratio EMA20/EMA100 trend state and distance,
rolling hedge beta (60-bar OLS of A returns on B returns), residual (A - beta*B) cumulative
z-score, ratio realized vol, correlation 60 bars.
events(): mean-reversion hypotheses (z < -2 -> +1 long A/short B; z > 2 -> -1) and trend
hypotheses (ratio breaks 55-bar high -> +1, low -> -1), residual z extremes.
Study: evaluate the SPREAD return (A minus beta*B, beta as of decision) with a custom
event study that mirrors common.event_study (next-open entry, horizons 1/3/6/12 on 4h and
1/3/7/14 on 1d, NW t, BH-FDR, half stability, decisions < 2025-09-14). Report which pairs /
hypotheses survive and effect size vs ~8-16 bps round-trip for two legs.
