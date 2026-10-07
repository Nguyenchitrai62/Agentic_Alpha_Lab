# oc_bookdipnet REPORT — book/dip long-overlap guard, idea #19 (2026-10-05; PLAN pre-registered before any outcome, one disclosed post-hoc extra)

## Setup
Base = exact v411 R2B1D17BF phase s=0 replica (`oc_ddanat17`: dips x1.7
inv-rule, budget 0.26x1.7, bear-book filter longs x0.5, R2 agents, win_start=5).
Book P&L per coin-bar is the engine's OWN attrib accounting from `raw_s0.pkl`
(NET of book fees/funding, fractions of bar-start equity; cols
BNB/BTC/ETH/SOL/XRP); dip = sleeve fractions; attrib-compounded base path
reproduces raw engine equity bit-for-bit (rel diff 0.0). The assignment's
vectorised-turnover fallback was NOT needed. Book-long sign = bear-scaled d2
(`forward_v205.research_books_d2` rebuilt exactly + BTC-open bear filter x0.5
on positives) ffilled at B-4h. Rule (fixed): at holding-bar start B, coin c's
book LONG is x0.5 iff rungs filled in [B-4h,B) and still open at B sum to >= 2x
that coin's mean rung weight (thr: BNB 0.275, BTC 0.228, ETH 0.215, SOL 0.217,
XRP 0.262); shorts/flat never scaled; dip unchanged (halving P&L is a disclosed
LIGHT approximation — no re-simulation of fills/stops). Live
2021-09-24..2026-09-23; years [A_k,A_{k+1}), A_5=2026-09-24 (10944 bars).
Repro: `research/tournament/oc_bookdipnet/{PLAN.md,compute_bookdipnet.py,results.json}`.

## Mechanism finding (why the strict rule is degenerate)
Max rung lifetime is 224m < 240m holding bar and ALL 2422 rung_timeouts exit
exactly at the next 4h open (2424/5466 exits land exactly on a B; 0 rung is
strictly open across any holding-bar boundary). The dip sleeve is FLAT at
every B by construction, so the pre-registered strict rule (`exit_t > B`)
fires on 0/54720 coin-bars — guard == base. The disclosed post-hoc extra uses
`exit_t >= B` (keeps timeouts closing at the B open; a dip-timeout brake, not
true simultaneous exposure): 363 guard coin-bars / 54720 (0.66%;
overlap-only 441). Expanding-mean threshold sensitivity fires 0 times.

## Per anchor year: combined (book+dip) base -> guarded-inc (strict guard == base everywhere)
| year | bars | guard-inc coin-bars | book-long base -> guard | combined ret base -> guard | combined maxDD(d) base -> guard | worst day base -> guard |
|---|---|---|---|---|---|---|
| 2021-09-24 | 2189 | 43 | -0.0344 -> -0.0289 | +0.7784 -> +0.7883 | 0.0990 -> 0.0975 | -0.0552 -> -0.0552 |
| 2022-09-24 | 2190 | 73 | +0.2623 -> +0.2421 | +0.5355 -> +0.5049 | 0.1532 -> 0.1556 (worse) | -0.0790 -> -0.0790 |
| 2023-09-24 | 2191 | 86 | +0.5185 -> +0.4999 | +2.1527 -> +2.0956 | 0.1811 -> 0.1814 (worse) | -0.1404 -> -0.1404 |
| 2024-09-24 | 2189 | 97 | +0.5375 -> +0.5378 | +2.3621 -> +2.3638 | 0.0756 -> 0.0722 | -0.0442 -> -0.0459 (worse) |
| 2025-09-24 | 2185 | 64 | +0.2848 -> +0.2882 | +1.0099 -> +1.0170 | 0.0913 -> 0.0881 | -0.0913 -> -0.0876 |

## Decision
Strict (pre-registered): maxDD improves 0/5, sum not lower 5/5 -> fails the
>= 4/5 DD leg. Inclusive extra: maxDD improves 3/5 (2021/2024/2025; worse in
2022/2023, incl. the FTX-year window), sum not lower 3/5 (up in
2021/2024/2025, down in 2022/2023) -> fails the >= 4/5 DD leg. Full-period
57.18x base vs 55.52x inclusive-guarded; book-long 1.569 -> 1.539. Worst day
improves only in 2025.

## Verdict
VERDICT: NOT PROMISING — the specified strict overlap guard can never fire (dip sleeve is flat at every holding-bar boundary by engine design), and even the lenient post-hoc boundary-inclusive dip-timeout brake cuts combined maxDD in only 3/5 years while lowering the yearly sum in the two crash years (2022/2023).

## Caveats
Guarded P&L = 0.5x attrib fractions on guard-on long coin-bars (no
re-simulation; fill/min-notional/stop non-linearities ignored); single phase
s=0 only; thresholds are full-sample mean rung weights (fixed sizing scale,
not fitted to returns); year stats year-rebased; tests
`tests/test_oc_bookdipnet.py` (7 pass: files/ordering, replica counts +
bit-for-bit path, strict-zero vs inclusive-363 census, mask longs-only +
boundary convention, overlap causality under future-rung perturbation,
year-partition cover).
