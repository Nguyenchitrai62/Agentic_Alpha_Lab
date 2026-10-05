# oc_lots REPORT — Bybit small-account feasibility of R2B1D17BF, phase s=0 (2026-10-05; PLAN pre-registered before any outcome)

## Setup
Inputs: research/tournament/oc_ddanat17/events_s0.parquet (20183 events) +
rungs_s0.parquet (5466 dip rungs), one causal engine phase s=0, live
2021-09-24..2026-09-23+12h. Book orders = 2325 `order_issue` with |weight|>0
(sensitivity: 1312 `book_fill`); dip rungs = 5466 rows. Phase equity E = A/4
(one sub-book per clock) for A = 1000/2000/5000/10000/20000 USDT. Lot rules
fetched LIVE from Bybit /v5/market/instruments-info: BTC 0.001 / ETH 0.01 /
SOL 0.1 / BNB 0.01 / XRP 0.1, step = min, min notional 5 USDT (all majors).
Placeable iff floor(qty/step)*step >= minQty AND floored-notional >= 5 USDT.
Repro: research/diagnostics/oc_lots/{PLAN.md,run_oc_lots.py,results.json}.
All five years are research data; findings need prospective validation.

## Overall placeable share (count / notional) per account
| A (E=A/4) | book orders (n=2325) | book fills (n=1312) | dip rungs (n=5466) |
|---|---|---|---|
| 1000 (250) | 0.605 / 0.656 | 0.614 | 0.653 / 0.826 |
| 2000 (500) | 0.799 / 0.829 | 0.806 | 0.806 / 0.919 |
| 5000 (1250) | 0.962 / 0.974 | 0.962 | 0.940 / 0.984 |
| 10000 (2500) | 1.000 / 1.000 | 1.000 | 0.984 / 0.997 |
| 20000 (5000) | 1.000 / 1.000 | 1.000 | 0.996 / 1.000 |

## Per-coin count share (book / rung) per account
| A | BTC | ETH | SOL | BNB | XRP |
|---|---|---|---|---|---|
| 1000 | 0.101 / 0.216 | 0.230 / 0.436 | 0.707 / 0.718 | 1.000 / 0.915 | 1.000 / 0.942 |
| 2000 | 0.319 / 0.446 | 0.712 / 0.669 | 0.993 / 0.927 | 1.000 / 0.979 | 1.000 / 0.992 |
| 5000 | 0.816 / 0.762 | 1.000 / 0.936 | 1.000 / 0.997 | 1.000 / 1.000 | 1.000 / 1.000 |
| 10000 | 0.998 / 0.924 | 1.000 / 0.993 | 1.000 / 1.000 | 1.000 / 1.000 | 1.000 / 1.000 |
| 20000 | 1.000 / 0.983 | 1.000 / 0.997 | 1.000 / 1.000 | 1.000 / 1.000 | 1.000 / 1.000 |

## Share of simulated P&L carried by placeable orders/rungs (net / gross)
| A | dip net / gross | book net / gross (FIFO, approx) |
|---|---|---|
| 1000 | 0.895 / 0.853 | 0.796 / 0.792 |
| 2000 | 0.959 / 0.935 | 0.821 / 0.938 |
| 5000 | 0.995 / 0.988 | 1.000 / 0.998 |
| 10000 | 1.000 / 0.998 | 1.000 / 1.000 |
| 20000 | 1.000 / 1.000 | 1.000 / 1.000 |

## Per-anchor-year count share (descriptive; book / rung)
| year | n book/rung | A=1000 | A=2000 | A=5000 | A=10000 | A=20000 |
|---|---|---|---|---|---|---|
| 21-09-24..22-09-23 | 346 / 967 | 0.590 / 0.687 | 0.766 / 0.830 | 1.000 / 0.961 | 1.000 / 0.995 | 1.000 / 0.996 |
| 22-09-24..23-09-23 | 430 / 1045 | 0.788 / 0.780 | 0.979 / 0.941 | 1.000 / 1.000 | 1.000 / 1.000 | 1.000 / 1.000 |
| 23-09-24..24-09-23 | 481 / 1332 | 0.624 / 0.673 | 0.771 / 0.805 | 0.973 / 0.935 | 1.000 / 0.991 | 1.000 / 0.999 |
| 24-09-24..25-09-23 | 541 / 987 | 0.486 / 0.620 | 0.754 / 0.804 | 0.930 / 0.945 | 0.998 / 0.984 | 1.000 / 1.000 |
| 25-09-24..26-09-23 | 527 / 1135 | 0.571 / 0.514 | 0.746 / 0.665 | 0.928 / 0.870 | 1.000 / 0.952 | 1.000 / 0.986 |

## Caveats
- Book P&L is FIFO-matched in weight-fraction units (entry book_fill/book_add
  vs exits, fills inherit their order_issue's placeability, 0 unmapped fills);
  weights are fractions of then-equity over a 58x compounding path, so the
  book net/gross shares are approximate; leftover unmatched entry 77.5 vs exit
  0.01 fraction units disclosed in results.json. Dip P&L uses the engine's own
  rungs_s0.loss (same convention as oc_ddanat17).
- Post-hoc change logged: notional-share cross-check columns added to the
  script after the first run (no definition change; counts/P&L rules as planned).
- Single phase s=0 only; other clocks may differ slightly; no PROMISING claim
  (deployment note, no rule).

## Verdict
VERDICT: R2B1D17BF phase s=0 needs a 20000 USDT account (5000/phase) for >=99%
placeability of both book orders (100%) and dip rungs (99.6%, gross P&L ~100%);
below that the bottleneck is BTC (at 1000 USDT: book 10%, rungs 22%) then ETH,
while BNB/XRP books are placeable at every size — so small accounts cannot
deploy the pick as simulated.
