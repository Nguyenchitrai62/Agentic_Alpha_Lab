# oc_stresshist — PLAN (pre-registered before any computation)

## Task
REPORTING only (no decision rule, no variant selection): stress-window table for the
deployment configs R2B1D17BFG2 (v421_runs.pkl) and R2B1D17BF (v411_runs.pkl).

## Hypothesis (descriptive, not predictive)
The gross-cap G=2.0 (G2) costs little vs uncapped D17BF in calm years and trims the
left tail inside crash weeks; the table shows "what a bad week looks like" for both.

## Exact causal definitions (frozen)
- Mixed path: per shift s in 0..3 take run dict t/eq/eq_min, build hourly close `e1`
  and intrabar-min `m1` with v388.hourly on grid [2021-09-24 04:00, Y1+12h], hourly ffill
  (identical code path as research/diagnostics/r2_decompose5/reset_metric.py).
- Reset at anchors: for anchor year y (ANCH[y], +365 d) each phase is divided by its
  value at ANCH[y], then averaged 1/4 across phases -> yearly close `es_y` (=1.0 at
  anchor) and yearly min `ms_y`. Every window is scored on its anchor year's reset
  path ("what a user starting that year gets"). No market data is loaded; only the
  two frozen runs pkls (results of already-run simulations).
- Named windows (UTC, end-exclusive): 2021-12-04 -> [12-04,12-11); LUNA
  [2022-05-09,05-16); 3AC [2022-06-13,06-20); FTX [2022-11-07,11-15);
  2023-08-17 -> [08-17,08-24); 2024-01-03 -> [01-03,01-10);
  2024-03-05 -> [03-05,03-12); [2024-08-04,08-08); [2025-10-10,10-12).
- Worst 5 weeks per config: rolling 7 d net return ret7(t)=es(t)/es(t-7d)-1 on the
  reset-year path (hourly steps, lookbacks never cross an anchor); greedy 5 minima
  with >= 7 d separation (non-overlap). Computed separately for G2 and D17BF and
  reported as two lists (each window = exact [t-7d, t]); every window is scored
  under BOTH configs so the difference is like-for-like.
- Per window, per config: start = es at w0 (ffill); week_ret = es(w1-)/start - 1 (%);
  trough = min es on [w0,w1); t_trough = its first time; peak = max es on
  [anchor, t_trough]; dd = 1-trough/peak (drawdown from the prior peak, %);
  recover = days from t_trough to first es >= peak searching to year end, else null
  (not recovered within the year).
- Difference columns: trough_G2 - trough_BF (year-equity points), dd_G2 - dd_BF (pp,
  negative = G2 shallower), recover_G2 - recover_BF (days).

## Decision rule
Default PROMISING/LOOK rule does not apply (reporting task). Verdict line only
describes whether G2's crash weeks look no worse than D17BF's.

## Resources
One process, no 1m data, only two small pkls (4x10944 rows each) -> RAM << 1 GB.

## Outputs
scripts (compute_stress.py), results.json, REPORT.md (two plain tables + verdict).

## Post-hoc change log
- Worst weeks: first draft scored exact-duplicate union; replaced by two per-config
  lists (each window scored under both configs) after the first run showed two
  near-duplicate July-2024 windows and a date-truncation misalignment. Window
  definition itself (exact [t-7d, t]) unchanged in spirit, now exact to the hour.
- Added week_ret (window net %) to score_window; fixed tz-aware Timestamp handling.
