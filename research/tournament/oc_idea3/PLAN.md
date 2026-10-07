# oc_idea3 PLAN (pre-registered BEFORE any outcome statistic)

## Idea (IDEAS.md #3, exact)

Pre-bar intraday-RV skip (don't place dips into an ongoing flush): if minutes
0-15 already printed most of the bar's range, the resting bids at 2.5-5 sigma
are chasing a live cascade; fills cluster at the worst adverse-selection point.
Skipping the bar avoids buying the middle of the waterfall.

## Hypothesis (fixed here)

Dip-rung fills whose (coin, bar) printed an unusually large first-15-minute
range perform worse than fills in quiet-open bars: mean y1.0 flagged < mean
y1.0 kept (spread negative). Skipping flagged (coin, bar) bids cuts left-tail
exposure (yearly daily-sum worst day improves) at the cost of some yearly sum
(filter, not a stream; expected return -0.2-0.0 pp/mo, DD -0.5-1.5 pp per IDEAS).
Sign is read from the data; consistency across anchor years is what matters
(PROMISING rule below).

## Data (fixed here)

- Fills: `research/tournament/ext/fills_U_ext.parquet`. Universe MAIN = majors
  {BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT} x R2 depths x1 in
  {2.5, 3.0, 3.5, 4.0, 5.0}. T = t_fill - f minutes (all T on 4h boundaries).
  Outcome = y1.0 only (exact net return at TP 1.0 sigma, unit rung size,
  fees + adverse funding already inside; y0.5/y1.5 NOT scored). Reported in
  bps (1 bps = 1e-4); round-trip cost ~4-8 bps.
- 1m klines (majors only, in repo; the assignment's stated 1m source for this
  idea): BTC `data/raw/btc_intraday_20260924/klines_1m_20*.parquet`, others
  `data/raw/majors_intraday_20260924/<SYM>_1m_20*.parquet` (columns
  open_time/open/high/low/close). Minutes used: t < 2026-09-24 00:00 UTC only.
  One coin in memory at a time (float32), one process, RAM < 1 GB.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides the
  old RULES.md hidden-year cut; all five years are research data and any finding
  needs prospective validation). No other data (no hourly, no funding, no
  options, no premium). No fetch (all required data is stored locally).

## Exact causal definitions (frozen)

- 4h grid: holding bar j covers [START + 4h*j, START + 4h*j + 4h) with
  START = 2020-08-01 00:00 UTC (midnight floor("4h") grid, same as v293 and
  oc_filltime). Bar j has minute offsets 0..239; next-bar open is offset 240.
  Bar open O_c(j) = 1m `open` of coin c at offset 0 (NaN when missing).
- sigma_4h(c, j) (known at the bar open, v293 definition): simple returns
  r_b = O_b / O_{b-1} - 1 of 4h bar opens; sigma(j) = sample std (ddof=1) of
  r over the 360 bars ending at j-1 (min_periods 120) =
  pct_change().rolling(360).std().shift(1). Bars with non-finite O_j or
  sigma <= 0 / NaN are unusable (any feature needing them is NaN).
- RV15(c, T) for a 4h bar open T (= START + 4h*j): let H = max `high` and
  L = min `low` over the 16 one-minute bars with offsets 0..15 inclusive
  (minutes [T, T+16min); the first fillable minute is 16, so all 16 minutes
  are strictly before any fill -- causal at minute 15). Then
  RV15(c, T) = (H - L) / (O_c(T) * sigma_4h(c, T)) (dimensionless, in sigma
  units: the 15-minute range as a multiple of the 60d 4h sigma). Require all
  16 highs/lows finite AND O finite AND sigma finite and > 0, else NaN.
  NaN RV15 -> NOT skipped (conservative: keep the bids).
- Threshold (single value per test year, walk-forward, no outcome read):
  for anchor A_k, q80_seq(k) = 80th percentile of RV15(c, T) over all
  (coin, bar) observations with T in [A_k - 365d, A_k) and RV15 non-NaN
  (the prior year, strictly pre-anchor; pooled over the 5 majors; one value
  for all coins). Require >= 500 training observations else the year's
  threshold is NaN (FAIL).
- SKIP flag (actionable at minute 15; the bot can cancel resting bids before
  minute 16): SKIP(c, T) = 1 iff RV15(c, T) > q80_seq(k) for the anchor year
  Y_k = [A_k, A_k + 365d) containing T. Per (coin, bar): when SKIP = 1, ALL
  rung bids of coin c in bar T are skipped (all k in R2). Fills carry the SKIP
  of their (sym, T). Rows with T >= 2026-09-24 00:00 UTC are excluded (none:
  fills end 2026-09-23 12:00). Fills with NaN RV15 (missing minutes/sigma) are
  SKIP = 0.
- LOYO thresholds (no outcome read): for held-out year h, q80_loyo(h) = 80th
  percentile of RV15(c, T) over (coin, bar) observations with T inside the
  OTHER 4 anchor years (union of Y_k, k != h; RV15 non-NaN; >= 500 required).
  SKIP_loyo for rows in year h uses q80_loyo(h). Spreads under LOYO thresholds
  are the LOYO readouts.

## Evaluation (fixed here)

- Anchor years (5): Y_k = [A_k, A_k + 365d) by T,
  A in {2021-09-24 .. 2025-09-24} (UTC).
- Per anchor year (sequential thresholds): n, n_skip (SKIP=1), n_keep; mean
  y1.0 skip/keep (bps) + win rates (y1.0 > 0) + min y1.0 skip/keep (bps);
  spread = mean_skip - mean_keep (bps; negative expected = flagged bars
  worse). Minimum-n: a year's spread is valid only if n_skip >= 10 AND
  n_keep >= 10, else NaN = FAIL for the sign count (never imputed).
- Skip simulation per year (unit rung size, same table as oc_macro): S_full =
  sum y1.0 over year rows; S_skip = sum y1.0 over year rows with SKIP=0;
  cut = (S_full - S_skip) / S_full (NaN if S_full <= 0; a skip that cuts a
  non-positive sum is not a saving); daily sums grouped by T floor('D'):
  worst_day_full, worst_day_skip; tail_improves = worst_day_skip >
  worst_day_full (strictly less negative). Kept-share = n_keep / n.
- LOYO: for held-out year h, spread_loyo(h) = mean_skip - mean_keep in year h
  under SKIP_loyo (requires n_skip >= 10 AND n_keep >= 10 else NaN = FAIL);
  agree_h = sign(spread_loyo(h)) == sign(spread_seq_pooled_other4)? NO --
  frozen simpler analogue of the tercile precedent: the LOYO check is the
  sign of spread_loyo(h) itself (negative expected), i.e. the threshold
  re-learned without year h still marks worse fills inside year h.
- DECISION RULE (assignment default + filter tail bar): PROMISING iff
  (a) spread_seq < 0 in >= 4 of 5 anchor years (same sign, and the useful
  direction; NaN = fail), AND (b) spread_loyo < 0 in >= 4 of 5 held-out
  years (NaN = fail), AND (c) tail_improves in >= 4 of 5 anchor years
  (sequential SKIP; NaN = fail). Otherwise NOT PROMISING. One variant only
  (q80); no tuning on results; any post-hoc change logged in REPORT.md.
- Descriptive only (NOT part of the rule): per-coin skip rates and spreads;
  overall pooled spread; retention/S_skip levels; worst-day dates; RV15
  distribution (q50/q80/q90) per training window; coverage (fraction of fills
  with non-NaN RV15).

## Causality / correctness tests (tests/test_oc_idea3.py)

- test_T_grid_and_bounds: majors-R2 join yields the oc_macro row count; T =
  t_fill - f minutes; T on 4h boundaries; no T at/after 2026-09-24.
- test_rv15_causal_truncate: 5 sampled (coin, bar) with fills; RV15 recomputed
  from 1m truncated to t <= T+15min equals the stored value; shifting/removing
  any minute > T+15min leaves it unchanged; NaN when the 0..15 window has gaps.
- test_sigma_matches_v293: sigma_4h for 2 coins x 5 bars equals
  pct_change().rolling(360).std().shift(1) on the same opens.
- test_thresholds_causal: q80_seq(k) uses no (coin, bar) with T >= A_k;
  q80_loyo(h) uses no bar of year h (recompute from stored RV15 table).
- test_skip_recomputable: SKIP recomputed from (sym, T, RV15, thresholds)
  after dropping all y-columns is identical (no outcome leak).

## Deliverables

research/tournament/oc_idea3/: PLAN.md (this file), analyze_idea3.py,
results.json, REPORT.md (tables + one-line verdict). tests/test_oc_idea3.py.
One process, RAM < 1 GB, majors 1m only. No tuning on results. No commits, no
edits outside the two allowed paths.
