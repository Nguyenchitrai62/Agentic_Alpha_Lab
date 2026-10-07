# oc_idea1 PLAN (pre-registered BEFORE any outcome statistic, 2026-10-05)

Implements idea #1 of research/tournament/oc_ideas/IDEAS.md EXACTLY as described
there ("Late-fill fast-TP"). This PLAN is written before any outcome is computed.

## Hypothesis

Late dip-rung fills (fill minute f >= 209, the last 30 fillable minutes of the
16..238 window) underperform early fills by 10-39 bps yet stay positive on
average (oc_filltime): they arrive into tired moves with little time left to
reach TP 1.0 sigma before the bar-end timeout, so they time out more often. A
faster take-profit (0.5 sigma) on late fills harvests what is there instead of
timing out, raising the yearly rung sums at 1/(1+n) weights without worsening
the worst day. Early fills keep TP 1.0 sigma (keeps upside). This is the
un-tested TP x lateness interaction cell: oc_tpbyn tested TP 1.5 on flush
count n (rejected 3/5); oc_dipexit tested unconditional exits incl. split-TP
(0/5) and TP1+120min (1/5); oc_filltime documented the LATE drag but never
tested a conditional TP.

## Universe, data, years (fixed)

- Rows: `research/tournament/ext/fills_U_ext.parquet`, majors only
  (BTCUSDT/ETHUSDT/SOLUSDT/BNBUSDT/XRPUSDT) x R2 rungs (`x1` in
  {2.5, 3.0, 3.5, 4.0, 5.0}). `T = t_fill - f minutes` (4h bar open, standard
  grid). No new data; no 1m read in this task.
- `n` = `n25` per rung REUSED from
  `research/tournament/oc_b1shape/fills_n.parquet` (detections among the 4 OTHER
  majors with `close(f-1) <= O(T)*(1-2.5*sigma(T))`, per oc_b1shape PLAN exact
  definitions). Join fills_U_ext to fills_n on (sym, Tbar=Bx, t_fill, f, k);
  inner join; assert y1.0 matches to 1e-12; drop rows with missing n (report
  count). `n` is used ONLY for the rung weights, never for the TP decision.
- Years: 5 walk-forward years Y0..Y4 = [anchor, anchor+365d) for anchors
  2021-09-24 .. 2025-09-24, keyed by `T`. Rows outside ignored.
- Outcomes per row: `y0.5 / y1.0` = exact net returns at TP 0.5/1.0 sigma
  (fees/funding included, stops/timeout unchanged v293 replica) from
  fills_U_ext. `y1.5` reported only in the descriptive late-vs-early bucket
  table for context (not scored).
- Market data up to 2026-09-24 00:00 UTC per assignment (all 5 years are
  research data; any PROMISING rule needs prospective validation before real
  money). Disclosed vs RULES.md hidden-year convention.

## Exact causal definition (frozen, one variant only)

- At the fill minute `f` (known exactly at the fill, bot-executable):
  TP = 0.5 sigma if f >= 209 else 1.0 sigma. Threshold 209 = first offset of
  the last 30 fillable minutes of the 16..238 window (fixed from oc_filltime,
  no fitting here). Stops (close5 4-sigma, 8-sigma backstop), timeout at the
  next 4h open, fees/funding unchanged by construction (exact y0.5/y1.0
  counterfactuals from the same engine).
- Base A `always1.0`: row outcome `yA = y1.0`.
- Cond B `tp05_if_late`: row outcome `yB = y0.5 if f >= 209 else y1.0`.
- At most 1 tested variant (this B vs A). No threshold search, no n interaction.

## Statistics (fixed, no fitting)

1. Descriptive bucket table: per year x fill-timing bucket (early f < 209,
   late f >= 209): count, share, mean y0.5, mean y1.0, mean(y0.5 - y1.0)
   (unweighted rung means), win rate (net > 0) under y1.0, plus overall row.
2. Rule test (equal exposure, same engine as oc_tpbyn):
   - Size `w = 1/(1+n)` for both rules (n = reused n25); per year rescale to
     mean 1 (`w' = w / mean(w over that year)`), yearly sum `S = sum(w'*y_rule)`;
     daily sums group `w'*y_rule` by `T.floor('D')` (UTC).
   - Report per rule: yearly S, per-year worst-day, overall worst-day
     (min over all days), full-path maxDD of cumulative daily sum
     (5 years concatenated chronologically; `maxDD = min(cumsum-running_max)`).
   - Effect `D = S_B - S_A` per year; LOO `D_{-i} = mean(D over years != i)`.
   - Also report late-share (fraction of fills with f >= 209) and changed-share
     per year for context.

## Decision rule (fixed, assignment default + IDEAS.md worst-day bar)

- PROMISING only if ALL three hold:
  (a) D > 0 in >= 4 of 5 anchor years, AND
  (b) leave-one-year-out D_{-i} > 0 in >= 4 of 5 cases, AND
  (c) yearly worst-day of B not worse than yearly worst-day of A
      (B_worst >= A_worst, tolerance 0) in >= 4 of 5 years.
- (a)+(b) = the assignment default decision rule; (c) = the extra worst-day
  bar required for sizing/filter ideas and pre-registered in IDEAS.md idea #1
  ("worst-day not worse in >= 4/5 years").
- One-line verdict in REPORT.md (`PROMISING` / `NOT PROMISING`).

## Protocol / resources (fixed)

- PLAN.md written before any outcome computation. One process, small frames
  only (no 1m data; reuse fills_n.parquet), RAM < 1 GB.
- No commits; write ONLY under `research/tournament/oc_idea1/`
  (+ `tests/test_oc_idea1.py`).
- Scripts: `analyze_idea1.py` (join + bucket table + rule test -> results.json);
  outputs `results.json`, `REPORT.md` (tables + one-line verdict).
