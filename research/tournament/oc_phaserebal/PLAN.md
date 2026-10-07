# oc_phaserebal PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

## Hypothesis
R2B1D17BF (registry v411) runs four phase sub-accounts (shifts s=0..3) at 1/4
capital each, never rebalanced. Phase luck is large (oc_manualshallow: phase
equity-end ratios up to ~5x), so the never-rebalanced mix lets one lucky phase
dominate, raising drawdown. Periodically moving capital between sub-accounts
back to equal weight (zero cost: internal transfer inside one exchange account;
open positions are scaled, which a bot would do by resizing at the next order)
should cut max yearly DD without lowering the 5y return.

## Data (fixed here)
- Source of truth: research/parallel/rounds/parallel-20260906-r2/v411/v411_runs.pkl
  (shifts s=0..3, row R2B1D17BF only; each value is exactly {t, eq, eq_min} on
  the 4h-close grid, live 2021-09-24..2026-09-23). No other market data is read.
  No 1m data. No refit, no selection, no tuning.
- Helpers (read-only, never edited): v388 module
  (research/parallel/rounds/parallel-20260906-r2/v388/v388_bot_stop_distance.py:
  ANCH, Y1=2026-09-23, hourly(), mix(), year_stats()) and reset_metric module
  (research/diagnostics/r2_decompose5/reset_metric.py: year_reset()).
- Grid: g0 = 2021-09-24 04:00 UTC, g1 = Y1 + 12h = 2026-09-23 12:00 UTC, via
  v388.hourly() exactly (1h grid, ffill, fillna 1.0; eq_min indexed at t-4h,
  mn = min(lo, e)). Per-phase series: E_s(t), M_s(t), s=0..3.
- Anchors: A_y in {2021-09-24, 2022-09-24, 2023-09-24, 2024-09-24, 2025-09-24},
  year y = (A_y, A_y + 365d]. The last year is cut at g1 (~364.5d of data).
- All five years are research data (assignment overrides the old RULES.md
  hidden-year cut); findings need prospective validation.
- LIGHT: one process, RAM < 1 GB (only ~4 x 10944 floats + ~44k hourly rows).

## Arms (fixed; at most 2 variants)
- (a) NO-REBAL = the reset metric reproduced EXACTLY: per-year R/DD =
  reset_metric.year_reset(runs, "R2B1D17BF", y) for y=0..4 (imported, not
  reimplemented; its formula: per-phase segment E_s[seg]/b_s averaged over
  s=0..3, R = 100*(es_end**(1/12)-1), DD = 100*max(1-ms/pk(es)) with
  pk = running max of es, no prepended 1.0). Cross-check per-year (R, DD)
  against v411_result.json R2B1D17BF years to 1e-9.
- (b) MONTHLY: continuous rebalanced path from g0 with capital 1.0 split
  equally. Rebalance times T_k = each 1st of month 00:00 UTC from 2021-10-01
  to 2026-09-01 that falls on the hourly grid (plus start g0 and end g1 as
  interval boundaries; no trade at g1). At each T_k equalise holdings.
  Between rebalances: P(t) = P(T_{k-1}) * mean_s(E_s(t)/E_s(T_{k-1})),
  M(t) = P(T_{k-1}) * mean_s(M_s(t)/E_s(T_{k-1})), evaluated on the hourly
  grid with T values snapped to the last grid point <= T. Zero transfer cost.
- (c) WEEKLY: identical mechanics with T_k = every Monday 00:00 UTC from
  2021-09-27 to 2026-09-21 (ISO week start, UTC) plus g0/g1 boundaries.
- Rebalanced close series E_port(t) and mark series M_port(t) are built per
  arm on the full hourly grid, then sliced per anchor year.

## Metrics (fixed)
- Per anchor year y for arms (b)/(c): slice E_port/M_port to
  seg_y = (A_y, A_y+365d], b = value at last grid point <= A_y (== 1.0-awareness
  for y=0 via the g0 start), es = E_port[seg]/b, ms = M_port[seg]/b,
  R_y = 100*(es.iloc[-1]**(1/12)-1), DD_y = 100*max(1-ms/pk(es)) with the SAME
  pk convention as year_reset (running max of es, no prepend) so the
  "not worse" comparison is apples-to-apples.
- 5y return per arm: geo mean of the five yearly monthlies,
  R5 = 100*(prod_y(1+R_y/100)**(1/5)-1). Max yearly DD = max_y DD_y.
- Full-path DD per arm over (g0, g1]: DD_4h = 100*max(1-E/PK(E)),
  DD_1m = 100*max(1-M/PK(E)), gate = max(both); for (a) the full-path series
  is the continuous never-rebalanced mix e,mn = v388.mix(runs,"R2B1D17BF",g1)
  (== v411 full_path_dd method), for (b)/(c) the rebalanced E_port/M_port.
- Report per arm: per-year R_y, per-year DD_y, R5, max yearly DD, full-path
  DD_4h/DD_1m/gate. No other metrics. No win rates (pkl has no trades).

## Decision rule (fixed; BOTH must hold; applied separately to (b) and (c) vs (a))
- SPECIFIC (assignment): candidate PROMISING only if (i) its per-year 1m DD is
  not worse than (a) in >= 4/5 anchor years, i.e. DD_cand,y <= DD_a,y + 0.005pp
  (0.005pp tolerance = float/grid noise) in >= 4 years, AND (ii) its 5y return
  is not lower, i.e. R5_cand >= R5_a - 0.0005pp.
- DEFAULT (tournament): effect d_y = DD_a,y - DD_cand,y (positive = DD cut).
  PROMISING only if d_y >= -0.005pp (same sign = non-negative) in >= 4/5 years
  AND the leave-one-year-out check holds in >= 4/5 cases, i.e. for each left-out
  year j, mean{d_y : y != j} >= -0.005pp in >= 4 of the 5 LOYO folds. The LOYO
  check is on the DD effect; the return leg is covered by SPECIFIC (ii) plus a
  reported LOYO on the return gap g_y = R_cand,y - R_a,y (mean{g: y != j} >=
  -0.0005pp reported, not gating).
- Otherwise the verdict is NOT PROMISING. One-line verdict in REPORT.md.
- No selection on the most-recent year alone; all five years count symmetrically
  here because the assignment defines the rule on all five anchor years.

## Outputs (fixed)
- research/tournament/oc_phaserebal/compute_rebalance.py (single script, one
  process), results.json (arms a/b/c: per-year R/DD, R5, max yearly DD,
  full-path DDs, rebalance calendars, checks, decision flags), REPORT.md
  (tables + one-line verdict), test tests/test_oc_phaserebal.py.
- Checks in results.json: pkl keys == {t,eq,eq_min}; arm (a) matches
  v411_result.json years exactly; rebalance counts (monthly 60, weekly 261);
  hourly grid cover; zero-cost transfer log (counts only).
