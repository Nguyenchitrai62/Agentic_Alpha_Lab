# v21 nested validation TCN — completed 2026-09-06

## Scope and provenance

The private Kaggle kernel `nguynchtrai/btc-swing-v21-val-20260906` completed
with 2×Tesla T4, worker exit codes `[0, 0]`, and all 33 seed/fold final
refits plus nested-selection artifacts present. The local GTX1650 replay audit
passed all 33 forecasts and policy parity checks; maximum replay error was
`2.86102294921875e-06` under the registered `rtol=atol=0.001` audit gate.

This is opened development history, not an independent test or live approval.
The continuous evaluator used one global cooldown, monthly cap, position and
compounded-equity state from 2023-06-01 through the 2026-03-23 maturity cutoff
(2.809092589 years; 4,076 decisions). Signals were formed after closed candles;
entries began on the next candle. Baseline exposure is 1x; 0.5x is a separate
risk comparator, not a rescue strategy.

## Continuous portfolio results

Normal cost is 0.02% per fill with long funding 0.01% every 8 hours and short
funding zero. Fee stress uses 0.055% per fill. Execution stress adds 5 bps
entry/target penetration, 5 bps market-exit slippage and 0.055% market-exit
fee. Drawdown is OHLC close-sampled; execution stress is not a queue or mark
price model.

| Branch / exposure | Scenario | Final equity | Gross PnL | Fees | Funding | Net return | DD | Fills | Monthly geometric |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| mean / 1x | normal | 66.316 | -32.147 | 0.664 | 0.873 | -33.684% | 40.33% | 22 | -1.211% |
| mean / 1x | fee stress | 65.278 | -32.045 | 1.812 | 0.864 | -34.722% | 41.14% | 22 | -1.257% |
| mean / 1x | execution stress | 61.016 | -37.247 | 0.978 | 0.758 | -38.984% | 46.04% | 19 | -1.455% |
| mean−std / 0.5x | normal | 85.417 | -14.020 | 0.186 | 0.377 | -14.583% | 14.84% | 10 | -0.467% |
| mean−std / 0.5x | fee stress | 85.119 | -13.994 | 0.511 | 0.377 | -14.881% | 15.12% | 10 | -0.477% |
| mean−std / 0.5x | execution stress | 85.075 | -14.212 | 0.337 | 0.377 | -14.925% | 15.18% | 10 | -0.478% |

The other registered branch, mean−std / 1x, ended at 72.560 normal equity
(`-27.440%`, DD `27.87%`, 10 fills). No branch reaches 5% monthly net, 30
fills, or the combined stress acceptance gate. The lower-DD 0.5x branch still
has negative net PnL and is not a candidate.

## Forecast diagnosis

The v21 ensemble mean had unconditional payoff MSE `8.4876` versus the
past-mature candidate-constant control `8.3653`, fill Brier `0.2133` versus
`0.1956`, and within-decision action-rank correlation `0.0261` versus `0.0013`.
High-score buckets were not reliable: the fixed `0.3–1.0%` bucket had observed
mean net `-0.5114%`, and the `1–2%` bucket had `-2.8462%`. This supports a new
registered ranking-loss/capacity hypothesis; it does not justify changing
thresholds or reversing v21 signals.

## Reproduction identity

- Plan: `configs/swing_v21_tcn_validation.json`
- Cloud export: `artifacts/kaggle/v21_download/tcn-training`
- Replay audit: `artifacts/research/v21_local_audit/audit.json`
- Continuous report: `artifacts/research/v21_local_portfolio/continuous/summary.json`
- Dataset manifest SHA-256: `a1ab4c5f7564bd58ac3daa7479685d16eff4b85fd027a8d5f56e82093056c381`
- Sequence-cache manifest SHA-256: `e3c08b4875d8848a6bd1681f1d1d9679a6d9d4d1f05d347eaa2492046a1fadba`
- Audit SHA-256: `a5f2dbab72060587ba7f2af1dfaffd0edb56b9831b1c1bbfaf952956706b0977`
- Source snapshot before v22 changes: Git `513dd4a920bc6ae84eb8cdb6d124dd36b56d2154`

The audit and portfolio explicitly record `independent_test=false` and
`live_approved=false`. v22 is a separately registered development experiment;
its package and hashes are recorded in the v22 config/package manifest.
