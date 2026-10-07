# oc_idea10 PLAN (pre-registered BEFORE any outcome statistic)

Idea #10 of `research/tournament/oc_ideas/IDEAS.md`: 1h-confirmation filter
on 4h dip bids (fewer trades, not more). This file freezes the hypothesis,
data, exact causal definitions, and decision rule before any outcome
statistic is computed. No tuning on results; any post-hoc change is logged
in REPORT.md.

## Idea (IDEAS.md #10, exact)

Mechanism: the hourly LADDER as an independent stream failed 3x
(v229/v275/v413: DD 30-44) -- more trades into faster noise. The opposite
direction is untested: use the 1h timeframe as a FILTER on the 4h ladder
(same bids, fewer of them), requiring the flush to be visible intraday
before buying the 4h dislocation.

Causal definition (verbatim): at T, for coin c, 1h-state =
(open_T - min low of prior six 1h bars)/sigma_4h(T), 1h bars strictly < T;
place coin c's 4h rung bids only if 1h-state > 1.0 (flush confirmed
intraday); else skip coin-bar.

Expected (IDEAS.md): return -0.3-+0.1 pp/mo (fewer fills), DD -0.5-1.5 pp,
win rate up 1-3 pp (slow-bleed bids removed); only interesting if DD falls
with retention >= 90%.

Differs from closest tried: v229/v275/v413 ran the hourly ladder as an
EXTRA STREAM (more rungs, DD 42-44, "closed for good"); v349 hour-of-day
multiplier (DD 22, rejected). A gate that REMOVES 4h bids != a second
ladder that ADDS hourly bids.

## Hypothesis (fixed here)

Dip-rung fills whose (coin, bar) already printed a >= 1-sigma intraday
flush in the 6 hours before the 4h open perform better than fills without
intraday confirmation: mean y1.0 kept > mean y1.0 dropped (spread
positive). Keeping only confirmed (coin, bar) bids raises per-rung mean
and win rate and improves the yearly daily-sum worst day at the cost of
some yearly sum (filter, not a stream). Sign is read from the data;
consistency across anchor years is what matters (PROMISING rule below).

## Data (fixed here)

- Fills: `research/tournament/ext/fills_U_ext.parquet`. Universe MAIN =
  majors {BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT} x R2 depths x1 in
  {2.5, 3.0, 3.5, 4.0, 5.0} (~6876 rows; per-year T-counts 990/1045/1330/
  989/1144, verified from counts only, no outcomes inspected).
  T = t_fill - f minutes (all T on 4h boundaries). Outcome = y1.0 only
  (exact net return at TP 1.0 sigma, unit rung size, fees + adverse funding
  already inside; y0.5/y1.5 NOT scored). Reported in bps (1 bps = 1e-4);
  round-trip cost ~4-8 bps.
- Hourly: `research/tournament/ext/hourly_ext.parquet` (hourly OHLC per
  coin, 2020-08-01..2026-09-23 23:00 UTC; columns t/open/high/low/close/sym;
  t = bar open, bar = [t, t+1h)). This is the assignment's "majors 1m
  aggregated to 1h" in stored form; NO 1m data is loaded.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides
  the old RULES.md hidden-year cut; all five years are research data and any
  finding needs prospective validation). No other data (no funding, no
  options, no premium, no book). No fetch (all required data is stored
  locally).
- LIGHT: one process, one coin's hourly frame in memory at a time
  (float64, < 100 MB), RAM < 1 GB.

## Exact causal definitions (frozen)

- 4h grid: holding bar open T lies on START + 4h*j with
  START = 2020-08-01 00:00 UTC (midnight floor("4h") grid, same as v293 and
  oc_dipexit). Verified: every MAIN-R2 fill has (T - START) mod 4h == 0.
  Rows with T >= 2026-09-24 00:00 UTC are excluded (none: fills end
  2026-09-23 12:00).
- open_T(c, T): `open` of coin c from hourly_ext at t == T (the 4h bar
  open price). NaN/missing when the hourly row is absent.
- Prior six 1h bars (strictly < T): hourly rows of coin c with
  t in {T-6h, T-5h, T-4h, T-3h, T-2h, T-1h} (the six hourly bars whose
  close <= T). minLow6(c, T) = min `low` over those six bars. Requires all
  six rows present with finite low, else NaN (unconfirmable).
- sigma_4h(c, T) (known at the bar open, v293 definition): 4h bar opens
  O_b(c) = hourly `open` at 4h-grid times for coin c (00/04/08/12/16/20
  UTC). Simple returns r_b = O_b / O_{b-1} - 1. sigma_ret(c, T) = sample
  std (ddof=1) of r over the 360 4h bars ending at the bar before T
  (min_periods 120) = pct_change().rolling(360).std().shift(1) evaluated
  at T. Requires finite O_T, finite sigma_ret > 0, else NaN.
- 1h-state (dimensionless, in sigma units, same units as rung depths k):
  state(c, T) = (open_T(c, T) - minLow6(c, T)) / (open_T(c, T) * sigma_ret(c, T)).
  The numerator is the 6h intraday drawdown in price; the denominator is
  the 60d 4h sigma in price (open * return-sigma). Requires open_T finite,
  minLow6 finite, sigma_ret finite and > 0, else NaN.
- KEEP flag (actionable at T; the bot reads six closed hourly bars and the
  trailing sigma, all known at the bar open, before placing resting bids):
  KEEP(c, T) = 1 iff state(c, T) > 1.0 (STRICT; flush confirmed intraday),
  else 0. NaN state -> KEEP = 0 (fail-closed: unconfirmable coin-bars are
  skipped, exactly as a live bot with missing data would place no bid).
  Threshold 1.0 and lookback six bars are the single pre-registered values
  from IDEAS.md (no percentile, no walk-forward fit, no outcome read).
- Row gate: each MAIN-R2 fill carries the KEEP of its (sym, T). Per
  (coin, bar): when KEEP = 0, ALL rung bids of coin c in bar T are skipped
  (all k in R2). Dropped fills are removed; kept fills are kept at unit
  rung size.
- At most 1 scored variant (this fixed 1.0/six-bar gate). The three
  per-series/descriptive splits of other studies do not apply here; no
  other threshold is scored. Any post-hoc threshold is a disclosed extra
  and is NOT part of the verdict.

## Evaluation (fixed here)

- Anchor years (5): Y_k = [A_k, A_k + 365d) by T,
  A in {2021-09-24 .. 2025-09-24} (UTC).
- Per anchor year: n_full, n_kept, n_drop; kept-share = n_kept / n_full;
  mean y1.0 full/kept/drop (bps) + win rates (y1.0 > 0) + min y1.0
  kept/drop (bps); spread = mean_kept - mean_full (bps; positive expected
  = confirmation selects better rungs). Minimum-n: a year's spread is
  valid only if n_kept >= 10 AND n_drop >= 10, else NaN = FAIL for the
  sign count (never imputed).
- Filter simulation per year (unit rung size, equal exposure, same table
  as idea 3 / oc_macro skip simulation): S_full = sum y1.0 over year rows;
  S_kept = sum y1.0 over kept rows; S_kept_eq = S_kept * n_full / n_kept
  (equal-exposure rescale to full notional; NaN if n_kept == 0);
  gain_eq = S_kept_eq - S_full = n_full * spread (same sign as spread);
  cut_raw = (S_full - S_kept) / S_full (NaN if S_full <= 0; descriptive).
  Daily sums grouped by T floor('D') (UTC, as in oc_macro): worst_day_full
  = min daily sum over full rows; kept daily sums rescaled by the same
  n_full / n_kept factor, worst_day_kept_eq = min over kept days;
  tail_improves = worst_day_kept_eq > worst_day_full (strictly less
  negative). Secondary (descriptive): maxDD of the cumulative daily-sum
  curve full vs kept_eq. Kept-share and win-rate lift reported as context
  (IDEAS.md interest bar: retention >= 90% with DD/worst-day improvement).
- LOYO agreement for the fixed gate (no cut-off to learn, as in the
  oc_macro precedent): pooled_other4_spread(h) = mean_kept - mean_full over
  rows of the other 4 anchor years pooled (NaN if either side < 10 rows);
  agree_h = sign(spread_h) == sign(pooled_other4(h)), both nonzero.
- DECISION RULE (assignment default + filter tail bar): PROMISING iff
  (a) spread (== gain_eq sign) is POSITIVE in >= 4 of 5 anchor years
  (same sign, and the useful direction; NaN = fail), AND
  (b) agree_h holds in >= 4 of 5 held-out years (NaN = fail), AND
  (c) tail_improves holds in >= 4 of 5 anchor years (NaN = fail).
  Otherwise NOT PROMISING. Costs context: per-rung means are rung-
  conditional (fills are ~2% of rung-bars), compared against ~4-8 bps
  round-trip cost.
- Descriptive only (NOT part of the rule): per-coin kept rates and
  kept-vs-drop spreads; overall pooled spread; S_kept levels; worst-day
  dates; state distribution (q50/mean/share > 1.0) per year; coverage
  (fraction of fills with non-NaN state); maxDD rows.

## Causality / correctness tests (tests/test_oc_idea10.py)

- test_counts_and_grid: majors-R2 join yields 6876 rows, T = t_fill - f,
  T on 4h boundaries, per-year T counts 990/1045/1330/989/1144; no T
  at/after 2026-09-24.
- test_state_causal: state(c, T) recomputed from hourly truncated to
  t <= T equals the stored value; perturbing/removing any hourly row with
  t > T leaves it unchanged; NaN when any of the six lows / open_T /
  sigma is missing; hand-check on 2 (coin, T) incl. a threshold boundary
  (state == 1.0 -> KEEP 0, strict).
- test_sigma_matches_v293: sigma_ret for 2 coins x 5 bars equals
  pct_change().rolling(360).std().shift(1) on the same 4h opens.
- test_keep_recomputable: KEEP recomputed from (sym, T, state) after
  dropping all y-columns is identical (no outcome leak); KEEP depends
  only on hourly rows with t <= T.
- test_decision_matches_counts: verdict recomputed from results.json
  counters (spread>0 count, LOYO agree count, tail count); sums/worst-day
  nondegenerate.

## Deliverables

research/tournament/oc_idea10/: PLAN.md (this file), analyze_idea10.py,
results.json, REPORT.md (tables + one-line verdict). tests/test_oc_idea10.py.
One process, RAM < 1 GB, hourly_ext + fills_U_ext only. No tuning on
results; any post-hoc change logged in REPORT.md. No commits, no edits
outside the two allowed paths.
