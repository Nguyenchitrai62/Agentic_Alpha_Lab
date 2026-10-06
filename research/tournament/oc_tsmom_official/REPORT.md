# oc_tsmom_official REPORT: TSMOM sleeve on the OFFICIAL metric

Method (frozen in PLAN.md): sleeve = `oc_tsmom` 30d BTC/ETH TSMOM exactly
(10% vol target, cap 1.0x, next-day-open, taker 0.00055, longs 0.0003/d;
`hourly_ext.parquet`, t < 2026-09-24 UTC only; daily r_s equals oc_tsmom to
5e-09) marked HOURLY on the v388 1h grid (g0 = 2021-09-24 04:00,
g1 = 2026-09-23 12:00): eq via hourly closes, eq_min worst-case (long ->
hour low, short -> hour high); day-boundary eq uses O(next day) so it
compounds the daily sleeve exactly (boundary gap 0.0; eq_min <= eq
everywhere). Base = 4-phase hourly eq/eq_min via `v388.hourly` ONLY.
Combination (overlay, mirrors `reset_metric.year_reset`): per shift
F_s = e1_s/b_s, sleeve F = S/bS (reset at each anchor); combined_es =
mean(F_s) + w*(F-1), combined_ms = mean(MN_s) + w*(FM-1); per-year R/DD
from the combined es/ms; full-path DD v388.mix-style continuous (no
reset). Post-hoc informed, REPORTING ONLY (no selection). One process, no
1m, peak RAM ~0.3 GB. All five years are research data; any finding needs
prospective validation. Repro:
`research/tournament/oc_tsmom_official/{PLAN.md,run_official.py,results.json}`;
test `tests/test_oc_tsmom_official.py`.

## Base proof (official numbers reproduced before combining)

row x src: official (R / W / DD / full-path) | recomputed via year_reset:

- R2B1D13BF (v424): official 4.971 / 2.485 / 14.98 / 14.86 | recomputed EXACT (all 5 years + full-path match)
- R2B1D14BFX5 (v424): official 5.067 / 2.463 / 15.34 / 15.21 | recomputed EXACT
- R2B1D17BFG2 (v421): official 5.410 / 2.588 / 16.91 / 16.82 | recomputed EXACT

## Main table (official metric; per row x weight)

row w | 5y R | worst | max yearly DD | full-path DD | stretch (R>=5, DD<15)

- R2B1D13BF 0.10 | 5.030 | 2.590 | 15.42 | 15.12 | NO (DD over by 0.42pp)
- R2B1D13BF 0.25 | 5.118 | 2.745 | 16.08 | 15.50 | NO
- R2B1D14BFX5 0.10 | 5.126 | 2.567 | 15.78 | 15.47 | NO
- R2B1D14BFX5 0.25 | 5.213 | 2.723 | 16.44 | 15.85 | NO
- R2B1D17BFG2 0.10 | 5.466 | 2.692 | 17.33 | 17.05 | NO
- R2B1D17BFG2 0.25 | 5.550 | 2.845 | 17.96 | 17.39 | NO

Per-year detail (base m% / DD% -> combined m% / DD%; excess / dDD in pp):

- D13BF@0.10: 21-22: 2.485/10.21 -> 2.590/10.04 (+0.105/-0.175);
  22-23: 3.286/14.98 -> 3.294/15.42 (+0.009/+0.438);
  23-24: 4.975/14.76 -> 5.036/15.01 (+0.062/+0.249);
  24-25: 9.526/7.33 -> 9.593/7.42 (+0.067/+0.085);
  25-26: 4.723/10.97 -> 4.778/11.50 (+0.055/+0.536).
- D13BF@0.25: excess +0.259/+0.022/+0.154/+0.167/+0.136;
  dDD -0.067/+1.094/+0.611/+0.635/+1.359.
- D14BFX5@0.10: excess +0.105/+0.009/+0.059/+0.066/+0.055;
  dDD -0.176/+0.439/+0.238/+0.085/+0.448.
- D14BFX5@0.25: excess +0.260/+0.022/+0.147/+0.165/+0.137;
  dDD -0.107/+1.095/+0.584/+0.467/+1.230.
- D17BFG2@0.10: excess +0.104/+0.009/+0.055/+0.060/+0.055;
  dDD -0.053/+0.420/+0.020/+0.083/+0.469.
- D17BFG2@0.25: excess +0.257/+0.022/+0.138/+0.149/+0.137;
  dDD -0.129/+1.049/+0.263/+0.207/+1.210.
  (Excess positive in 30/30 year-cells; DD worse in 24/30 — better only in
  2021-22. Same correlated add-on pattern as oc_tsmom/oc_tsmomcombo.)

Daily-grid vs official metric (the combo-study gap, confirmed):
D13BF@0.10 was 5.068 / 14.49 on the daily grid, now 5.030 / 15.42 on the
official metric (-0.04pp R, +0.93pp DD). The grid understated DD by ~0.9pp
here (0.7-2.8pp range quoted in the assignment).

Descriptive header-default check (no gate): per-year excess same-sign 5/5
(all positive) and LOYO sign-hold 5/5 for all 6 combos.

## Caveats / post-hoc log

1. Post-hoc informed by design (assignment): sleeve + rows + weights picked
   after oc_tsmom/oc_tsmomcombo; labelled, no PROMISING gate, no selection.
2. Sleeve day-open levels are stitched from yearly-convention daily returns
   (entry-from-0 each anchor, exactly as oc_tsmom); the single leap-year gap
   day 2024-09-23 (no anchor year covers it) uses the continuous convention
   (prev = actual previous pos) — one day, sub-bp effect, documented in code.
3. The overlay is extra notional (combined = base + w*sleeve P&L), not a
   capital split; funding/fees on the sleeve notional are inside r_s.
4. No 1m data was loaded, so the gate DD (max of 4h-close and 1m-marked) is
   NOT evaluated; the official hourly+eq_min metric used here is the
   deployment-adjacent convention per the assignment.
5. Checks pass: sleeve gap 5e-09 vs oc_tsmom; base proof exact (R, DD,
   full-path); monthly/total residual <= 6e-04pp; eq_min <= eq everywhere.

## One-line verdict

REPORTING ONLY: on the official metric no combination reaches stretch —
the closest, R2B1D13BF@0.10 at 5.03 %/month with max yearly DD 15.42
(full-path 15.12), misses DD<15 by 0.42pp; the sleeve remains a correlated
return add-on (+0.01..+0.26pp/year excess, DD worse in 24/30 year-cells),
not a diversifier.
