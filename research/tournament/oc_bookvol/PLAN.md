# oc_bookvol — PLAN (pre-registered BEFORE any outcome is computed)

## Hypothesis

The deployed book-level volatility target (0.25 / trailing 60-day realised vol
of the book P&L, cap 2) is one of several defensible scalings. Three fixed
alternatives are tested against it on the SAME vectorised book P&L:
(a) per-coin 30-day realised vol (risk-parity tilt across coins),
(b) a slower 120-day book-level window,
(c) a 60-day downside-semivariance target.
A variant is PROMISING only if it improves BOTH Sharpe and max drawdown with
the pre-registered sign-consistency rule below.

## Inputs (read-only, never edited)

- Books: rebuilt EXACTLY as `scripts/forward_v205.py::research_books_d2`
  (`o1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2`, `d2 = 0.8*o1 + 0.2*(D+Dq)/2`,
  union index, missing -> 0.0) from `artifacts/research/engine_real/`.
- Opens: `artifacts/research/engine_real/opens_v154.parquet` (4h opens).
- Symbols: BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides the
  old tournament-harness dev cutoff; all five years are research data,
  findings still need prospective validation).
- No 1m data, one process, RAM << 1 GB (two small 4h frames only).

## Exact causal definitions (fixed now)

- Grid: inner join of books index with opens index (dropna all), sorted 4h
  grid. Weight `w_c[t]` is known at the close of bar `t`.
- Next-bar simple return: `r_c[t] = open_c[t+1]/open_c[t] - 1`. The last grid
  bar has no forward return and is dropped. Same timing as oc_bookic.
- Unscaled book P&L: `u[t] = sum_c w_c[t]*r_c[t]` (gross, no costs).
- Scales `s[t]` / tilts use ONLY bars strictly before `t` (windows ending at
  `t-1`; every input `w[s], open[s], open[s+1]` for `s <= t-1` is known at the
  close of `t-1`, hence at the close of `t`). Window `[t-W, t-1]`.
- Turnover (L1, undrifted — disclosed simplification, no position drift):
  `TO[t] = sum_c |ws_c[t] - ws_c[t-1]|`, first grid bar vs flat 0.
  Cost `0.0005 * TO[t]` (0.05% per unit turnover, as assigned).
- Variant net: `pn[t] = sum_c ws_c[t]*r_c[t] - 0.0005*TO[t]`.
- Equity: `eq` compounded from 1.0 at the grid start,
  `eq[t+1] = eq[t]*(1+pn[t])` (weights are fractions of equity).
- Bars/year annualisation: PD = 6 bars/day, ANN = sqrt(6*365) = sqrt(2190).
- V0 BASE (deployed): `sig0[t] = std(u[t-360..t-1], ddof=1)*ANN`,
  min_periods 120; `s0[t] = min(2, 0.25/sig0[t])`; NaN or sig<=0 -> 1.0;
  `ws0_c[t] = w_c[t]*s0[t]`.
- Va RISK-PARITY (30d per-coin): `sig_c[t] = std(r_c[t-180..t-1],
  ddof=1)*ANN`, min_periods 60; `inv_c = 1/sig_c`; if any coin non-finite or
  <= 0 that bar -> tilt 1.0 all coins; else `tilt_c = inv_c/mean(inv)`,
  clipped to [0.5, 2.0] (no renormalisation after clip — disclosed);
  `wsA_c[t] = w_c[t]*tilt_c[t]`. No book-level scale (pure allocation tilt).
- Vb SLOW (120d book): same as V0 with window 720, min_periods 240.
- Vc SEMI (60d downside): same window as V0 (360, min_periods 120);
  `mu = mean(u[window])`; `semivar = mean(min(0,u-mu)^2)` over the FULL
  window (upside contributes 0); `semi[t] = sqrt(semivar)*sqrt(2)*ANN`
  (sqrt2 so a symmetric window matches std — disclosed); NaN/semi<=0 -> 1.0;
  `sc[t] = min(2, 0.25/semi[t])`; `wsC_c[t] = w_c[t]*sc[t]`.
- Anchor years: `A_k = 2021-09-24 .. 2025-09-24`, partition
  `[A_k, A_{k+1})` for k=0..3 and `[A_4, A_4+365d)` for the last (leap-day
  fix as in oc_bookic: 2023-09-24..2024-09-24 spans Feb-29, so literal +365d
  would orphan 6 bars; disclosed here before seeing outcomes).
- Per (variant, year) on year bars: return `= prod(1+pn)-1`; max DD on the
  year-rebased equity (start 1.0): `max(1 - eq/min-peak)`; Sharpe
  `= mean(pn)/std(pn,ddof=1)*ANN` (rf 0); NaN if < 30 bars or std==0.

## Decision rule (from the assignment, applied to DD and Sharpe)

- Per year effects vs BASE: `dSharpe_y = Sharpe_V,y - Sharpe_BASE,y`
  (positive = better); `dDD_y = DD_BASE,y - DD_V,y` (positive = V draws
  down less). NaN or `<= 0` counts as FAIL (the common sign must be an
  improvement, not merely consistent).
- LOYO stability (no fitted parameters exist, so LOYO is a stability check):
  `LOYO_h` passes for a metric iff `sign(d_h) == sign(mean_{k!=h} d_k)` and
  that training mean is `> 0` (NaN -> fail).
- Variant V is PROMISING iff ALL FOUR hold: dSharpe>0 in >= 4/5 years AND
  dDD>0 in >= 4/5 years AND LOYO-Sharpe passes in >= 4/5 held-out years AND
  LOYO-DD passes in >= 4/5. Return and pooled-5y stats are descriptive only.
- First-four-year (2021-2024) sensitivity is reported descriptively (repo
  selection rule) but is NOT part of the verdict.

## Causality / coverage tests (tests/test_oc_bookvol.py)

- test_scales_causal: truncate books+opens at two cuts; scales at rows <= cut
  identical when recomputed on the truncated frame.
- test_vol_window_ends_before_t: scale[t] unchanged when all opens at/after
  open[t] are perturbed (windows end at t-1).
- test_turnover_cost: cost >= 0 everywhere; flat-weight bars cost 0.
- test_year_partition: the 5 year masks are disjoint and cover every scored
  bar exactly once; per-year bar counts reported.

## Outputs

- `research/tournament/oc_bookvol/`: PLAN.md (this file),
  `compute_bookvol.py`, `results.json`, REPORT.md (tables + one-line
  verdict). No tuning on results; any post-hoc change logged in REPORT.md.
  No commits.
