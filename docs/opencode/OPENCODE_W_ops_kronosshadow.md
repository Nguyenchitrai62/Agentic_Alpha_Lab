# OpenCode task ops_kronosshadow - prospective Kronos feature log (4 clocks x 5 majors, every hour) for a later counterfactual of the K2 dip tilt
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. EXCEPTION (leader-assigned implementation): you may CREATE `scripts/kronos_shadow.py`,
`tests/test_kronos_shadow.py` and `docs/opencode/KRONOSSHADOW_20261007.md`. Read-only everywhere else; do not start the loop yourself (only
`--once --dry-run`); the leader starts it. Public Bybit / Binance market-data GETs only.

## Why
research/tournament/oc_kronoshidden/REPORT.md: the Kronos-small dip tilt K2 (rung size x1.25 in the favourable outer quintile of risk = -low1,
x0.75 in the unfavourable one; anchor-2025 fit: direction +1, q20 0.5872, q80 2.1828 - see fits.json) beat G2 and an exposure-matched control
by +0.15 %/month on the post-release year with lower DD. Not deployed (marginal). Cheapest clean evidence: log the features prospectively and
later re-weight the paper runners' real dip fills offline.

## Implement scripts/kronos_shadow.py
- Model and settings IDENTICAL to research/tournament/oc_kronoshidden (reuse its model/ folder and kronos_fast.py by import from that path;
  Kronos-small + Tokenizer-base, context 400 x 4h bars, pred_len 6, S = 64, T = 1.0, top_p 0.9, top_k 0, fp32; seed per (sym, shift, T) =
  hash-based so reruns are reproducible). GPU if available else CPU (state the CPU time per run).
- Each run (hourly; idempotent): for clock shift s = current UTC hour mod 4 ... more precisely, for every shift s whose 4h bar opened in the
  last hour (bar opens at s, s+4, ... UTC), build the 400 closed 4h bars of that shift for each of BTC/ETH/SOL/BNB/XRP from Bybit (or Binance)
  public 1m/60m klines (same OHLCV + quote volume convention as oc_kronoshidden/build_bars_4shift.py; document any venue difference), compute
  the 8 features + sigma + C0 for bar open T, and the K2 multiplier using the frozen anchor-2025 fit (fits.json). Append to
  `artifacts/research/kronos_shadow/kronos_features_live.parquet` (sym, shift, T, features, k2_mult, model_sha, logged_at); a row is
  PROSPECTIVE when logged_at - T <= 30 min.
- `--once`, `--dry-run`, `--backfill-hours N` (labelled backfill rows, never counted as prospective), robust to API errors (retry, log,
  exit 0), runtime print.
- Tests: bar building causality (bars closing <= T only), seed reproducibility on a fixed input, multiplier rule vs fits.json, idempotence.
- Doc (<= 30 lines): the leader's start command (a loop like the carry loop, every 10 minutes is fine since it is idempotent per bar) and the
  planned offline evaluation (after >= 8 weeks: join prospective rows to the G2 paper runners' dip fills by (sym, phase, bar) and compare
  sum(k2_mult x rung P&L) vs sum(rung P&L) at equal average exposure).
