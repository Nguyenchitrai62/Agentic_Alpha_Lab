# oc_filltime PLAN (pre-registered BEFORE any outcome is computed)

## Question

Dip-rung outcome by the fill minute `f` within the 4h bar (16..238) and by the
time since the fill coin last made a 24h high, for the majors R2 rungs, ALSO
conditional on `n` = number of OTHER majors at <= open x (1 - 2.5 sigma_4h) at
minute f-1. Is there a stable f-window where rungs lose (e.g. the last 30
minutes before the bar-end exit)?

## Universe, outcome, years (fixed)

- Fills: `research/tournament/ext/fills_U_ext.parquet`. Universe MAIN = majors
  {BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT} x R2 depths x1 in
  {2.5, 3.0, 3.5, 4.0, 5.0} (~6876 rows). TT = t_fill - f minutes (all TT on 4h
  boundaries; verified in tests).
- Outcome = y1.0 only (net return at TP 1.0 sigma, unit rung size; y0.5/y1.5
  are NOT scored). Reported in bps (1 bps = 1e-4); round-trip cost ~4-8 bps.
- Anchor years (5): Y_k = [A_k, A_k + 365d) by TT,
  A in {2021-09-24 .. 2025-09-24} (UTC, ~990/1045/1330/989/1144 rows).
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides the
  old RULES.md hidden-year cut; all five years are research data and any
  finding needs prospective validation before real money).

## 1m inputs (fixed; one coin at a time, float32, RAM < 2 GB)

- BTC: `data/raw/btc_intraday_20260924/klines_1m_20*.parquet`; others:
  `data/raw/majors_intraday_20260924/<SYM>_1m_20*.parquet`. Columns
  open_time/open/high/low/close. Minutes used: t < 2026-09-24 00:00 UTC.
  Continuous per-coin 1m index from 2020-08-01 00:00 UTC; missing minutes =
  NaN (never fill / never trigger; a feature needing a NaN minute is NaN).
- 4h grid: holding bar j covers [START + 4h*j, START + 4h*j + 4h) with
  START = 2020-08-01 00:00 UTC (midnight floor("4h") grid, same as v293). Bar j
  has minute offsets 0..239; next-bar open is offset 240. Bar open O_c(j) =
  open of offset 0 (NaN when missing).
- sigma_4h (known at the bar open, v293 definition): simple returns
  r_b = O_b / O_{b-1} - 1 of 4h bar opens; sigma(j) = std(r over the 360 bars
  ending at j-1, min_periods 120, ddof=1) = pct_change().rolling(360).std()
  .shift(1). Bars with non-finite O_j or sigma <= 0 / NaN are unusable (any
  feature needing them is NaN).

## Features (exact, causal — value at TT uses ONLY minutes <= f-1 plus quantities known at the bar open)

Let m = bar_start + (f - 1) minutes (the last minute fully closed before the
fill minute; the fill itself at minute f is NEVER read).

1. `f` — fill minute offset within the bar, taken directly from fills_U_ext
   (integers 16..238 by construction). No 1m data needed; causal by design.
2. `age24` — minutes since the fill coin last made its trailing 24h high,
   evaluated at m: window W = the 1440 minutes [m-1439, m]; Hmax = max high
   over W; age24 = m - max{t in W : high(t) == Hmax} (most recent occurrence;
   0 means the 24h high was just made at m). Require all 1440 highs non-NaN,
   else NaN. Range 0..1439. Large = stale high (no new high for a long time).
3. `n_weak` — number of OTHER majors (0..4) at/below their 2.5-sigma dip level
   at minute m: for each c' != fill coin, weak_{c'} = 1 iff close_{c'}(m),
   O_{c'}(j), sigma_{c'}(j) are all finite AND
   close_{c'}(m) <= O_{c'}(j) * (1 - 2.5 * sigma_{c'}(j)); n_weak = sum over the
   4 others. Valid only if all 4 others have finite inputs, else NaN.
   (O/sigma are bar-open quantities; the only intrabar read is close(m).)

Fixed LATE window (the question's example, descriptive + scored): LATE = 1 iff
f >= 209 (offsets 209..238 = the last 30 fillable minutes of the 16..238
window, i.e. fills with < ~30 min left before the bar-end exit race).

## Evaluation (fixed here)

- Per anchor year, per continuous feature (f, age24, n_weak): Spearman
  rho(feature, y1.0) over year rows (pairwise-complete; NaN if < 30 valid
  pairs — counts as a FAIL for the sign count, never imputed). Report n and
  coverage (fraction of year rows with non-NaN feature).
- Tercile means per year: cut-offs q33/q67 = percentiles of the feature over
  the TRAINING pool = rows with TT < A_k AND feature non-NaN (strictly
  previous data only). Require >= 100 training rows else the year's terciles
  are NaN (FAIL). Assignment: Lo: v <= q33, Hi: v > q67, Mid: else; NaN
  feature -> unassigned. Report mean y1.0 + n per tercile.
- LOYO spread: for held-out year h, training = rows of the other 4 anchor
  years; cut-offs from training; spread_h = mean(y1.0 | Hi) - mean(y1.0 | Lo)
  in the held-out year; require >= 30 rows in EACH of Hi/Lo else NaN (FAIL).
- LATE window: per year report n_late, mean y1.0 late vs early in bps, win
  rates, spread_h = mean_late - mean_early; LOYO analogue: pooled-other-4
  spread sign vs held-out spread sign (no cut-offs to learn; the window is
  fixed, so the yearly spreads ARE the LOYO spreads; the check is whether the
  held-out sign matches the pooled sign of the other 4 years).
- DECISION RULE (from the assignment, per feature / for LATE): PROMISING iff
  (a) sign(rho) [for LATE: sign(spread), negative expected] is identical in
  >= 4 of 5 anchor years (NaN = fail), AND (b) sign(spread_h) is identical in
  >= 4 of 5 held-out years (NaN = fail). Also reported descriptively: whether
  the spread sign matches the IC sign, and the LATE-vs-tercile-Hi overlap.
- At most 3 variants: the 3 features above (f, age24, n_weak); LATE is the
  fixed-window readout of the f analysis, not a 4th variant. No thresholds
  were fit on outcomes (209 = last-30-minutes arithmetic; tercile cut-offs
  are learned walk-forward only).

## Causality / correctness tests (tests/test_oc_filltime.py)

- test_T_grid_and_f_range: TT == t_fill - f for all majors-R2 rows;
  f in 16..238; TT on 4h boundaries; per-year counts 990/1045/1330/989/1144.
- test_age_truncation: 5 sampled rungs; recompute age24 from 1m highs
  truncated to t <= m; assert equality with the stored value; assert shifting
  all data after m leaves it unchanged; assert NaN when the window has gaps.
- test_nweak_truncation: 5 sampled rungs; recompute n_weak from closes
  truncated to t <= m plus bar-open O/sigma; assert equality; assert no read
  of minute f or later (drop minutes > m, unchanged).
- test_sigma_matches_v293: sigma_4h for 3 coins x 5 bars equals
  pct_change().rolling(360).std().shift(1) on the same opens.
- test_cutoffs_causal: year-1 and one LOYO fold's q33/q67 use no row with
  TT >= the test year's start (recompute from features parquet).

## Deliverables

research/tournament/oc_filltime/: PLAN.md (this file), build_features.py
(1m -> features_filltime.parquet, one coin at a time, float32),
analyze_filltime.py (IC + terciles + LOYO + LATE -> results.json),
features_filltime.parquet, results.json, REPORT.md (tables + one-line
verdict). tests/test_oc_filltime.py. One process, no commits, no edits
outside the two allowed paths. Any post-hoc change logged in REPORT.md.
