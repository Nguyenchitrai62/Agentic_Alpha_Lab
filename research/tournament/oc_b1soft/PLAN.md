# oc_b1soft PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

Idea #24: SOFT correlation count for B1.

## Hypothesis (fixed here)

The robustness scan research/diagnostics/oc_plateau showed the B1 flush
threshold F is the DD lever (F 2.0: 5.04 %/mo / DD 16.0; F 2.5: 5.43 /
18.33; F 3.0: 5.68 / 22.1). Hard counting wastes information: a board at
1.2 sigma everywhere scores n=0 under every hard F, same as a calm board.
Pre-registered direction: replacing the hard count with a SOFT count that
gives partial credit between 1.0 and 2.5 sigma improves the allocation
efficiency (size-weighted sum per unit of daily-sum-path drawdown) over
both hard B1(F=2.5) and B1(F=2.0), at fixed fill prices and exits. Fixed
rule, no fitted parameters.

Fixed rule: at the fill minute f of coin a, for every other major b,
d_b = (O_b - C_b(f-1)) / (O_b * sigma4_b) (sigma units below its own bar
open); n_soft = sum_b clip((d_b - 1.0) / 1.5, 0, 1) (0 at <= 1 sigma,
linear ramp, 1 at >= 2.5 sigma); size x 1 / (1 + n_soft).

## Data (fixed here, all in repo - no fetch)

- 1m klines: `data/raw/btc_intraday_20260924` (BTC),
  `data/raw/majors_intraday_20260924` (ETH/SOL/BNB/XRP). Minutes used:
  t < 2026-09-24 00:00 UTC. Missing minutes (NaN) never fill, never trigger
  an exit touch, and never count toward any n.
- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- Rungs k in {2.5, 3.0, 3.5, 4.0, 5.0} (R2 depths, same set as oc_b1deeper).
- Bars: standard 4h grid, bar j covers [START + 4h*j, START + 4h*j + 4h)
  with START = 2020-08-01 00:00 UTC. Only bars with open T in
  [2021-09-24 00:00, 2026-09-24 00:00) UTC are traded (5 anchor years
  Y0..Y4 = [anchor, anchor+365d), anchors 2021-09-24..2025-09-24, keyed
  by T).
- Market data up to 2026-09-24 00:00 UTC is read per the assignment (all
  five years are research data; any PROMISING result needs prospective
  validation before real money). Disclosed against RULES.md 2 /
  VF_COMMON hidden-year conventions.
- Resources: one process, one coin's full H/L in RAM at a time
  (float32); all-five-coins 1m opens/closes held as float32 arrays for
  the n detector; RAM < 3 GB.

## Exact causal definitions (frozen)

1. Bar open: O_c(T) = 1m `open` of coin c at minute T (no ffill; NaN =
   missing). sigma_4h(c,T): simple returns r_b = O_b/O_{b-1} - 1 of 4h
   bar opens; sigma = std(r over 360 bars ending at T-1, min_periods 120,
   ddof=1) = v293/oc_dipexit/oc_b1deeper definition. Known at the bar
   open T. Bars with non-finite O, sg <= 0 or NaN are skipped (no rungs
   that bar).
2. Base rung level: lv(a,T,k) = O_a(T) * (1 - k*sg_a(T)). Static bid for
   ALL four arms (no price amendment; SOFT changes size only).
3. Fill (all arms identical): resting limit BUY at lv, live offsets
   16..238 inclusive (same as oc_b1deeper). Fill at FIRST offset f with
   low(T+f) < lv (STRICT trade-through). Fill price px = lv. A rung that
   never trades through expires with no fill. Fill uses only minute-T+f
   low vs lv (causal; level needs no future).
4. Flush distance at the fill minute (uses only the last CLOSED minute
   T+f-1, known at fill minute f): for each other major b != a,
   d_b = (O_b(T) - C_b(T+f-1)) / (O_b(T) * sg_b(T)). Any non-finite
   input (O_b, sg_b <= 0 or NaN, C_b NaN) gives d_b = NaN = contributes
   0 (conservative, same as oc_b1deeper). Own coin never counted.
   Boundary: d_b >= F exactly counts as flushing (matches price form
   C <= O*(1-F*sg), same as v399/oc_b1deeper <=).
5. Arms (per filled rung; fills and net returns IDENTICAL across arms,
   only the weight differs):
   (a) B1(F=2.5): n = #{b: d_b >= 2.5}, w = 1/(1+n).
   (b) B1(F=2.0): n = #{b: d_b >= 2.0}, w = 1/(1+n).
   (c) B1(F=1.5): n = #{b: d_b >= 1.5}, w = 1/(1+n).
   (d) SOFT: n_soft = sum_b clip((d_b - 1.0)/1.5, 0, 1), NaN -> 0;
       w = 1/(1+n_soft), so w in [0.2, 1.0].
6. Post-fill exits (long), oc_b1deeper D0 replica measured from px = lv:
   sl = px*(1-4*sg), bl = px*(1-8*sg), tp = px*(1+1.0*sg). Evaluated on
   minutes t in f+1..239 then timeout at 240 (next-bar open o2 = 1m open
   at T+240): backstop touch (first t with low(t) <= bl) exits at
   min(bl,open(t)) taker; else TP touch (first t with high(t) > tp,
   STRICT) exits at tp maker; else close5 stop (clock minutes m with
   (m+1)%5==0, first m with close(m) <= sl) exits at open(m+1) (or o2
   if m=239) taker; else timeout at o2 taker + funding 0.0001 if
   (T+4h).hour in (0,8,16). Priority stop-first: backstop wins ties
   (kb<=ks and kb<=kt); else TP wins only if strictly earlier (kt<ks);
   else stop; else timeout. A stop and TP in the same minute -> stop
   wins. Fees: fill maker 0.0002; TP leg maker 0.0002 (total 2*maker on
   TP); stop/backstop/time legs taker 0.00055. Net returns are fractions
   of px. Fills whose exit price is missing (NaN open, NaN o2 on a
   stop-at-239/timeout path) give NaN net and are DROPPED (all arms
   share the same kept set).
7. Aggregation per arm per anchor year: group w*y (RAW) and w'*y
   (RENORMALISED, w' = w / mean(w over that arm's fills in that year);
   mean 1; single-fill year -> w' = 1) by EXIT date (calendar UTC date
   of T+x, x = exit offset, 240 = next-bar open date). Yearly raw sum
   Sr = sum of raw daily sums; raw worst day Wr = min raw daily sum;
   raw maxDD DDr = max drawdown of the raw cumulative daily-sum path
   from 0 (0 when monotone non-decreasing); raw efficiency
   Er = Sr / DDr. Same with renormalised weights: S, W, DD,
   E = S / DD. Guards (fixed): no fills in an arm-year -> S = 0, W = 0,
   DD = 0, E = NaN (comparison FAILs). DD == 0 with S > 0 -> E = +inf;
   DD == 0 with S <= 0 -> E = 0. Win rate = fraction of kept fills with
   y > 0 strictly (equal-weight, descriptive).
8. Provenance: B1(F=2.5) fills must match the oc_b1deeper B1 fill count
   per coin to the tick (5498 total:
   1067/1126/952/1179/1174); mismatch = replica bug, stop and fix.

## Decision rule (fixed, from the assignment)

Per anchor year Y0..Y4, RENORMALISED (equal-exposure, primary) path:
E_SOFT(Y), E_25(Y) = B1(F=2.5), E_20(Y) = B1(F=2.0).
PASS(Y) iff E_SOFT(Y) > E_25(Y) AND E_SOFT(Y) > E_20(Y) (STRICT; ties
fail; any NaN fails). PROMISING iff PASS in >= 4 of 5 years. Otherwise
NOT PROMISING. B1(F=1.5) and all RAW-efficiency counts are descriptive
consistency rows only and cannot flip the verdict. One-line verdict in
REPORT.md. Descriptive only: fills, win rate, raw sums, worst days,
full-path sums/DD.

## Protocol (fixed)

- PLAN.md written before any outcome computation. Then scripts:
  `soft.py` (pure-numpy core: d vector, n_hard, n_soft, size, strict
  fill, D0-from-fill exit), `run.py` (per-coin loop, shared fills,
  4-arm weights, raw + renormalised daily paths -> results.json).
  Outputs: results.json, REPORT.md (tables + one-line verdict). Tests:
  `tests/test_oc_b1soft.py` (synthetic hand checks: d/n_soft ramp,
  boundary counts, weight bounds, strict fill, exit parity with
  oc_b1deeper; causality: fill/n use only m-1 closes; sigma excludes
  the bar).
- No commits; no edits outside research/tournament/oc_b1soft/
  (+ tests/test_oc_b1soft.py).
