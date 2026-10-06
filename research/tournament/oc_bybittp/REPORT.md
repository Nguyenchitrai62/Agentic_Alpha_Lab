# oc_bybittp REPORT (2026-10-06; PLAN pre-registered before any outcome)

## Setup
Venue-native B1 replica per venue (static bid at `lv = O(T)*(1-k*sg(T))`,
STRICT `low < lv` fill on offsets 16..238, D0 exits from the fill price,
maker 0.0002 / taker 0.00055, longs pay 0.0001 on settling timeouts).
Binance 1m vs the S5 Bybit store (`data/raw/bybit_linear_1m_20261004`).
Overlap = bar open T in [2021-11-15, 2026-09-24), majors x R2 depths
(2.5/3/3.5/4/5), standard 4h grid. 53,220 paired bars, 5,430 Binance vs
5,408 Bybit kept fills (tick-identical to oc_venuegap: gap +0.516 rung-y,
TP 55.80/55.79% — replica validated), 5,245 both-fill rungs with both exits
kept. All five years are research data: findings need prospective validation.

## 1. Divergent-TP rungs are rare and symmetric — no Bybit shortfall in B1
| coin | both-fill | both-TP | bin-only-TP | byb-only-TP | neither-TP |
|---|---|---|---|---|---|
| BTC | 1013 | 510 | 8 | 15 | 480 |
| ETH | 1084 | 547 | 11 | 18 | 508 |
| SOL | 912 | 489 | 12 | 13 | 398 |
| BNB | 1118 | 576 | 13 | 12 | 517 |
| XRP | 1118 | 689 | 13 | 21 | 395 |
| ALL | 5245 | 2811 (53.6%) | 57 (1.1%) | 79 (1.5%) | 2298 (43.8%) |
Bybit has MORE solo TPs than Binance (79 vs 57) in every coin except BNB
(12 vs 13). Single-venue-fill TPs (fill-gap, not near-miss): BTC 30/30,
ETH 31/21, SOL 29/27, BNB 38/27, XRP 34/22 (bin/byb) — again no Bybit
shortfall. Per-year bin-only counts never exceed 5 in any coin-year. The
deployment's -34/-59 Bybit TP shortfall (oc_bookvenue) does NOT reproduce
in the static-B1 replica: it needs the deployment dips (kd 1.7 corr sizing,
risk budget, learned R2 sizes/TPs, venue-open timeouts).

## 2. Near-miss distance (miss_bps on the NON-TP venue's own tape vs its own TP)
| coin.dir | n | median | p25/p75 | <=1/2/3/5/10/25 bps | neg* |
|---|---|---|---|---|---|
| BTC.bin-only | 8 | 6.2 | 1.0/14.8 | 13/38/38/38/62/88% | 0% |
| ETH.bin-only | 11 | 10.3 | 1.6/137.1 | 27/27/36/45/45/55% | 9% |
| SOL.bin-only | 12 | 5.4 | -57.0/84.6 | 33/33/50/50/58/67% | 25% |
| BNB.bin-only | 13 | 3.4 | 0.9/47.8 | 31/46/46/54/54/62% | 15% |
| XRP.bin-only | 13 | 14.2 | 0.6/79.0 | 31/38/38/38/46/62% | 15% |
| ALL.bin-only | 57 | 7.0 | 0.7/79.0 | 28/37/42/46/53/65% | 14% |
| ALL.byb-only | 79 | 17.1 | 1.4/62.6 | 22/28/32/35/43/54% | 6% |
\*neg = high DID exceed TP but exit was stop-first (backstop tied/earlier).
Only ~1/4-1/3 of misses sit within 1-2 bps; median miss is 3-14 bps per
coin (7.0 pooled). Half the misses are >5 bps away — not all "near".

## 3. What the miss became (non-TP side exit split)
ALL bin-only (Bybit side): time 84.2%, stop 10.5%, backstop 5.3%.
ALL byb-only (Binance side): time 91.1%, stop 6.3%, backstop 2.5%.
Per coin: BTC 100% timeout both directions; ETH 91/94% timeout; SOL 75/69%
timeout (rest stops); BNB 77% timeout (+1 backstop); XRP ~70-80% timeout.
Timeouts dominate as hypothesised, but ~15% are stops/backstops a tighter
TP cannot always front-run (needs the exact replay in §4, which handles it).

## 4. TP-inside offsets: Bybit recovery vs Binance cost (exact replay)
| coin | d=1 | d=2 | d=3 | d=5 | (recovered / 57 bin-only; Binance shave) |
|---|---|---|---|---|---|
| BTC (n=8) | 1 (13%) | 3 (38%) | 3 (38%) | 3 (38%) | shave d bps, 100% retained |
| ETH (n=11) | 2 (18%) | 2 (18%) | 3 (27%) | 4 (36%) | same |
| SOL (n=12) | 1 (8%) | 1 (8%) | 3 (25%) | 3 (25%) | same |
| BNB (n=13) | 2 (15%) | 4 (31%) | 4 (31%) | 5 (38%) | same |
| XRP (n=13) | 2 (15%) | 3 (23%) | 3 (23%) | 3 (23%) | same |
| ALL | 8 (14%) | 13 (23%) | 16 (28%) | 18 (32%) | shave 1.0/2.0/3.0/5.1 bps |
Binance base TPs (n=2868 paired): 100.0% stay TP at every offset on EVERY
coin — the cost is purely the shave: -1.01/-2.03/-3.04/-5.07 bps per kept
TP. Symmetric Bybit side: 100% stay TP, same shave; byb-only recovery on
Binance 15/22/25/29%. Side effect (NOT venue-specific): tighter TPs also
manufacture TPs from paired non-TPs — Binance converts 32/56/77/105 of
2377 non-TPs (1.3/2.4/3.2/4.4%) vs 8/13/16/18 recovered on Bybit; at d=5 the
Binance bonus (105) is ~6x the Bybit recovery (18).

## Notes
- Miss uses each venue's OWN tape and OWN TP (venue-native, as S5 does);
  paired year = Binance-exit year (mismatched exit-year pairs are negligible:
  exits land within the bar). Coverage perfect: 10,644/10,644 bars tradeable
  on both venues per coin.
- Repro: `research/tournament/oc_bybittp/{PLAN.md,core.py,run.py,
  results.json,fills.parquet,paired.parquet}` + `tests/test_oc_bybittp.py`
  (11 pass); one process, peak RAM ~0.6 GB.
- Caveats: B1 base (no kd=1.7/budget/bear-filter/R2-size scaling); rung-y
  sums are not portfolio %/month; offsets are hypothesis arithmetic only.

## Verdict
VERDICT: divergent B1 TPs are near-misses that mostly become timeouts (84%),
but only ~1/3 sit within 5 bps and Bybit shows no TP shortfall to fix (79
solo TPs vs 57 on Binance), so a 5-bps-inside TP — the best of the four,
recovering 18/57 (32%) at a 5.1 bps shave per kept TP — is NOT a venue fix:
it manufactures ~6x more new Binance TPs (105) than Bybit recoveries, and is
kept as a hypothesis for a later pre-registered test only.
