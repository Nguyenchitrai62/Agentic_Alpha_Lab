# oc_bookcoinwf REPORT: walk-forward per-coin book gating (idea #38)

Book = `forward_v205.research_books_d2` (rebuilt exactly as oc_dvolshort,
cell-checked formula); opens = v154 4h opens. Grid = 10955 bars
(2021-09-24..2026-09-23 16:00 UTC; last bar dropped, no forward open) x 5
coins = 54775 rows. Screen = open-to-open 4h returns with the assigned
0.0005/unit turnover cost: net cell = `w*R1 - 0.0005*|w - w_prev|` per sym
(first prev = 0; gated path uses its own gated prev, so dropping a coin
pays one unwind turnover at the year boundary). Rule (fixed in PLAN.md):
for year `Y_k`, trade only coins with cumulative book P&L over ALL grid
bars `T < A_k - 7d` (from 2020-08) strictly positive; year 1 history is
empty (books start exactly at `A_0`) and falls back to the full book.
Equity per year reset to 1, `eq *= 1 + sum_s pnl`; maxDD = peak-to-trough;
worst week = min 42-bar compounded return. Full tables in `results.json`;
`panel.parquet` holds per-(T,sym) rows. Note: cost here is the assigned
0.0005 (oc_dvolshort's code was reused structurally but it used 0.0002).

## Verdict

PROMISING as assigned (5/5 P&L-not-lower, 5/5 DD-not-worse) but VACUOUS:
the gate never binds — every coin's history P&L is positive at every
anchor, so gated weights equal full weights in all 5 years (identical
paths, zero turnover saved, zero DD change).

## Per-coin history and gated sets (net, portfolio-return units)

| anchor year | hist BNB / BTC / ETH / SOL / XRP (all data before anchor-7d) | gated coins |
|---|---|---|
| 2021-09-24 | (empty history -> fallback) | all 5 |
| 2022-09-24 | 0.0693 / 0.0623 / 0.0239 / 0.0933 / 0.0328 | all 5 |
| 2023-09-24 | 0.0698 / 0.1898 / 0.0744 / 0.1307 / 0.1284 | all 5 |
| 2024-09-24 | 0.1659 / 0.3628 / 0.2083 / 0.2230 / 0.1792 | all 5 |
| 2025-09-24 | 0.2760 / 0.4912 / 0.2701 / 0.2317 / 0.3957 | all 5 |

Every history sum is > 0, so no coin is ever excluded.

## Per-coin per-year book P&L, full (= gated) (net)

| year | BNB | BTC | ETH | SOL | XRP | total |
|---|---|---|---|---|---|---|
| 21-22 | 0.068665 | 0.063310 | 0.025551 | 0.091176 | 0.044236 | 0.292937 |
| 22-23 | 0.001001 | 0.122922 | 0.048742 | 0.032004 | 0.083985 | 0.288653 |
| 23-24 | 0.103768 | 0.170786 | 0.126340 | 0.091536 | 0.050933 | 0.543362 |
| 24-25 | 0.114392 | 0.116898 | 0.068300 | 0.015416 | 0.220038 | 0.535045 |
| 25-26 | 0.137770 | 0.105710 | 0.105501 | 0.049924 | 0.053189 | 0.452094 |

All 25 coin-years are positive (weakest: BNB 22-23 +0.0010, SOL 24-25
+0.0154). Gated per-coin values are identical (excluded coins would show
only a boundary unwind cost, but there are none).

## Gated vs full book path per year (net; identical)

| year | total P&L ungated / gated | worst week ungated / gated | maxDD ungated / gated | P&L not lower | DD not worse |
|---|---|---|---|---|---|
| 21-22 | 0.292937 / 0.292937 | -0.103662 / -0.103662 | 0.138415 / 0.138415 | yes (equal) | yes (equal) |
| 22-23 | 0.288653 / 0.288653 | -0.047268 / -0.047268 | 0.072336 / 0.072336 | yes (equal) | yes (equal) |
| 23-24 | 0.543362 / 0.543362 | -0.069033 / -0.069033 | 0.086739 / 0.086739 | yes (equal) | yes (equal) |
| 24-25 | 0.535045 / 0.535045 | -0.045930 / -0.045930 | 0.065296 / 0.065296 | yes (equal) | yes (equal) |
| 25-26 | 0.452094 / 0.452094 | -0.069603 / -0.069603 | 0.079810 / 0.079810 | yes (equal) | yes (equal) |

Counts: P&L not lower 5/5; DD not worse 5/5 (all by equality). Full 5y
path (context, compounded from year-1 start): total P&L 2.112092 both
paths; maxDD 0.138415 both paths.

## Caveats / post-hoc log

1. No post-hoc change to hypothesis, definitions, gate, costs, or the
   decision rule. PLAN.md was written before `compute_bookcoinwf.py` ran.
2. The PASS is vacuous by equality: with a strict `> 0` history rule and
   all-positive coin histories, the gate is a no-op. A threshold above
   zero (or a relative-rank rule) would be needed for the gate to bind,
   but that would be a new pre-registered variant, not added here.
3. Vectorised open-to-open screen only (no vol target, governor, dip
   sleeve, funding, SL/TP, or engine limit path); 0.0005/unit turnover on
   undrifted weights (first bar vs flat 0; boundary turnover carried
   across years on each path's own chain). In-sample walk-forward style
   (gates strictly pre-anchor with a 7d embargo, but all five years were
   available when the idea was scored); needs prospective validation.

## One-line verdict

PROMISING as assigned (5/5 P&L not lower, 5/5 DD not worse) but VACUOUS — the positive-history gate never excludes any coin, so gated and full books are identical.
