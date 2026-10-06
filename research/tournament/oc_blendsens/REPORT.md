# oc_blendsens REPORT: blend-weight SENSITIVITY of the deployed BOT book (no selection)

Book legs rebuilt exactly as `oc_dvolshort` (mirror of
`scripts/forward_v205.py::research_books_d2`): `o1` from
member_A/Aq_O1_orders + member_B/Bq_tv, `dmean = (D+Dq)/2`; blends
`w(alpha) = alpha*o1 + (1-alpha)*dmean`, alpha in {1.0 O1-only, 0.9,
0.8 deployed, 0.7, 0.0 D-only}. v410 bear filter FIRST (BTC 4h open <
rolling-1200 mean, min 600, inclusive; longs x0.5 in bear). Screen exactly
as oc_dvolshort structurally: grid = blend x opens_v154 inner join,
10955 bars (2021-09-24..2026-09-23 16:00 UTC; last bar dropped, no forward
open) x 5 coins = 54775 rows; `R1 = open[T+1]/open[T]-1`; net cell =
`wb*R1 - 0.0005*|wb-wprev|` per sym (first prev = 0, each blend its own
global chain; rate is the assigned 0.05%, oc_dvolshort used 0.0002).
Per-year equity reset to 1, compounded as `eq *= 1+sum_s pnl`; maxDD =
peak-to-trough; worst week = min 42-bar return. Full tables in
`results.json`; `panel.parquet` holds per-(T,sym) rows. Bear share on grid
0.466 (0.76 / 0.41 / 0.22 / 0.14 / 0.80 per year).

## Verdict

NOT a clean plateau (sensitivity, no selection): local steps through the
deployed 0.8/0.2 are MIXED in sign (E1/E2 same-sign 3/5, LOYO 2/5 — neither
meets the 4/5 + 4/5 default bar) and NOT small (mean adjacent step 0.0134
>= the pre-registered 0.01). The blend sits between two opposing extremes:
2024 rewards O1 (+0.033/step) while 2025 rewards D (-0.019/step).

## Per-year screen (net book P&L; costs included)

| year | O1 only | 0.9/0.1 | 0.8/0.2 deployed | 0.7/0.3 | D only | E1=08-07 | E2=09-08 | O1-D |
|---|---|---|---|---|---|---|---|---|
| 21-22 | 0.286853 | 0.283065 | 0.278895 | 0.274475 | 0.233097 | 0.004420 | 0.004170 | 0.053756 |
| 22-23 | 0.250934 | 0.243316 | 0.235444 | 0.227315 | 0.164147 | 0.008129 | 0.007872 | 0.086787 |
| 23-24 | 0.537109 | 0.540816 | 0.544150 | 0.546558 | 0.549035 | -0.002408 | -0.003334 | -0.011926 |
| 24-25 | 0.581674 | 0.549843 | 0.517693 | 0.484993 | 0.239283 | 0.032700 | 0.032150 | 0.342391 |
| 25-26 | 0.356557 | 0.375724 | 0.394724 | 0.414419 | 0.546894 | -0.019695 | -0.019000 | -0.190337 |

Same-sign: E1 3/5 (pos 3, neg 2), E2 3/5 (pos 3, neg 2), O1-D 3/5.
LOYO (strict sign of held-out vs mean of other 4): E1 2/5, E2 2/5, O1-D 2/5.
Mean adjacent step (|E1|+|E2|)/2 averaged over years = 0.0134.
Deployed rank by net each year: never best, never worst (always interior:
2021/2022/2024 O1-side wins, 2023/2025 D-side wins).

## Worst week per blend per year

| year | O1 | 0.9 | 0.8 | 0.7 | D |
|---|---|---|---|---|---|
| 21-22 | -0.054268 | -0.054778 | -0.055289 | -0.055801 | -0.059420 |
| 22-23 | -0.045771 | -0.046518 | -0.047268 | -0.048023 | -0.053495 |
| 23-24 | -0.071495 | -0.070485 | -0.069471 | -0.068479 | -0.062742 |
| 24-25 | -0.045296 | -0.045606 | -0.045930 | -0.046267 | -0.056683 |
| 25-26 | -0.075841 | -0.075570 | -0.075345 | -0.075124 | -0.073825 |

Read: worst week is flat across blends (<= 0.7pp spread every year).

## maxDD per blend per year (per-year reset paths)

| year | O1 | 0.9 | 0.8 | 0.7 | D |
|---|---|---|---|---|---|
| 21-22 | 0.083986 | 0.088099 | 0.092278 | 0.096643 | 0.130199 |
| 22-23 | 0.079492 | 0.076556 | 0.073721 | 0.070888 | 0.091903 |
| 23-24 | 0.097109 | 0.089987 | 0.087902 | 0.086323 | 0.077932 |
| 24-25 | 0.055233 | 0.060260 | 0.065296 | 0.070340 | 0.123478 |
| 25-26 | 0.089053 | 0.088083 | 0.087166 | 0.086269 | 0.089282 |

Full 5y path (context, compounded from year-1 start): maxDD O1 0.106606,
0.9 0.105548, 0.8 0.104644, 0.7 0.104086, D 0.130199; total net O1 2.013128,
0.9 1.992763, 0.8 1.970907, 0.7 1.947760, D 1.732455. Interior blends carry
the lowest full-path DD; D-only spikes DD in 2021 (0.130) and 2024 (0.123).

## Turnover / cost per blend per year (0.0005/unit; costs in net above)

| year | turnover O1/0.9/0.8/0.7/D | cost O1/0.9/0.8/0.7/D |
|---|---|---|
| 21-22 | 45.83/44.58/43.55/42.77/45.00 | 0.0229/0.0223/0.0218/0.0214/0.0225 |
| 22-23 | 57.86/56.29/55.23/54.59/61.47 | 0.0289/0.0281/0.0276/0.0273/0.0307 |
| 23-24 | 71.26/68.70/66.63/65.03/68.73 | 0.0356/0.0344/0.0333/0.0325/0.0344 |
| 24-25 | 77.08/74.60/72.81/71.63/80.67 | 0.0385/0.0373/0.0364/0.0358/0.0403 |
| 25-26 | 68.59/65.56/62.95/60.76/59.90 | 0.0343/0.0328/0.0315/0.0304/0.0300 |

## Caveats / post-hoc log

1. No post-hoc change to hypothesis, blends, bear filter, costs, grid, or
   the plateau rule. PLAN.md was written before `compute_blendsens.py` ran.
2. Code-only cleanups toward PLAN before running (not outcome-driven):
   removed a dead assert/no-op line, an unused variable, and a redundant
   turnover recompute (single global-chain computation kept).
3. Vectorised open-to-open screen only (no vol target, governor, dip
   sleeve, funding, SL/TP, or engine limit path); 0.0005/unit turnover on
   bear-filtered weights, each blend its own chain. Sensitivity only — no
   selection verdict; needs prospective validation (all five years were
   available when scored).

## One-line verdict

NOT a clean plateau (sensitivity, no selection): deployed 0.8/0.2 is always
interior (never best/worst) but local steps flip sign by year (3/5, LOYO
2/5) and average 0.0134 per 0.1 alpha — 2024 pulls toward O1, 2025 toward D.
