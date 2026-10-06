# oc_bookscale REPORT — book-weight x1.1 / x1.2 on R2B1D17BFG2 (2026-10-06)

DIAGNOSTIC / frontier exploration. No selection claim; any adoption would need
prospective paper evidence. POST-HOC MOTIVATED (labelled): oc_saturation found
the book leg the cheapest return per DD among levers (D20->D20B11 book x1.1:
+0.115 %/mo for +0.26 DD). Question: does a book scale keep 5y >= 5.0 under
S1 and S3 (where G2 + carry gives 4.70 / 4.72) with max yearly DD < 18?

## Setup

Rows (pre-registered PLAN.md): G2 (book_mult 1.0), G2B11 (ALL standard book
weights x1.1), G2B12 (x1.2), all else = v421 R2B1D17BFG2 wiring (B1 inv,
kd=1.7, risk budget 0.26*1.7=0.442, bear-book filter halves LONG targets,
G=2.0 gross cap, trade-mode books, win_start=5). `trade["book_mult"]` scales
the size target inside the engine (signal threshold uses the unscaled target;
commutes with the bear filter; same precedent as v407 R2B1D20B11). Caps and
the cross-margin budget UNCHANGED on every row. Scenarios: base (gate costs
maker 0.0002/taker 0.00055), S1 cost stress (maker 0.0004/taker 0.0012), S3
latency (win_start 30/sleeve_start 31), exactly as v421_audit/robust_v421.py.
Harness: 4 phases s=0..3, 2021-09-24..2026-09-23, reset-metric year_reset per
anchor year, v388.mix full-path DD; 36 legs sequential, each via heavy_slot
--tag oc_bookscale (per-leg cache runs/<ROW>_<CFG>_s<S>.pkl). Book-only P&L
share from engine attrib (per-bar book vs sleeve fractions, yearly sums
averaged over shifts, oc_saturation convention). Budget binds bounded via the
exits-first concurrent-notional sweep (engine emits no skip log; same
convention as oc_saturation sec 3). Carry: each row+scenario + f=0.25 by the
oc_carryfric/combine_carryd13 method UNCHANGED (frozen 33 trades, hourly
causal mark, S1 stressed drag 0.0044).

## Reproduction (gate)

G2/base reproduces v421 exactly: 5y 5.41 %/mo, max yearly DD 16.91,
full-path DD 16.82; per-shift equities bit-match (55.993/17.031/26.262/6.264).
G2/S1 and G2/S3 also match the v421 audit to the digit (checks gaps 0.0);
G2+carry f=0.25 matches oc_carryfric to the digit (4.696/4.717, gaps 0.0).
Proceeding was justified.

## Per row and scenario (reset-metric %/mo R / DD; 5y mean, worst, maxDD, fullDD, losing, book share)

| key | 2021 | 2022 | 2023 | 2024 | 2025 | 5y | worst | maxDD | fullDD | losing | book5y |
|---|---|---|---|---|---|---|---|---|---|---|---|
| G2/base | 2.588 / 10.86 | 3.282 / 16.91 | 6.045 / 15.81 | 10.677 / 8.27 | 4.648 / 12.90 | 5.410 | 2.588 | 16.91 | 16.82 | 0 | 0.461 |
| G2/S1 | 1.975 / 11.18 | 2.592 / 17.45 | 4.853 / 16.01 | 9.712 / 8.31 | 3.900 / 13.61 | 4.571 | 1.975 | 17.45 | 17.37 | 0 | 0.514 |
| G2/S3 | 2.070 / 11.85 | 2.476 / 17.32 | 4.346 / 16.03 | 9.798 / 8.36 | 4.380 / 12.75 | 4.578 | 2.070 | 17.32 | 17.24 | 0 | 0.454 |
| G2B11/base | 2.665 / 11.69 | 3.543 / 17.25 | 6.078 / 15.98 | 11.056 / 8.52 | 4.954 / 13.45 | 5.619 | 2.665 | 17.25 | 17.21 | 0 | 0.488 |
| G2B11/S1 | 2.068 / 12.04 | 2.599 / 17.64 | 5.196 / 16.10 | 10.078 / 8.60 | 4.097 / 14.35 | 4.769 | 2.068 | 17.64 | 17.49 | 0 | 0.532 |
| G2B11/S3 | 2.130 / 12.81 | 2.614 / 17.51 | 3.893 / 16.12 | 10.174 / 8.65 | 4.619 / 13.19 | 4.647 | 2.130 | 17.51 | 17.45 | 0 | 0.491 |
| G2B12/base | 2.668 / 12.76 | 3.571 / 17.62 | 6.115 / 16.32 | 11.222 / 8.98 | 5.124 / 14.04 | 5.698 | 2.668 | 17.62 | 17.52 | 0 | 0.501 |
| G2B12/S1 | 2.086 / 13.03 | 2.138 / 18.34 | 4.729 / 16.52 | 10.322 / 9.10 | 4.304 / 14.69 | 4.673 | 2.086 | 18.34 | 18.16 | 0 | 0.552 |
| G2B12/S3 | 2.096 / 13.54 | 2.518 / 18.04 | 4.301 / 16.58 | 10.197 / 9.06 | 4.661 / 14.20 | 4.715 | 2.096 | 18.04 | 18.70 | 0 | 0.495 |

Marginals over G2: B11 +0.209 / +0.34 DD at base, +0.198 / +0.19 under S1,
+0.069 / +0.19 under S3; B12 over B11 +0.079 / +0.37 at base, -0.096 / +0.70
under S1, +0.068 / +0.53 under S3. The friction gain shrinks while DD keeps
rising; x1.2 even loses return vs x1.1 under S1. Book share rises with the
mult (0.46 -> 0.49 -> 0.50 at base) as intended. No losing year anywhere.

## Each row + carry f=0.25 (oc_carryfric method; R_5y / maxDD / fullDD chained)

| key | 5y | worst | maxDD | fullDD | losing | carry lift pp |
|---|---|---|---|---|---|---|
| G2/base | 5.533 | 2.736 | 16.78 | 16.78 | 0 | +0.123 |
| G2/S1 | 4.696 | 2.118 | 17.31 | 17.31 | 0 | +0.125 |
| G2/S3 | 4.717 | 2.226 | 17.18 | 17.18 | 0 | +0.139 |
| G2B11/base | 5.741 | 2.811 | 17.12 | 17.12 | 0 | +0.122 |
| G2B11/S1 | 4.892 | 2.210 | 17.51 | 17.51 | 0 | +0.123 |
| G2B11/S3 | 4.788 | 2.284 | 17.38 | 17.38 | 0 | +0.141 |
| G2B12/base | 5.819 | 2.814 | 17.50 | 17.50 | 0 | +0.121 |
| G2B12/S1 | 4.799 | 2.189 | 18.20 | 18.85 | 0 | +0.126 |
| G2B12/S3 | 4.854 | 2.251 | 17.90 | 18.21 | 0 | +0.139 |

Carry adds +0.12-0.14pp everywhere and trims DD ~0.1pp (same honest lift as
oc_carryfric); it does not rescue the friction gap.

## Budget binds (caps unchanged: risk budget 0.442, G=2.0; pooled 4 shifts)

No liquidations anywhere (liq 0 on all 36 legs). Dip gross cap enforced:
max concurrent 2.0000 on every phase of every row/scenario. Near-cap
(C+w > 1.8) fills: 148-170 of ~21-22k fills (0.7-0.8%, weight share similar);
over-cap fills 0 everywhere by the exact list-order pairing (an early
time-sorted pairing build showed 2.0296 on one S3 leg and was fixed; see
caveats). Mean governor 0.93-0.97, slightly lower on scaled rows (more DD
feedback). The risk budget binds only in flush clusters as before; scaling
books does not move dip concurrency (fills/rungs counts flat across bm).

## Win rates (extra, pooled 4 shifts, audit-standard fees)

G2/base book 5064 / 0.5154, rung 21513 / 0.6858, all 0.6533 (matches the
v421 audit). Scaled rows keep the same profile within noise (B11 all 0.652,
B12 all 0.651; yearly tables in results.json). The overlay adds no trades.

## Plain answer

- G2B11 S1 alone 4.769 / 17.64, +carry 4.892 / 17.51; S3 alone 4.647 / 17.51,
  +carry 4.788 / 17.38. DD < 18 holds, but 5y >= 5.0 fails in all four.
- G2B12 S1 alone 4.673 / 18.34, +carry 4.799 / 18.20; S3 alone 4.715 / 18.04,
  +carry 4.854 / 17.90. 5y >= 5.0 fails in all four, and DD < 18 fails three
  of four (only S3+carry scrapes under at 17.90 while still missing return).
- verdict: NO for G2B11 (alone false, with_carry false) and NO for G2B12
  (alone false, with_carry false). A book scale does NOT keep 5y >= 5.0
  under S1 and S3 with max yearly DD < 18, with or without carry f=0.25.

VERDICT: NO — diagnostic only, no selection claim; any adoption would need
prospective paper evidence.

## Caveats / post-hoc log

1. Pairing fix logged: the first G2/S3/s1 build paired rungs time-sorted and
   read max concurrent 2.0296 (over the hard cap); re-pairing in exact engine
   list order (fill immediately followed by its exit) gives 2.0000 with
   identical equities. All 12 prior legs were rerun with the fixed pairing;
   all 36 caches are post-fix.
2. Book share is flow attribution (attrib fractions summed per year,
   averaged over shifts), not geometric R; only shares are interpreted.
3. Combined carry DD is the chained-reset convention (labelled), and carry
   marks are hourly-close (lower bound on the carry leg); S1 uses stressed
   carry costs exactly as oc_carryfric.
4. All five years are research data; S1/S3 are the published friction set.
   Repro: research/diagnostics/oc_bookscale/{PLAN.md, oc_bookscale.py,
   results.json, runs/}; test tests/test_oc_bookscale.py.
