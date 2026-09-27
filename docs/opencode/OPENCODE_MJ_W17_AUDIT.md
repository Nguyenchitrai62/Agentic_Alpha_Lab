# mj W17: blind audit of the majors TSMOM portfolio (read OPENCODE_VF_COMMON.md first)
Reproduce ONE number from this text before reading the leader's code. Do NOT open
`scripts/mj_tsmom_portfolio.py`, `scripts/mj_lab.py`, `research/mj_portfolio_risk.py` or
`artifacts/research/mj/` until A is saved. Write only under `research/mj_audit/` and
`tests/test_mj_audit.py`.

Spec (Binance USD-M 4h bars; BTC from `data/raw/ma_ribbon_20260924/klines_4h.parquet` +
`klines_1d.parquet`; ETH/SOL/BNB/XRP from `data/raw/xs_universe_20260924/{SYM}_{4h,1d}.parquet`,
funding `{SYM}_funding.parquet`, BTC funding `data/raw/ma_ribbon_20260924/funding.parquet`):
- Align the five assets on the union of 4h open_time; a missing asset has weight 0.
- Signal per asset at 4h close t: mean of sign(log close_t - log close_{t-6*h}) for h in (7, 30)
  days; clip below at 0 (long-only). Set to 0 if the asset's last CLOSED daily bar has
  close < SMA50 < SMA200 (daily closes).
- raw_i = signal_i / vol_i, vol_i = std of the last 180 4h log returns * sqrt(6*365).
- Portfolio scale: port_r_t = sum_i raw_{i,t-1} * r_{i,t} (r = 4h log return); pvol = std of the
  last 180 port_r (min 60) * sqrt(6*365); scale = min(0.3 / pvol, 10); w = raw * scale; if
  sum|w| > 3 divide all weights so sum|w| = 3.
- Turnover band: keep the previous weight of an asset unless the new weight differs by > 0.05.
- Execution: weight decided at close t earns open_{t+2}/open_{t+1} - 1; cost 0.0002 * sum|w_t - w_{t-1}|;
  funding: w * funding rates summed within bar t+1; equity compounds.
- Window: bars with open_time in [2023-09-24, 2024-09-22 20:00 UTC], start flat.
A. Save `research/mj_audit/replication.json` with net %, max DD on 4h equity, turnover per day.
B. Then read the leader files and `artifacts/research/mj/tsmom_portfolio/*`, write
   `research/mj_audit/COMPARISON.md` (differences > 1 pp with root cause) and audit the
   leader code for look-ahead (signal, vol, portfolio scale, daily ribbon join, funding).
