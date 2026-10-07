# oc_trendladder PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

Idea #55: trend-conditional ladder depth.

## Hypothesis (fixed here)

In an uptrend, dips are shallower on average so a shallower resting bid
fills at a better price with less adverse excursion; in a downtrend, dips
run deeper so a deeper bid avoids catching a falling knife. Fixed rule, no
fitted parameters: scale every rung depth k by a BTC-trend multiplier known
at the bar open — 0.85 when BTC's 30-day return is positive (shallower:
2.5 -> 2.125 sigma, etc.), 1.15 when negative (deeper). Direction
pre-registered: TREND (conditional depth) beats BASE (fixed R2 depths) on
yearly size-weighted sums at no worse maxDD. Sizes, the B1 correlation size
rule and D0 exits are otherwise unchanged, stops/TP measured from the
actual fill price.

## Data (fixed here, all in repo — no fetch)

- 1m klines: `data/raw/btc_intraday_20260924` (BTC),
  `data/raw/majors_intraday_20260924` (ETH/SOL/BNB/XRP). Minutes used:
  t in [2020-08-01 00:00, 2026-09-24 00:00] UTC. Missing minutes (NaN)
  never fill, never trigger an exit touch, and never count as flushing.
- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- Rungs k in {2.5, 3.0, 3.5, 4.0, 5.0} (R2 depths, base).
- Bars: standard 4h grid, bar j covers [START + 4h*j, START + 4h*j + 4h)
  with START = 2020-08-01 00:00 UTC. Only bars with open T in
  [2021-09-24 00:00, 2026-09-24 00:00) UTC are traded (5 anchor years
  Y0..Y4 = [anchor, anchor+365d), anchors 2021-09-24..2025-09-24, keyed
  by bar open T).
- Market data up to 2026-09-24 00:00 UTC is read per the assignment (all
  five years are research data; any PROMISING result needs prospective
  validation before real money). Disclosed against RULES.md 2 /
  VF_COMMON hidden-year conventions.
- Replica: oc_b1deeper B1 arm (static bid, size x 1/(1+n), D0-from-fill
  exits) is copied exactly as BASE; TREND differs only by the depth
  multiplier below.
- Resources: one process, one coin's full H/L in RAM at a time
  (float32); all-five-coins 1m opens/closes held as float32 arrays for
  the n detector; bar opens/sigmas/trend precomputed per coin; RAM < 3 GB.

## Exact causal definitions (frozen)

1. Bar open: O_c[j] = 1m `open` of coin c at minute T_j = START + 4h*j
   (no ffill; NaN = missing). sigma_4h(c,j): simple returns
   r_i = O[i]/O[i-1] - 1 of 4h bar opens; sigma = std(r over 360 bars
   ending at j-1, min_periods 120, ddof=1) = v293/oc_dipexit/oc_b1deeper
   definition (pct_change().rolling(360,min120).std(ddof=1).shift(1)).
   Known at the bar open T_j. Bars with non-finite O, sg <= 0 or NaN
   are skipped (no rungs that bar).
2. BTC 30-day trend at bar j (strictly rows < bar, known at the open):
   r30(j) = O_BTC[j-1] / O_BTC[j-181] - 1 (180 4h bars = 30 days, both
   indices < j; O[j] itself is NOT used). Requires finite positive
   denominator and finite numerator, else NaN. Multiplier
   mult(j) = 0.85 iff finite and r30(j) > 0 (strict), else 1.15
   (zero, negative and NaN all take the deeper branch; disclosed).
   Same mult for every coin and every rung of bar j. History starts
   2020-08-01 so j-181 exists for all traded bars (2021-09-24 on);
   NaN mult branch is only a missing-data fallback.
3. Base rung level: lv_base(a,j,k) = O_a[j] * (1 - k*sg_a[j]).
   Trend rung level: lv_tr(a,j,k) = O_a[j] * (1 - k*mult(j)*sg_a[j]),
   i.e. k_eff = k*mult(j) (2.5 -> 2.125 when mult=0.85; 2.5 -> 2.875
   when mult=1.15, etc.). Non-finite or <= 0 levels are skipped.
4. Correlation count at minute m (live window offsets 16..238 inclusive,
   same as oc_b1deeper / oc_dipexit): n(a,j,m) = number of OTHER majors
   b != a with finite O_b[j], finite C_b(T_j+m-1), finite sg_b[j] > 0
   AND C_b(T_j+m-1) <= O_b[j] * (1 - 2.5*sg_b[j]). C uses the 1m
   `close` at minute T_j+m-1 (last fully closed minute; no cross-bar
   ffill, within-bar NaN stays NaN = not flushing). Own coin never
   counted (0..4). Flush at exactly 2.5 sigma counts (<=). Detection
   threshold is NOT trend-scaled (sizes/B1 unchanged per assignment).
   v399-exact, same as oc_b1deeper.
5. Arms per candidate rung (bar j, coin a, depth k):
   (a) BASE: resting limit BUY at lv_base, live offsets 16..238. Fill
       at FIRST offset f with low(T_j+f) < lv_base (STRICT
       trade-through). Fill price = lv_base. n_fill = n(a,j,f).
       size_mult = 1/(1+n_fill) (B1, kept).
   (b) TREND: resting limit BUY at lv_tr, live offsets 16..238. Fill
       at FIRST offset f with low(T_j+f) < lv_tr (STRICT). Fill price
       = lv_tr. n_fill = n(a,j,f) at its OWN fill minute (same
       detector). size_mult = 1/(1+n_fill) (kept as BASE).
6. Post-fill exits (long), oc_b1deeper/oc_dipexit D0 replica measured
   from the ACTUAL fill price px (px = lv_base for BASE; px = lv_tr
   for TREND): sl = px*(1-4*sg), bl = px*(1-8*sg), tp = px*(1+1.0*sg).
   Evaluated on minutes t in f+1..239 then timeout at 240 (next-bar
   open o2 = 1m open at T_j+240): backstop touch (first t with
   low(t) <= bl) exits at min(bl,open(t)) taker; else TP touch (first
   t with high(t) > tp, STRICT) exits at tp maker; else close5 stop
   (clock minutes m with (m+1)%5==0, first m with close(m) <= sl)
   exits at open(m+1) (or o2 if m=239) taker; else timeout at o2
   taker + funding 0.0001 if (T_j+4h).hour in (0,8,16). Priority
   stop-first: backstop wins ties (kb<=ks and kb<=kt); else TP wins
   only if strictly earlier (kt<ks); else stop; else timeout. A stop
   and TP in the same minute -> stop wins. Fees: fill maker 0.0002;
   TP leg maker 0.0002 (total 2*maker on TP); stop/backstop/time legs
   taker 0.00055. Net returns are fractions of px. Fills whose exit
   price is missing (NaN open, NaN o2 on a stop-at-239/timeout path)
   give NaN net and are DROPPED per arm.
7. Weights: w = size_mult per kept fill. PRIMARY comparison
   renormalises per anchor year to equal mean exposure within arm:
   w' = w / mean(w over that arm's fills in that year) (mean 1;
   single-fill year -> w' = 1). Only ALLOCATION/price quality is
   tested, not mean exposure (same as oc_b1deeper). Raw
   (non-renormalised) sums are reported descriptively.
8. Daily sums per arm per year: group w'*y by EXIT date (calendar UTC
   date of T_j+x, x = exit offset, 240 = next-bar open date). Yearly
   sum S = sum of daily sums. Worst day W = min daily sum. Cumulative
   path over exit dates sorted ascending from 0: C_k = cumsum;
   maxDD = max(0, max_{p<q}(C_p-C_q)) in w'*y units (0 when monotone
   non-decreasing). Win rate = fraction of kept fills with y > 0
   strictly (equal-weight, descriptive).

## Decision rule (fixed, from the assignment)

Per anchor year Y0..Y4, with renormalised weights: S_base(Y),
S_tr(Y), DD_base(Y), DD_tr(Y). PASS_sum(Y) iff S_tr(Y) >= S_base(Y)
(not lower; equal passes; NaN -> FAIL). PASS_dd(Y) iff
DD_tr(Y) <= DD_base(Y) (not worse; equal passes; NaN -> FAIL).
PROMISING iff (a) PASS_sum in >= 4 of 5 years AND (b) PASS_dd in
>= 4 of 5 years. Otherwise NOT PROMISING. One-line verdict in
REPORT.md. Descriptive only: fills, win rate, raw sums, worst days,
full-path sums/DD.

## Protocol (fixed)

- PLAN.md written before any outcome computation. Then scripts:
  `trend.py` (pure-numpy core: n vector, trend mult, static-level
  fill, D0-from-fill exit), `run.py` (per-coin loop, per-arm fill
  ledger + exit-day sums -> results.json). Outputs: results.json,
  REPORT.md (tables + one-line verdict). Tests:
  `tests/test_oc_trendladder.py` (synthetic hand checks + causality:
  fill uses only m-1 closes; sigma excludes the bar; trend uses only
  rows < bar and O[j] is not read).
- No commits; no edits outside research/tournament/oc_trendladder/
  (+ tests/test_oc_trendladder.py).
