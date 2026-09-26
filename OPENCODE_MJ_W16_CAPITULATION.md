# mj W16: capitulation / liquidation-cascade reversals on majors (read OPENCODE_VF_COMMON.md first)
Files: `src/agentic_alpha_lab/patterns/capitulation.py`, `tests/test_mj_capitulation.py`,
`research/mj/capitulation_study.py`, `artifacts/research/mj/capitulation/*`. Prefix `cap_`.
Assets: BTC, ETH, SOL, BNB, XRP. Timeframes 15m and 1h (fetch 15m/1h with
`fetch_klines` into data/raw/majors_intraday_20260924/{SYM}_{tf}.parquet if absent; BTC 1h in
data/raw/ma_ribbon_20260924, BTC 15m in data/raw/btc_intraday_20260924).
Definitions fixed before looking at results:
- flush bar: return < -3 x ATR14-based typical move or low below 20-bar low by > 1 ATR, with
  quote volume z-score > 3; lower wick >= 50% of range (recovery) vs no-wick (continuation).
- squeeze-up mirror for shorts.
- multi-asset cascade: >= 3 of 5 majors flush in the same bar.
- also the OI flush from `agentic_alpha_lab.patterns.positioning` for BTC as a cross-check.
events(): +1 after flush-with-wick (reversal hypothesis), -1 after flush-without-wick
(continuation), mirrored for up-squeezes; cascade versions.
Event study on each asset/timeframe via common.event_study (horizons 15m: 4/16/48/96;
1h: 1/4/12/24). Report n, bps, hit rate, stability, and whether effects exceed costs.
