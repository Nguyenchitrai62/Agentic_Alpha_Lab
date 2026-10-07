# oc_rolling17 PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

## Hypothesis / task
REPORTING task only (no rule, no PROMISING verdict). Quantify how stable the
deployed BOT rows are across start dates: for R2B1D17BF (primary; v411:
dips x1.7 inv-rule, budget 0.26x1.7, bear-book filter longs x0.5) and for
R2B1D16 (reference, present in the same v411_runs.pkl) — plus R2-4P only if it
is present in v411_runs.pkl or v406_runs.pkl — evaluate EVERY rolling 12-month
window starting on the 24th of each month from 2021-09-24 to 2025-09-24
(49 windows), with the four phase sub-accounts reset to 1/4 at each window
start exactly like reset_metric.year_reset.

## Exact causal / metric definitions (fixed before running)
- Inputs (read-only, never edited): research/parallel/rounds/parallel-20260906-r2/v411/v411_runs.pkl
  (shifts s=0..3, strats R2B1D17BF + R2B1D16), v411_result.json (expected rows),
  research/parallel/rounds/parallel-20260906-r2/v406/v406_runs.pkl (presence check only),
  research/diagnostics/r2_decompose5/reset_metric.py (year_reset),
  v388_bot_stop_distance.hourly/mix (grid + conservative intrabar logic).
- Hourly grid (verbatim copy of v388.hourly): for run r, t = to_datetime(r["t"], utc=True);
  grid = date_range("2021-09-24 04:00" UTC, g1, freq="1h") with g1 = Y1+12h =
  2026-09-23 12:00 UTC (v388.Y1); e = Series(eq,index=t).reindex(grid,ffill).fillna(1.0);
  lo = Series(eq_min,index=t-4h).reindex(grid,ffill).fillna(1.0); m = minimum(lo,e).
- year_reset replica: for anchor a0 (midnight UTC), per shift s: b = e1[e1.index<=a0].iloc[-1]
  (or 1.0 if none); seg = (index>a0)&(index<=a0+365d); E_s = e1[seg]/b, MN_s = m1[seg]/b;
  es = mean(E_s), ms = mean(MN_s); pk = maximum.accumulate(es);
  R = 100*(es.iloc[-1]**(1/12)-1) (monthly geometric % over the 365d window);
  DD = 100*max(1-ms/pk) (conservative intrabar, 1m-marked low vs 4h-close peak);
  losing = 1 iff R < 0 (equivalently window net < 0).
- Generalisation: window_reset(runs,strat,a0) is the SAME code with a0 any midnight-UTC
  Timestamp (not just the five ANCH dates). No other change (same grid, same b/seg/es/ms/pk).
- Windows: a0 = 24th of each month, 2021-09-24 .. 2025-09-24 inclusive = 49 starts
  (Sep-21 + Oct-21..Aug-25 monthly + Sep-25). Window end = a0+365d on the same hourly grid
  (clipped by g1 for the last windows, exactly as year_reset does for y=4).
- Reproduction proof (gate before reporting): for the five standard anchors
  2021-09-24..2025-09-24, window_reset must match reset_metric.year_reset R to <=1e-3
  and DD to <=1e-3 for both R2B1D17BF and R2B1D16, and match v411_result.json
  years rows to <=1e-3 (rounding: R 3dp, DD 2dp as stored).
- Per window outputs: start (YYYY-MM-DD), R (monthly geo %, 3dp), DD (conservative %, 2dp),
  losing (0/1), end_eq (es.iloc[-1] ratio, 6dp for audit).
- Summaries per strat: distribution over the 49 windows of R and of DD:
  min / p10 / median / p90 / max (linear interpolation, numpy default), share R>=5 (%),
  share DD<15 (%), share DD<20 (%), count losing windows, worst-window dates
  (lowest R; highest DD; ties -> earliest). Plus the five standard-anchor rows for reference.

## Decision / verdict rule
REPORTING task: no selection rule, no PROMISING claim. Default tournament
PROMISING rule is NOT applied. One-line verdict names the stability pattern only
(share >=5%, DD shares, worst dates). Findings need prospective validation; all five
years are research data per the assignment (market data read only to 2026-09-24 00:00 UTC
via the cached runs; no 1m data loaded).

## Resources / constraints
- LIGHT job: one process, RAM < 1 GB (runs pkl ~4 MB + hourly grid ~150k rows x 8 series),
  no 1m data, no simulation, no refit. Read-only outside
  research/tournament/oc_rolling17/ (+ tests/test_oc_rolling17.py). No commits.
- Outputs: run_rolling17.py, results.json, REPORT.md, tests/test_oc_rolling17.py.
  Test asserts: 49 windows, repro to 1e-3 on five anchors vs year_reset and vs
  v411_result.json, window metric invariants (DD>=0, losing==(R<0), sorted starts).
