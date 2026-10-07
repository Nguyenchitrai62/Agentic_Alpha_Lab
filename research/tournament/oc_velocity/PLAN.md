# oc_velocity PLAN (pre-registered BEFORE any outcome is computed, 2026-10-05)

Idea #23: flash-velocity dip guard (bot-only).

## Hypothesis (fixed here)

oc_ddanat4p found the gate DD is the 2024-01-03 BTC flash crash (one-bar
multi-coin stop cascade). Hypothesis (direction pre-registered): during a
BTC flash-velocity episode inside a 4h holding bar, dip rungs filled after
the velocity print keep falling through into stop/backstop exits, so
cancelling ALL majors' still-resting dip bids for the rest of that bar once
BTC prints a >= 3-sigma 15-minute velocity drop (filled rungs keep their
stop / TP) cuts maxDD at negligible cost to the yearly sum. Bot-executable:
a bot observes each closed 1m print and cancels resting bids; filled rungs
are untouched. Fixed rule, no fitted parameters: K = 3.0, span = 15 min.

## Data (fixed here, all in repo - no fetch)

- 1m klines: `data/raw/btc_intraday_20260924` (BTC),
  `data/raw/majors_intraday_20260924` (ETH/SOL/BNB/XRP). Minutes used:
  t in [2020-08-01 00:00, 2026-09-24 00:00] UTC. Missing minutes (NaN)
  never fill, never trigger an exit touch, and never trigger the guard.
- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- Rungs k in {2.5, 3.0, 3.5, 4.0, 5.0} (R2 depths, oc_b1deeper replica).
- Bars: standard 4h grid, bar j covers [START + 4h*j, START + 4h*j + 4h)
  with START = 2020-08-01 00:00 UTC. Bar-relative minute offsets 0..239;
  next-bar open is offset 240. Only bars with open T in
  [2021-09-24 00:00, 2026-09-24 00:00) UTC are traded (5 anchor years
  Y0..Y4 keyed by T: Y_i = [anchor_i, anchor_{i+1}) with anchors
  2021-09-24, 2022-09-24, 2023-09-24, 2024-09-24, 2025-09-24 and end
  2026-09-24 00:00; same keying as oc_b1deeper run.py).
- Market data up to 2026-09-24 00:00 UTC is read per the assignment (all
  five years are research data; any PROMISING result needs prospective
  validation before real money). Disclosed against RULES.md 2 / VF_COMMON
  hidden-year conventions.
- Resources: one process, one coin's full H/L in RAM at a time (float32);
  all-five-coins 1m opens/closes held as float32 arrays for the n detector
  and the BTC velocity detector; RAM < 3 GB.

## Exact causal definitions (frozen)

1. Bar open: O_c(T) = 1m `open` of coin c at minute T (no ffill; NaN =
   missing). sigma_4h(c,T): simple returns r_b = O_b/O_{b-1} - 1 of 4h bar
   opens; sigma = std(r over 360 bars ending at T-1, min_periods 120,
   ddof=1) = v293/oc_dipexit/oc_b1deeper definition
   (pct_change().rolling(360).std(ddof=1).shift(1)). Known at the bar open
   T. Bars with non-finite O, sg <= 0 or NaN are skipped (no rungs that
   bar). BTC guard additionally requires finite O_BTC(T) and finite
   sg_BTC(T) > 0, else the guard never fires that bar.
2. Base rung level: lv(a,T,k) = O_a(T) * (1 - k*sg_a(T)).
3. Correlation count at minute m (live offsets 16..238 inclusive, v399 /
   oc_b1deeper exact): n(a,T,m) = number of OTHER majors b != a with
   finite O_b(T), finite C_b(T+m-1), finite sg_b(T) > 0 AND
   C_b(T+m-1) <= O_b(T) * (1 - 2.5*sg_b(T)). C uses the 1m `close` at
   minute T+m-1 (last fully closed minute; no cross-bar ffill, within-bar
   NaN stays NaN = not flushing). Own coin never counted (0..4). Flush at
   exactly 2.5 sigma counts (<=).
4. B1 arm (oc_b1deeper replica, size only): resting limit BUY at lv, live
   offsets 16..238. Fill at FIRST offset f with low(T+f) < lv (STRICT
   trade-through). Fill price = lv. n_fill = n(a,T,f). size_mult w =
   1/(1+n_fill). At most one fill per (bar, coin, k).
5. Velocity guard trigger (BTC only, causal): let c[i] = BTC 1m `close` at
   bar-relative minute i (i = 0..239; c[i] is the close of minute T+i,
   known once minute T+i closes). Let sg = sg_BTC(T). For each live
   decision minute m in [16..238], define window closes
   W(m) = {c[m-16], ..., c[m-1]} (16 closes, all <= minute T+m-1, hence
   known before minute T+m trades). Trigger at m iff all 16 closes in
   W(m) are finite AND c[m-1] <= max(W(m)) * (1 - 3.0*sg). (Including
   c[m-1] in the max is per the assignment formula; a fresh high can never
   trigger since (1-3sg) < 1.) The guard minute m*(T) = smallest m in
   [16..238] satisfying the trigger; None if never triggered. Within-bar
   NaN in W(m) -> no trigger at m (conservative). sg <= 0 / NaN -> never.
6. Guard arm (B1+velocity-guard): same rungs/levels/sizes/exits as B1, but
   a rung that would fill at B1 minute f is KEPT iff m*(T) is None OR
   f < m*(T) (strictly before the guard; cancellation is effective from
   minute m* onward because the trigger uses only closes up to m*-1).
   Rungs with f >= m*(T) are REMOVED (cancelled, contribute 0). Kept rungs
   keep fill price lv, weight w = 1/(1+n_fill) (same as B1), and the same
   exit outcome as B1 (filled rungs keep their stop / TP; exits do not
   depend on the guard).
7. Post-fill exits (long), oc_b1deeper D0 replica measured from fill price
   px = lv: sl = px*(1-4*sg), bl = px*(1-8*sg), tp = px*(1+1.0*sg).
   Evaluated on minutes t in f+1..239 then timeout at 240 (next-bar open
   o2 = 1m open at T+240): backstop touch (first t with low(t) <= bl)
   exits at min(bl,open(t)) taker; else TP touch (first t with high(t) >
   tp, STRICT) exits at tp maker; else close5 stop (clock minutes m with
   (m+1)%5==0, first m with close(m) <= sl) exits at open(m+1) (or o2 if
   m=239) taker; else timeout at o2 taker + funding 0.0001 if
   (T+4h).hour in (0,8,16). Priority stop-first: backstop wins ties
   (kb<=ks and kb<=kt); else TP wins only if strictly earlier (kt<ks);
   else stop; else timeout. A stop and TP in the same minute -> stop wins.
   Fees: fill maker 0.0002; TP leg maker 0.0002 (total 2*maker on TP);
   stop/backstop/time legs taker 0.00055. Net returns are fractions of px.
   Fills whose exit price is missing (NaN open, NaN o2 on a stop-at-239 /
   timeout path) give NaN net and are DROPPED per arm (same as replica).
8. Weights / sums (frozen): NO renormalisation (unlike oc_b1deeper's
   primary). Both arms use identical per-rung weights w = 1/(1+n_fill);
   the guard arm is a strict subset sum of B1, so S_guard vs S_B1 measures
   the cost of cancelled rungs at constant sizing. Daily sums per arm per
   year: group w*y by EXIT date (calendar UTC date of T+x, x = exit
   offset, 240 = next-bar open date). Yearly sum S = sum of daily sums
   (= sum of w*y). Worst day Wd = min daily sum. Cumulative path over exit
   dates sorted ascending from 0: C_k = cumsum; maxDD = max(0,
   max_{p<q}(C_p-C_q)) in w*y units (0 when monotone non-decreasing). Win
   rate = fraction of kept fills with y > 0 strictly (equal-weight,
   descriptive). Removed-rung stats per year: count, equal-weight mean(y),
   win rate (y>0), size-weighted removed sum RS = sum(w*y).
9. Guard events: one event per bar T with m*(T) not None (whether or not
   any rung was removed). The 10 largest events are ranked by removed-rung
   count descending, tie-break by removed RS ascending (most negative
   first), then earliest T. Each lists bar open UTC, m*, removed count,
   removed mean/win/RS. Query dates 2024-01-03, 2024-08-05, 2022-06-13,
   2022-11-09, 2025-10-10: guard "fired" on date D iff some bar with
   [T, T+4h) intersecting calendar day D (UTC) has m* not None; report
   yes/no per date.

## Decision rule (fixed, from the assignment)

Per anchor year Y0..Y4 (same-weight w*y sums): S_B1(Y), S_g(Y), DD_B1(Y),
DD_g(Y). PASS_dd(Y) iff DD_g(Y) <= DD_B1(Y) (not worse; equal passes; NaN
-> FAIL). PASS_sum(Y) iff S_g(Y) >= 0.95 * S_B1(Y) (guard keeps >= 95% of
B1; equal passes; NaN -> FAIL; if S_B1(Y) <= 0 the same inequality
applies, i.e. the guard must not lose more). PROMISING iff (a) PASS_dd in
>= 4 of 5 years AND (b) PASS_sum in >= 4 of 5 years. Otherwise NOT
PROMISING. One-line verdict in REPORT.md. Descriptive only: fills, win
rate, raw sums, worst days, removed stats, full-path sums/DD.

## Protocol (fixed)

- PLAN.md written before any outcome computation. Then scripts:
  `velocity.py` (pure-numpy core: n vector, velocity trigger, strict
  fill, D0-from-fill exit - copied logic from oc_b1deeper deeper.py with
  attribution, plus guard_trigger), `run.py` (per-coin loop, B1 ledger +
  guard mask + exit-day sums -> results.json). Outputs: results.json,
  REPORT.md (tables + one-line verdict). Tests:
  `tests/test_oc_velocity.py` (synthetic hand checks: trigger exact
  boundary, NaN never triggers, causality window uses only m-1 closes,
  sigma excludes the bar, cancel rule f < m* kept / f >= m* removed,
  kept exits identical to B1; plus replica causality).
- No commits; no edits outside research/tournament/oc_velocity/
  (+ tests/test_oc_velocity.py).
