# oc_tsmomcombo REPORT: TSMOM sleeve (exact oc_tsmom reuse) overlaid on cached frontier rows

Method (frozen in PLAN.md): sleeve = `oc_tsmom` 30d BTC/ETH TSMOM exactly
(10% vol target, cap 1.0x, next-day-open, taker 0.00055, longs 0.0003/d;
`hourly_ext.parquet`, t < 2026-09-24 UTC only). Base = daily-grid reset:
per-shift F(a0)=1.0 with `v388.hourly(runs[s][row], 2021-09-24 04:00,
2026-09-23 12:00)`, r_b(E)=F(E+1)/F(E)-1 at 00:00, same holding days as the
sleeve. Combined r_c = r_b + w*r_s, w in {0.10, 0.25}, equity 1.0 per anchor
year [A, A+365d). DD CONVENTION: daily-00:00 grid max peak-to-trough per year,
NO eq_min/1m marking (same as oc_tsmom Variant B). Official reset-metric
numbers (hourly grid + eq_min lows, from `vNNN_result.json` / `oc_frontier`)
are shown for reference only. Post-hoc informed, REPORTING ONLY (no
selection). One process, no 1m, RAM < 1 GB. All five years are research data;
any finding needs prospective validation. Repro:
`research/tournament/oc_tsmomcombo/{PLAN.md,run_combo.py,results.json}`;
test `tests/test_oc_tsmomcombo.py`.

## Base reference (official vs daily-grid recomputation)

row x src: official (R / W / DD_yearly / full-path) | daily-grid (R / W / DD):

- R2B1D13BF (v424): official 4.971 / 2.485 / 14.98 / 14.86 | grid 4.966 / 2.485 / 14.09
- R2B1D14BFX5 (v424): official 5.067 / 2.463 / 15.34 / 15.21 | grid 5.062 / 2.463 / 14.63
- R2B1D17BFG2 (v421): official 5.410 / 2.588 / 16.91 / 16.82 | grid 5.405 / 2.588 / 16.09
- R2B1D17BF (v411): official 5.425 / 2.831 / 18.33 / 16.90 | grid 5.420 / 2.831 / 15.51
- G2K20 (v422): official 5.874 / 2.832 / 17.79 / 17.69 | grid 5.869 / 2.832 / 16.96
(R gaps <= 0.005; DD gaps -0.7..-2.8pp: daily grid understates official DD.)

## Main table (daily-grid; per row x weight: 5y %/mo, worst year, max yearly DD)

row w | 5y R | worst | maxDD | excess R vs grid-base | dDD | dom official (n) | dom frontier members | stretch
R2B1D13BF 0.10 | 5.068 | 2.613 | 14.49 | +0.102 | +0.40 | 20 | Y: v409/R2B1D13; F: v409/R2B1D15B08, v420/R2B1F20K17 | YES
R2B1D13BF 0.25 | 5.216 | 2.799 | 15.09 | +0.250 | +1.00 | 37 | Y: v423/R2B1D17BFX45; F: +v423/R2B1D17BFX45 | no
R2B1D14BFX5 0.10 | 5.165 | 2.590 | 15.03 | +0.103 | +0.40 | 28 | Y: v423/R2B1D17BFX45; F: same 3 | no
R2B1D14BFX5 0.25 | 5.312 | 2.776 | 15.63 | +0.250 | +1.00 | 42 | Y: v423/R2B1D17BFX45; F: same 3 | no
R2B1D17BFG2 0.10 | 5.508 | 2.717 | 16.48 | +0.103 | +0.39 | 56 | Y: v421/v422 R2B1D17BFG2 tie; F: v415/R2B1D17BFS5 | no
R2B1D17BFG2 0.25 | 5.656 | 2.905 | 17.12 | +0.251 | +1.03 | 50 | Y: none; F: v415/R2B1D17BFS5, S6 | no
R2B1D17BF 0.10 | 5.524 | 2.961 | 15.74 | +0.104 | +0.23 | 65 | Y: G2, G2F20K20, X45 + tie; F: 5 rows | no
R2B1D17BF 0.25 | 5.674 | 3.149 | 16.41 | +0.254 | +0.90 | 64 | Y: G2 tie; F: S5, S6 | no
G2K20 0.10 | 5.973 | 2.962 | 17.34 | +0.104 | +0.38 | 50 | Y: v407/R2B1D20B11, v422/G2K20; F: +S5, S6 | no
G2K20 0.25 | 6.122 | 3.151 | 18.23 | +0.253 | +1.27 | 44 | Y: v407/R2B1D20B11; F: +S5, S6 | no
(Y = dominated yearly-frontier members; F = dominated full-path-frontier
members; full dominated-official lists in results.json. Excess/dDD vs the
daily-grid base above. Per-year excess is positive in 50/50 year-cells;
per-year DD is worse in 48/50 — same correlated add-on pattern as oc_tsmom.)

## Caveats / post-hoc log

1. Post-hoc informed by design (assignment): sleeve + rows + weights picked
after oc_tsmom/oc_frontier; labelled, no PROMISING gate, no LOYO gate.
2. Dominance is daily-grid-vs-official: our DD is understated 0.7-2.8pp vs the
official eq_min convention, so every dominance margin < ~1pp DD (all 0.10x
rows) is fragile and NOT a deploy claim; no 1m data was loaded so gate DD
(max of 4h-close and 1m-marked) is unevaluated.
3. v424 rows (R2B1D13BF, R2B1D14BFX5) postdate oc_frontier (v399..v423), so they
have no official frontier entry; dominance is still checked against the 80
official rows.
4. Checks pass: sleeve r_s equals oc_tsmom to 5e-09; R2B1D17BF@0.25 reproduces
oc_tsmom combined monthly/DD exactly (0.0); monthly/total residual <= 5e-04pp.
5. The single stretch hit (R2B1D13BF@0.10: 5.068, 14.49) sits 0.51pp under the
DD<15 line on the understated grid (base grid itself is 14.09 vs official
14.98) and would likely fail on the official metric — descriptive only.

## One-line verdict

REPORTING ONLY: all 10 overlays add return (+0.10pp at 0.10x, +0.25pp at
0.25x) and DD (+0.2..+1.3pp) and nominally dominate >=1 official frontier
member on the understated daily grid, but only R2B1D13BF@0.10 touches stretch
(5.07 %/mo, DD 14.49) within the DD-convention caveat — a correlated add-on, not a diversifier.
