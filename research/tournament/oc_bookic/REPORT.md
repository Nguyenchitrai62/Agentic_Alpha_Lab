# oc_bookic — REPORT: where does the BOT book earn and lose (5y gross)

Book = `forward_v205.research_books_d2` (rebuilt exactly); opens = v154 4h
opens. Metric = `w[t] x (open[t+1]/open[t]-1)`, gross, NO costs, before vol
target/governor/sleeve. Full tables in `results.json`.

## 1. Per anchor year: gross P&L, long vs short leg (5 coins summed)

| year | bars | total | long | short |
|---|---|---|---|---|
| 2021-09-24 | 2190 | +0.3205 | +0.1780 | +0.1425 |
| 2022-09-24 | 2190 | +0.3184 | +0.2903 | +0.0281 |
| 2023-09-24 | 2196 | +0.5776 | +0.6153 | **-0.0378** |
| 2024-09-24 | 2190 | +0.5717 | +0.5217 | +0.0501 |
| 2025-09-24 | 2189 | +0.4905 | +0.3057 | +0.1848 |
| 5y | 10955 | **+2.2787** | +1.9111 | +0.3677 |

No losing year gross; the ONLY negative (year x leg) cell is the 2023 short
leg (-0.0378: SOL short -0.0445, BNB short -0.0265, BTC short -0.0175).

## 2. Spearman IC of weight vs next-42-bar return, per (year, coin)

| year | BNB | BTC | ETH | SOL | XRP |
|---|---|---|---|---|---|
| 2021 | +0.22 | +0.12 | +0.14 | +0.08 | +0.08 |
| 2022 | -0.05 | -0.02 | -0.07 | +0.07 | -0.08 |
| 2023 | -0.00 | +0.09 | +0.07 | +0.02 | -0.02 |
| 2024 | +0.16 | +0.02 | +0.15 | -0.04 | +0.13 |
| 2025 | +0.14 | +0.04 | +0.16 | +0.07 | +0.13 |

Weak but mostly positive 7-day IC; negative patch in 2022 (BNB/ETH/XRP).
5y gross per coin: BTC +0.62, XRP +0.48, BNB +0.46, ETH +0.40, SOL +0.30 —
no coin is a 5y loss carrier.

## 3. Regimes (5y): BTC-trend and BTC-vol splits of the same gross P&L

| split | group A | group B |
|---|---|---|
| trend | above +1.758 | below +0.521 |
| vol | low +1.498 | high +0.781 |

Both regimes earn over 5y; below-trend and high-vol contribute
disproportionately little. Worst cells: 2021 BTC below-trend (-0.021) and
2021 BTC high-vol (-0.020); 2024 BNB high-vol (-0.040, offset by +0.163 low-vol).

## 4. Drawdown windows (gross book P&L, per coin + total)

| window | bars | total | BNB | BTC | ETH | SOL | XRP |
|---|---|---|---|---|---|---|---|
| W1 2022-07-20..2022-11-10 | 684 | -0.0373 | +0.0337 | **-0.0708** | +0.0273 | **-0.0422** | +0.0146 |
| W2 2023-04-17..2023-06-14 | 354 | -0.0483 | **-0.0297** | -0.0088 | **-0.0237** | +0.0093 | +0.0045 |
| W3 2022-01-13..2022-01-22 | 60 | **-0.0778** | -0.0205 | -0.0024 | **-0.0352** | -0.0199 | +0.0002 |
| W4 2024-01-03 (1 day) | 6 | -0.0154 | +0.0007 | -0.0080 | -0.0020 | -0.0050 | -0.0010 |

ALL four windows lose despite every full year winning: W3 (Jan-2022 crash,
-0.078 in 10 days, led by ETH) is the sharpest per-bar; W1 is carried by
BTC+SOL shorts-longs mistiming; W2 by BNB+ETH.

## Verdict (one line)

**The book has no 5y-negative leg/regime/coin — its losses concentrate in the
2023 short leg (-0.038, the only negative year-leg) and in all four drawdown
windows (sharpest: W3 Jan-2022 crash, -0.078 in 10 days led by ETH; W1 led by
BTC/SOL), i.e. shorts and crash bars, not any one coin or the below-trend /
high-vol regime on average.**

## Proposed (NOT tested) follow-ups — at most 2, with economic reason

1. **Crash-brake**: force book weights toward flat for a fixed N bars after a
   large broad-market down bar/day (W3-type). Reason: forced-liquidation
   cascades make near-term returns run against a slow momentum book (it adds
   into the falling knife / covers into the squeeze).
2. **Short-gate in high-vol downtrends**: scale down (not up) short weights
   when BTC is below its 1200-bar mean AND trailing-30d vol is above its 1y
   median. Reason: bear-market relief rallies are the fastest, most-shorted
   moves — short losses are unbounded while the edge (IC) is weakest exactly
   there (2022 IC patch, 2023 short leg).

Caveats: gross vectorised P&L only (no spread/fees/funding, no vol target,
governor, SL/TP, sleeve, or compounding); timing is next-4h-bar open-to-open,
not the engine's limit-fill path; windows/regimes were inspected on the same
5y, so any rule above must be judged walk-forward on pre-anchor data only.
