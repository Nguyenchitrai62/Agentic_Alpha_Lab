# oc_oos12d — REPORT (tiny sample, clean)

Window 2026-09-24 00:00 .. 2026-10-06 00:00 UTC (12 days, genuinely new; research ends 2026-09-23).
Mode: **dip sleeve alone, rule-based** (books=0, no R2/G2 agent tables, no refit).
Why: frozen members end 2026-09-23; v240_O1 prospective rows are sparse+error-prone
from 09-28 and v285_CB is member-D only from 09-29, so the full G2 book
(0.8×O1+0.2×D) cannot be reconstructed honestly. No backfill rows used.
Engine: `engine_user.simulate`, 4 clock shifts, v321 dip rules + G2 overlays
(inv corr kd=1.7, budget 0.26×1.7, gross cap 2.0), gate costs
(maker 0.0002 / taker 0.00055 / long funding 0.0001 per settlement / shorts 0),
`win_start=5`, stop-first. 1m from Binance vision daily zips (CHECKSUM-verified,
`data/raw/majors_1m_oos_20261006/`, 17280 bars/symbol, gap-free).

## Result (4-phase mix, per reset-metric convention)
- Daily equity (start + 12 closes): 1.0 → 1.001872; total **+0.187%**.
- Max DD: close 0.149%, 1m-marked 0.149%, gate **0.149%**.
- Trades (pooled over 4 phase sub-accounts): **14 rung exits, 12 wins, win 85.7%**;
  book events 0 (by construction). Expect ~3.5 rungs per sub-account.
- Expectation band (10000 random 12-day windows, v421 G2 mixed daily):
  p5 −4.173%, p50 +1.028%, p95 +13.634%; OOS **percentile 37.8** (below median,
  inside the band). Median 12-day DD band p50 1.565% / p95 7.96% vs OOS 0.149%.
- verdict: inside the historical band on a tiny sample; **no gate claim**
  (12 days cannot pass/fail 5%/month). Full G2 (book+dip) remains unscored OOS.

## Reproduce
`.venv/Scripts/python.exe research/diagnostics/oc_oos12d/oc_oos12d.py --run`
(fetch: `--fetch`); `.venv/Scripts/python.exe -m pytest tests/test_oc_oos12d.py -q`.
