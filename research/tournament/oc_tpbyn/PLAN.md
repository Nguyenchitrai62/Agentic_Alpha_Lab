# oc_tpbyn PLAN (pre-registered BEFORE any outcome statistic, 2026-10-05)

## Hypothesis
When a majors dip rung fills while the rest of the majors board is also
limit-down (market-flush count n >= 2), the bounce is larger / more
persistent, so a wider take-profit (1.5 sigma_4h) beats the deployed
1.0-sigma TP on those fills; when n < 2 the deployed 1.0-sigma TP is kept.
Test: conditional rule TP = 1.5 sigma if n >= 2 else 1.0 vs always 1.0.

## Universe, n reuse, years (fixed)
- Rows: `research/tournament/ext/fills_U_ext.parquet`, majors
  (BTC/ETH/SOL/BNB/XRP) R2 rungs only (`x1` in {2.5,3.0,3.5,4.0,5.0}).
  `T = t_fill - f minutes` (4h bar open, standard grid).
- `n` = `n25` per rung REUSED from `research/tournament/oc_b1shape/fills_n.parquet`
  (no 1m read in this task): detections among the 4 OTHER majors with
  `close_c(f-1) <= O_c(T)*(1-2.5*sigma_c(T))`, sigma = trailing-360 4h
  open-to-open std (min 120), per oc_b1shape PLAN exact definitions.
  Join fills_U_ext to fills_n on (sym, Tbar=Bx, t_fill, f, k); inner join;
  assert y1.0 matches to 1e-12; drop rows with missing n (report count).
- Years: 5 walk-forward years Y0..Y4 = [anchor, anchor+365d) for anchors
  2021-09-24 .. 2025-09-24, keyed by `T`. Rows outside ignored.
- Outcomes per row: `y0.5 / y1.0 / y1.5` = exact net returns at TP
  0.5/1.0/1.5 sigma (fees/funding included) from fills_U_ext.
- Market data up to 2026-09-24 00:00 UTC per assignment (all 5 years are
  research data; any PROMISING rule needs prospective validation before
  real money). Disclosed vs RULES.md hidden-year convention.

## Statistics (fixed, no fitting)
1. Bucket table: per year x n-bucket (0, 1, 2+ where 2+ = n in {2,3,4}):
   count, mean y0.5, mean y1.0, mean y1.5 (unweighted rung means), plus
   overall row. Also report the per-bucket mean(y1.5 - y1.0) sign per year.
2. Rule test (equal exposure, sizes as deployed v399):
   - Base A `always1.0`: row outcome `yA = y1.0`.
   - Cond B `tp15_if_n2`: row outcome `yB = y1.5 if n >= 2 else y1.0`.
   - Size `w = 1/(1+n)` for both rules; per year rescale to mean 1
     (`w' = w / mean(w over that year)`), yearly sum `S = sum(w'*y_rule)`;
     daily sums group `w'*y_rule` by `T.floor('D')` (UTC).
   - Report per rule: yearly S, per-year worst-day, overall worst-day
     (min over all days), full-path maxDD of cumulative daily sum
     (5 years concatenated chronologically; `maxDD = min(cumsum-running_max)`).
   - Effect `D = S_B - S_A` per year; LOO `D_{-i} = mean(D over years != i)`.

## Decision rule (fixed, assignment default)
- PROMISING only if D > 0 (same positive sign) in >= 4 of 5 anchor years
  AND leave-one-year-out D_{-i} > 0 in >= 4 of 5 cases.
- Tails (worst day / maxDD) are reported for context only and do not gate
  the verdict (unlike oc_b1shape); any tail deterioration is disclosed.
- One-line verdict in REPORT.md (`PROMISING` / `NOT PROMISING`).

## Protocol / resources (fixed)
- PLAN.md written before any outcome computation. One process, small frames
  only (no 1m data; reuse fills_n.parquet), RAM < 1 GB.
- No commits; write ONLY under `research/tournament/oc_tpbyn/`
  (+ `tests/test_oc_tpbyn.py`).
- Scripts: `analyze_tpbyn.py` (join + bucket table + rule test -> results.json);
  outputs `results.json`, `REPORT.md` (tables + one-line verdict).
