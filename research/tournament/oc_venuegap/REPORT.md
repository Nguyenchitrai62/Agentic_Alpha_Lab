# oc_venuegap REPORT (2026-10-06; PLAN pre-registered before any outcome)

## Setup
Venue-native B1 replica per venue (static bid at `lv = O(T)*(1-k*sg(T))`,
STRICT `low < lv` fill on offsets 16..238, D0 exits from the fill price,
maker 0.0002 / taker 0.00055, longs pay 0.0001 on settling timeouts;
`n` detector venue-native). Binance 1m
(`data/raw/btc_intraday_20260924`, `data/raw/majors_intraday_20260924`) vs
the S5 store (`data/raw/bybit_linear_1m_20261004`, as in
`v411_audit/robust_v411.py`). Overlap = bar open T in [2021-11-15,
2026-09-24) (S5 start; Y0 short window). 53,220 paired bars/coin
(10,644 x 5), 25 coin x depth cells, 5,430 Binance vs 5,408 Bybit kept
fills. Years by exit date. All five years are research data: findings need
prospective validation.

## 1. Yearly rung P&L gap (equal-weight sum of net y; size-weighted side row)
| year | n bin/byb | sum bin | sum byb | gap (bin-byb) | gap_w (size-wtd) | TP bin/byb |
|---|---|---|---|---|---|---|
| 2021* | 922/921 | 3.388 | 3.105 | +0.283 | +0.460 | .524/.524 |
| 2022 | 1045/1029 | 0.393 | 0.320 | +0.073 | -0.094 | .543/.538 |
| 2023 | 1330/1322 | 5.276 | 5.128 | +0.148 | -0.089 | .636/.636 |
| 2024 | 989/989 | 4.066 | 4.093 | -0.027 | +0.082 | .554/.560 |
| 2025 | 1144/1147 | 1.538 | 1.498 | +0.040 | +0.101 | .512/.510 |
| TOTAL | 5430/5408 | 14.662 | 14.145 | **+0.516** | +0.460 | .558/.558 |
\*Y0 short window from 2021-11-15. Gap = +3.6% of Bybit rung P&L; per-year
gaps are <= 0.28 against yearly sums of 0.3-5.3 (sign flips in 2024).

## 2. Per-coin x depth: fills agree, TP agrees, no depth carries a big gap
Both-fill dominates every cell (e.g. BTC 2.5: 430 both vs 9 bin-only vs 13
byb-only; deepest 5.0: 49-72 both vs <=9 single); single-venue fills are
2-5% of rungs. Paired exit agreement: both-TP 40-82% by depth, TP split
disagreement only ~1-3% of paired rungs. Mean trade-through depth differs by
<= 7 bps (Binance deeper in 19/25 cells, e.g. SOL 5.0: 122.6 vs 113.1 bps).
Largest cell P&L gaps (5-year sums): XRP 3.0 +0.305, SOL 2.5 -0.234,
ETH 2.5 -0.224, XRP 2.5 +0.172, BNB 3.0 +0.169; all other cells |gap| <= 0.15.

## 3. Per-coin-year gap (bin-byb equal-weight sums)
| year | BTC | ETH | SOL | BNB | XRP |
|---|---|---|---|---|---|
| 2021* | +0.049 | +0.012 | +0.104 | +0.080 | +0.039 |
| 2022 | -0.028 | -0.116 | -0.143 | +0.112 | +0.248 |
| 2023 | -0.069 | +0.175 | -0.223 | -0.023 | +0.287 |
| 2024 | +0.025 | +0.071 | -0.061 | +0.110 | -0.172 |
| 2025 | -0.015 | -0.211 | +0.046 | +0.069 | +0.151 |
| 5y | -0.038 | -0.069 | -0.277 | +0.348 | **+0.553** |
XRP is positive in 4/5 years and sums to +0.553 ≈ the entire +0.516 total
gap; every other coin nets ~0 over 5 years. No coin shows a large,
same-sign-every-year drag.

## 4. 4h-open / rung-level shift (the mechanical shifter)
Median open diff (byb-bin): BTC +0.01, ETH -0.17, SOL +0.32, BNB -3.59,
XRP 0.00 bps; mean |open| diff: 1.5/1.5/2.4/5.2/2.2 bps. Median level diff
at k=2.5: -0.18/-0.72/-0.38/-4.07/+0.68 bps. BNB has the largest basis
(median -3.6 bps) yet its 5y gap is only +0.35 with flipping yearly signs,
so the level shift does not convert into P&L. Coverage is perfect: all
10,644 bars/coin tradeable on both venues (Bybit sigma history suffices
from 2021-11-15, SOL included).

## Notes
- Replica check: Binance B1 fills 5,430 over the overlap vs oc_b1deeper B1
  5,498 over [2021-09-24, 2026-09-24) (difference = the 7 pre-overlap
  weeks) — replica consistent.
- Caveats: B1 base (kd=1) without the deployment kd=1.7/budget/bear-filter
  scaling (scales both venues ~equally); rung-y sums are not portfolio
  %/month and cannot be subtracted from the S5 engine drag directly; exits
  use each venue's own tape (venue-native, as S5 does).
- Repro: `research/tournament/oc_venuegap/{PLAN.md,venue.py,run.py,
  results.json,fills.parquet}` + `tests/test_oc_venuegap.py` (10 pass);
  one process, peak RAM ~0.6 GB.

## Verdict
VERDICT: XRP rungs carry the whole (small) dip-ladder venue gap (+0.55 of +0.52 total) but routing just XRP dip rungs to Binance would recover only ~4% of rung P&L and cannot explain the ~0.4-0.5 %/month S5 drag, so the S5 venue gap must live overwhelmingly in the BOOK leg, not the dip ladder — a book-leg Binance-vs-Bybit replay is the needed follow-up.
