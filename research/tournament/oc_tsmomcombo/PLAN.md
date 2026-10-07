# oc_tsmomcombo PLAN (pre-registered BEFORE any outcome is computed)

Frontier check, post-hoc informed and labelled as such (sleeve choice and base
rows are chosen AFTER seeing `oc_tsmom` and `oc_frontier`). No outcome of THIS
task has been inspected; the rules below are fixed here.

## Hypothesis (fixed here, descriptive)

`oc_tsmom` showed a 0.25x BTC/ETH 30-day TSMOM sleeve adds +0.05..+0.46 %/month
but +0.5..+1.5 pp max yearly DD to R2B1D17BF (correlated add-on, NOT
PROMISING). `oc_frontier` lists the official (R, DD) Pareto rows. Question:
does the SAME sleeve, overlaid at 0.10x / 0.25x on other cached frontier rows,
produce a combined point that dominates an official frontier point or reaches
the stretch (max yearly DD < 15 with >= 5 %/month)? This is REPORTING ONLY.

## Base rows x sleeve weights (fixed here, 5 x 2 = 10 combos)

- R2B1D13BF <- `research/parallel/rounds/parallel-20260906-r2/v424/v424_runs.pkl`
- R2B1D14BFX5 <- v424/v424_runs.pkl
- R2B1D17BFG2 <- v421/v421_runs.pkl (audited twin in v422 is identical)
- R2B1D17BF <- v411/v411_runs.pkl (deployment pick, reference)
- G2K20 <- v422/v422_runs.pkl (highest-R frontier region)
- Weights w in {0.10, 0.25} (overlay, same as oc_tsmom 0.25 plus a lighter 0.10).

## Sleeve: reuse oc_tsmom code and sleeve EXACTLY (frozen)

Copy of `research/tournament/oc_tsmom/run_tsmom.py` definitions, constants
unchanged: coins BTCUSDT+ETHUSDT; hourly `research/tournament/ext/hourly_ext.parquet`
with t < 2026-09-24 00:00 UTC only; day D = UTC day; O(sym,D) = open of bar
t = D 00:00, C(sym,D) = close of bar t = D 23:00 (missing day -> coin flat 0,
no forward fill); ret30(sym,D) = C(D)/C(D-30)-1, signal = sign (0 if any of
31 closes missing); vol = std of 30 daily log returns ending D (ddof=1) *
sqrt(365), NaN/non-positive -> pos 0; pos(sym,D) = signal*min(0.10/vol,1.0),
known at close D, held over E = D+1 entered at O(E); g(E) = sum pos(E-1)*
(O(E+1)/O(E)-1) (missing open -> 0); cost(E) = 0.00055*sum|pos(E-1)-pos(E-2)|
(pos before first holding day = 0); fund(E) = 0.0003*sum max(pos(E-1),0);
r_s(E) = g-cost-fund. Sleeve equity starts 1.0 at each anchor open, compounds.
Anchors A in {2021-09-24,...,2025-09-24}, year = holding days E in [A,A+365d)
with O(E),O(E+1) available (last year ends 2026-09-22 by construction).

## Base: same daily-grid reset convention as oc_tsmom Variant B (frozen)

Per (row, year y, anchor a0): F_s = e1_s/b_s per shift s=0..3 where
e1_s,_ = v388.hourly(runs[s][row], g0=2021-09-24 04:00 UTC,
g1=2026-09-23 12:00 UTC) (v388_bot_stop_distance.hourly: 1h ffill grid),
b_s = last e1_s value <= a0; F = mean_s F_s (F(a0)=1.0 by construction).
Base daily r_b(E) = F(E+1 00:00)/F(E 00:00)-1. Holding days E = intersection
of sleeve-available and base-available days per year (same shared-day rule as
oc_tsmom; year 0 drops the 2021-09-24 partial day). Base year equity starts
1.0, compounds r_b. DD CONVENTION (daily grid, stated): max peak-to-trough on
the daily-00:00 year path, NO eq_min / 1m marking (same as oc_tsmom primary;
oc_tsmom REPORT caveat 2: reads ~1-3pp below 1m-marked DDs). For REFERENCE
only, also report each base row's official reset-metric numbers from
`vNNN_result.json` rows[row] = (R, W, DD=max years[i][1], years, full_path_dd)
and the oc_kpi/oc_frontier published DDs (hourly grid with eq_min lows).

## Combined + metrics (frozen)

r_c(E) = r_b(E) + w*r_s(E). Combined year equity starts 1.0, compounds r_c.
Per (row,w,year): monthly % = eq_end^(1/12)-1; max yearly DD = daily-grid DD
of the combined year path. Aggregates: 5y geometric monthly % =
(prod_y eq_end)^(1/60)-1; worst year = min yearly monthly %; max yearly DD =
max yearly DD. Cross-check: w=0 reproduces base nets; compounding residuals
~0; R2B1D17BF@0.25 reproduces oc_tsmom combined monthly/DD exactly (abs tol).

## Dominance + stretch (frozen, descriptive)

Official set = `research/tournament/oc_frontier/results.json` rows (80) with
(R, dd_yearly) and its frontier_yearly / frontier_fullpath lists. Combined
point (R_5y, max-yearly-DD daily-grid) DOMINATES official point P iff
R_c >= R_P AND DD_c <= DD_P with >=1 strict (oc_frontier Pareto rule).
Report per combo: list of dominated official rows (or "dominates none"), and
whether it dominates ANY official frontier member (flag). STRETCH flag:
R_5y >= 5.0 AND max yearly DD < 15 (daily-grid). Caveat: DD conventions differ
(daily-grid vs official hourly+eq_min), so dominance/stretch are labelled
daily-grid-vs-official, not a deploy claim. No 1m data is loaded, so gate DD
(max of 4h-close and 1m-marked) is NOT evaluated here.

## Decision rule (fixed here)

REPORTING ONLY: no PROMISING / NOT-PROMISING selection is made (post-hoc
informed frontier check per the assignment). The header default 4-of-5 +
4-of-5-LOYO rule is NOT applied as a gate (no new effect is claimed); per-year
excess (combined-base) signs are shown in the table for transparency only.

## Deliverables (fixed here)

`research/tournament/oc_tsmomcombo/`: PLAN.md (this file), run_combo.py,
results.json, REPORT.md (tables + one-line verdict). Test:
`tests/test_oc_tsmomcombo.py` (sleeve-exactness: r_s equals oc_tsmom r_sleeve
per year; causality: shift C(D) moves only signals D..D+30; caps: hourly cap,
pos cap 1.0, vol-target math; recompute: results.json series recompound to
stored totals; base: w=0 reproduces base, R2B1D17BF@0.25 matches oc_tsmom).
One process, no 1m data, RAM < 1 GB. Market data up to 2026-09-24 00:00 UTC
(assignment override; all five years are research data; any finding needs
prospective validation). Post-hoc changes, if any, logged in REPORT.md.

## Amendment log (append-only; original above frozen)
(none yet)
