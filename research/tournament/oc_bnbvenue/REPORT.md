# oc_bnbvenue REPORT (2026-10-06; PLAN pre-registered before any outcome)

DIAGNOSTIC (no rule, no PROMISING verdict). Question: BNB's Bybit top-of-book
is ~10x Binance's while BTC/ETH/SOL/XRP match — how much of the
Bybit-vs-Binance drag is BNB, book vs dip leg, and what would BNB-on-Bybit
(a)/(b)/(c) do to the deployment 5y, as a hypothesis only.
Method: read ONLY six published `results.json` aggregates (no 1m, no engine
runs, one process, stdlib json): `oc_topbook`, `research/diagnostics/
oc_bookvenue` (the assignment's `research/tournament/oc_bookvenue` path does
not exist — substitution logged in PLAN.md), `oc_venuegap`, `oc_bybittp`,
`oc_contrib`, `oc_kpi_g2`. Deployment = R2B1D17BFG2 (G2: 5y net +2538.7%,
eq 26.3874x, DD gate 16.82; R5 ~= 5.61 %/month over 60 anchor-months); BOT
book = `forward_v205.research_books_d2` (reference only, via
`r2_decompose5.py`, not executed). All five years are research data; findings
need prospective validation. Repro: `PLAN.md`, `compute_bnbvenue.py` ->
`results.json` (this file renders it) + `tests/test_oc_bnbvenue.py`.

## 1. Top-of-book spread: only BNB differs (oc_topbook pooled means)
| coin | binance mean | bybit mean | bybit/binance | extra (byb-bin) |
|---|---|---|---|---|
| BTC | 0.0120 | 0.0118 | 0.98 | -0.00 bps |
| ETH | 0.0371 | 0.0370 | 1.00 | -0.00 bps |
| SOL | 0.8279 | 0.8277 | 1.00 | -0.00 bps |
| BNB | 0.1269 | 1.2677 | 9.99 | +1.14 bps/side |
| XRP | 0.6633 | 0.6632 | 1.00 | -0.00 bps |
BNB pays ~1.14 bps extra spread per side on Bybit (~2.3 bps round-trip on a
market fill); a maker limit fill earns, not pays, half of it, so the per-book-
fill bound is ~1 bps, not a portfolio drag until multiplied by fills.

## 2. Dip leg, B1 replica rung-y sums (oc_venuegap, bin-byb; NOT %/month)
| coin | 5y gap | share of net +0.516 | yearly gaps 21/22/23/24/25 |
|---|---|---|---|
| BTC | -0.038 | -7% | +0.049/-0.028/-0.069/+0.025/-0.015 |
| ETH | -0.070 | -14% | +0.012/-0.116/+0.175/+0.071/-0.211 |
| SOL | -0.277 | -54% | +0.104/-0.143/-0.223/-0.061/+0.046 |
| BNB | +0.348 | +67% | +0.080/+0.112/-0.023/+0.110/+0.069 |
| XRP | +0.553 | +107% | +0.039/+0.248/+0.287/-0.172/+0.151 |
| TOTAL | +0.516 | 100% | +0.283/+0.073/+0.148/-0.027/+0.040 |
BNB dip gap is positive in 4/5 years but small: +0.348 units = 2.5% of Bybit
rung P&L (0.348/14.145); XRP alone (+0.553) exceeds the net gap while
SOL/ETH/BTC net negative. BNB depth cells: 3.0 +0.169 carries ~half the BNB
gap; 2.5 +0.063, 4.0 +0.098, 3.5 +0.005, 5.0 +0.014. Scale anchor: the whole
B1 5y gap (+0.516) is 3.6% of Bybit rung P&L — the B1 dip ladder is almost
venue-insensitive, so BNB's B1 share is 67% of a small number.

## 3. Divergent TPs are NOT a BNB story (oc_bybittp, both-fill rungs)
| coin | both-fill | both-TP | bin-only | byb-only | single-venue TP bin/byb |
|---|---|---|---|---|---|
| BTC | 1013 | 510 | 8 (14%) | 15 (19%) | 30/30 |
| ETH | 1084 | 547 | 11 (19%) | 18 (23%) | 31/21 |
| SOL | 912 | 489 | 12 (21%) | 13 (16%) | 29/27 |
| BNB | 1118 | 576 | 13 (23%) | 12 (15%) | 38/27 |
| XRP | 1118 | 689 | 13 (23%) | 21 (27%) | 34/22 |
| ALL | 5245 | 2811 | 57 | 79 | — |
Bybit has MORE solo TPs than Binance overall (79 vs 57); BNB is symmetric
(13 vs 12). BNB carries 23% of bin-only misses and 15% of byb-only — no
excess. The deployment TP shortfall (-34/-59 TPs, §4) does NOT reproduce in
this static replica (needs kd 1.7/budget/R2-size/venue-open timeouts), so no
BNB-venue TP fix can be read off this table.

## 4. Book leg, deployment engine (oc_bookvenue s=0/s=2, single-phase %/month)
| phase | base | s5 (Bybit) | gap | book eff (c-a) | dip eff (d-a) | residual |
|---|---|---|---|---|---|---|
| s=0 | 7.054 / DD 19.9 | 6.781 / 19.97 | -0.273 | +0.005 (-2% of gap) | -0.153 (56%) | -0.125 |
| s=2 | 5.620 / DD 29.11 | 4.972 / 31.03 | -0.648 | -0.100 (15%) | -0.484 (75%) | -0.064 |
Book execution is venue-identical: fills +2/+14 MORE on Bybit (rates
30.27->30.48% s0, 29.91->30.26% s2, +0.21/+0.35pp); stops differ by <=5,
TPs by <=1 on ~1300 fills; matched limits -0.66 mean / -0.13 median bps,
fills -0.47/-0.65 mean / -0.09 median bps; stops/TPs medians <=0.5 bps.
Per-year book eff never exceeds |-0.28| %/month in any coin-year cell. The gap
rides the DIP ladder (s0: -25 fills/-34 TPs/+6 stops; s2: -57/-59/+11, TP rate
-0.4/-0.6pp) plus sizing/interaction residual. **BNB share of the book leg is
UNKNOWN from this source: oc_bookvenue publishes no per-coin book table** (not
imputed); the only BNB book number is the §1 spread bound (~1.1 bps/fill side)
and the venue-open median shift (BNB -3.59 bps, mean|.| 5.15 vs 1.5-2.4 for
others), which does not convert into P&L in the B1 replica (§2).

## 5. Deployment baseline and BNB's P&L weight (oc_kpi_g2 + oc_contrib)
G2 per-anchor R (geo mean %/month): 2021 2.59, 2022 3.28, 2023 6.05,
2024 10.68, 2025 4.65; full path DD 16.05/16.82 (4h/1m, gate 16.82), net
+2538.7% (26.39x). BNB true-pair attribution (books+dips entering each anchor
year, mix% = 1/4-capital additive; pooled total 287.28):
| year | BNB mix% | BNB n | BNB win | memo |
|---|---|---|---|---|
| 2021 | +4.16 | 965 | 0.572 | smallest contributor |
| 2022 | -0.02 | 1048 | 0.630 | ~zero (only losing BNB year) |
| 2023 | +5.43 | 1201 | 0.681 | |
| 2024 | +12.06 | 1067 | 0.661 | |
| 2025 | +17.71 | 1253 | 0.650 | largest contributor |
| pooled | +39.33 (13.7% of 287.28) | 5534 (21% of trades) | 0.641 | every other coin also positive pooled |
DD windows (realized mix%, BNB share): 2023-04 -9.94 BNB -8.36 (84%);
2023-07 -7.10 BNB -0.47 (7%); flash 2024-01-03 -15.55 BNB -1.10 (7%);
2024-06 -6.78 BNB +1.63 (-24%, offsets); 2025-10 -6.40 BNB +0.09 (-1%).
BNB carries exactly one of five windows.

## 6. Scenarios: BNB on Bybit, hypothesis arithmetic ONLY (no re-simulation)
(a) BNB on Bybit, unchanged rules. Rung-y cost = BNB gap 0.348 units (2.5% of
Bybit rung P&L). Proportional illustration on the deployment dip_eff scale
(rung-y != %/month, labelled only): 0.674 x dip_eff = -0.10 %/month (s0) /
-0.33 %/month (s2) single-phase. Book side: spread bound ~1.14 bps/side times
~20% BNB share of ~1300 book fills ≈ <0.02 %/month. Combined: a BNB-venue
penalty, if the B1 share transferred 1:1 (it does not — deployment amplifies
via sizing/timeouts), would still be <0.1-0.3 %/month single-phase against a
5-7 %/month base — i.e. not the drag, and BNB dip-only routing cannot recover
the -0.27/-0.65 %/month S5 gap because XRP+residual dominate it.
(b) BNB dip rungs only (drop BNB book). BNB book vs dip is NOT separated per
coin in oc_contrib; proportional-to-sleeve illustration (book 38.5% of
additive): BNB book ≈ 15.15 mix%, BNB dip ≈ 24.19 mix% of the 39.33 BNB total.
No-assumption bound for dropping BNB book: 0..39.33 mix% additive. Either way
the 5y stays BNB-positive on dips under this assumption; the assumption itself
is the caveat — a true book/dip-per-coin split needs a re-attribution, not
done here.
(c) No BNB at all. Drop full BNB +39.33 mix% additive (13.7% of the 287.28
additive total; yearly drops in §5 table, worst in 2025). Illustrative linear
haircut on the geometric mean: 5.61 x 13.7% ≈ 0.77pp/month order-of-magnitude
only (no compounding re-fit, funding excluded, 18 open books excluded as in
oc_kpi). DD directionally: removing BNB would erase ~84% of the 2023-04
realized window but offset the 2024-06 window (-24% share means BNB was
helping) and leave the gate flash (7% BNB) and 2025-10 (~0%) intact — so gate
DD likely moves by only ~1-2pp, not below any 15% target on this evidence
alone. No year turns losing from a BNB removal except 2022 is already ~zero
for BNB.

## Caveats
Assignment path `research/tournament/oc_bookvenue` does not exist; book numbers
are from `research/diagnostics/oc_bookvenue` (S5 window from 2021-11-15, s=0/s=2
single-phase — NOT the 4-phase-mix gate DD). Rung-y sums cannot be subtracted
from %/month; scenario (a) scaling is an explicitly labelled illustration, not
a conversion. (b) assumes an even BNB book/dip split — the true split is
unpublished. All five years are research data; any routing claim needs
prospective validation. LIGHT job: stdlib json only, <5 MB, no 1m.

## Verdict
VERDICT: BNB's ~10x Bybit spread is real but its venue drag is small and dip-led (B1 BNB gap +0.35 units = 2.5% of rung P&L, symmetric solo TPs, book execution venue-identical with no per-coin book-drag table), so BNB-on-Bybit scenarios move the deployment 5y only via BNB's ~14% additive P&L share and barely move gate DD — a BNB-venue fix is not the drag fix; hypotheses (a)/(b)/(c) above are arithmetic illustrations only, with no routing change recommended.
