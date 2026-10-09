# oc_k2placebo — PLAN (pre-registered 2026-10-07, BEFORE any outcome)

Diagnostic only: is the Kronos K2 dip tilt's post-release gain (+0.15 %/month in
oc_kronoshidden) distinguishable from random timing? Nothing here selects or
changes anything. The post-release year 2025-09-24 .. 2026-09-23 was already
scored once by oc_kronoshidden; dev years 2021..2024 are inside Kronos'
pretraining (upper bound, not clean).

## Frozen inputs (read-only, never edited)

- `research/tournament/oc_kronoshidden/kronos_features_4shift.parquet`:
  cols sym/shift/T/low1 (+sigma etc), 260,325 rows, 2020-10-06 .. 2026-09-23.
- `research/tournament/oc_kronoshidden/fits.json`: per-anchor direction (+1 all
  five anchors), q20, q80 of risk = -low1 (anchor-2025 fit for post-release yr).
- `research/tournament/oc_kronoshidden/REPORT.md`: K2 rule = x1.25 favourable
  outer quintile / x0.75 unfavourable / x1 else; missing feature -> 1.
- `research/tournament/oc_placebo_dip/compute_placebo_dip.py`: D0 rung outcomes
  (TP 1 sigma, close5 stop 4 sigma, 8-sigma backstop, timeout next 4h open;
  maker 0.0002 / taker 0.00055; v293 settle funding), B1 sizes w = 1/(1+n_fill),
  4 clock phases (4h grid from 2020-08-01 00:00 UTC + 0/1/2/3 h), majors x R2
  depths {2.5,3,3.5,4,5}, live offsets 16..238 strict trade-through, bars open
  in [2021-09-24, 2026-09-24). Imported read-only (no copy-paste drift).

## Pre-registered computations (ONLY these)

1. Replica rebuild: call `build_base()` verbatim (no args). Reproduction gate:
   5y 4-phase-mean base sum == 7.718304 +/- 0.002 (oc_placebo_dip base_sum5y),
   ledger n_fills == 22312, checksum 902c5bbfe8fed3c0. If gate fails: STOP.
2. K2 multiplier per rung fill: bar key (sym, shift = phase, T = bar open =
   START + bar_time minutes, START = 2020-08-01 UTC) joined to feature table on
   (sym, shift, T). risk = -low1. Per year y in 0..4 (anchors 2021..2025-09-24,
   year y = [A_y, A_{y+1}) with A_5 = 2026-09-24): fit = fits.json[ANCH5[y]],
   hi/lo = 1.25/0.75, `assign_mult` logic copied from tilt_rule.py
   (dir +1: r >= q80 -> 1.25; r <= q20 -> 0.75; else 1.0; NaN/missing -> 1.0).
3. Per year y (4-phase mean, w*y units, y = D0 y1.0 leg):
   - base(y) = mean_p sum_{fills phase=p,year=y} w*y
   - k2(y) = mean_p sum w*mult_K2(bar)*y
   - realmean(y) = mean mult_K2 over fills in year y (each rung fill = 1 obs)
   - norm(y) = k2(y) / realmean(y); also report decision mean over all feature
     rows with T open in year y (diagnostic, not used in test).
4. Timing placebo (primary): 1000 permutations, seed 20261007. Per year y:
   take the bar-level multiset of K2 multipliers over ALL decision bars
   (feature-table rows with T open in year y, all sym/shift) and randomly
   reassign them to bars (uniform permutation via default_rng(20261007+y)).
   Each fill inherits its bar's permuted mult. Permuted k2_perm(y) and
   norm_perm(y) = k2_perm(y) / realmean(y) (denominator = ACTUAL realmean,
   constant per year, so percentile(norm) == percentile(raw)). Null keeps the
   multiplier distribution and exposure, destroys timing (incl. within-bar).
5. Block placebo (persistence-preserving): 1000 permutations, seed 20261008.
   Per (sym, shift, year): order decision bars by T, chunk into consecutive
   blocks of 42 bars (42x4h = 7 d; last block shorter kept as-is), permute
   blocks within the same (sym, shift, year) with default_rng(20261008+y).
   Map to fills, same norm. Tests whether the gain survives local persistence.
6. Percentile per year: pct = 100*(1 + #{perm norm <= actual norm})/(1 + 1000).
   Significant at 5% iff pct >= 95. Report per-year table for both placebos.
   Focus = post-release year y=4 (only clean year); dev years y=0..3 reported
   for context with contamination label.

## What is NOT done

- No engine rerun, no G2 overlay, no variant selection, no threshold tuning.
- No use of forward returns beyond the replica's own D0 y outcomes (which are
  mechanical stop/TP/timeout exits, not a fitted signal). No fit on test years.
- If anything changes after seeing an outcome, the original row stays and the
  change is an extra disclosed row.

## Outputs

- `research/tournament/oc_k2placebo/results.json` (all numbers + seeds + join
  coverage), `REPORT.md` (<= honest table + plain statement + 3-line
  Vietnamese verdict), `tests/test_oc_k2placebo.py` (>=1 causality/truncation
  test + >=1 hand-checked synthetic case, run with pytest).
- Scratch only under `research/tournament/oc_k2placebo/tmp/`. Heavy step
  (replica rebuild, >0.4 GB) via heavy_slot; permutations are light (numpy).
- Leakage statement in REPORT: feature timing (400 bars <= T, Kronos side),
  label windows (D0 exits mechanical, no label fit here), fit windows (fits
  from harness rows t_exit < A - 7d, shift-0 only — inherited, not recomputed),
  fill timing (live 16..238 strict trade-through, inherited from replica).
