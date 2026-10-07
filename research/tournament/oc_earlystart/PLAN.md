# oc_earlystart PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

Idea #28: earlier dip ladder (bot places bids at minute 5, fillable from minute 6).

## Hypothesis (fixed here)

The engine's dip bids rest from minute 16 (sleeve_start=16) because the plan
used to arrive late, but rung levels depend only on the bar open O(T) and
sigma4 sg(T) — both known at the bar open T — so a bot can place them at
minute 5. The user rule only forbids fills in the first 5 minutes after the
4h close. Hypothesis (direction pre-registered): making the SAME B1 rungs
fillable from minute 6 instead of 16 adds net value (extra fills in minutes
6-15 are on average winners net of costs) at no worse tail. Fixed rule, no
fitted parameters: resting limit BUY at lv fillable over offsets 6..238
(EARLY) vs 16..238 (BASE); everything else identical.

## Data (fixed here, all in repo - no fetch)

- 1m klines: `data/raw/btc_intraday_20260924` (BTC),
  `data/raw/majors_intraday_20260924` (ETH/SOL/BNB/XRP). Minutes used:
  t < 2026-09-24 00:00 UTC. Missing minutes (NaN) never fill, never trigger
  an exit touch, and never count as flushing.
- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- Rungs k in {2.5, 3.0, 3.5, 4.0, 5.0} (R2 depths).
- Bars: standard 4h grid, bar j covers [START + 4h*j, START + 4h*j + 4h) with
  START = 2020-08-01 00:00 UTC. Only bars with open T in
  [2021-09-24 00:00, 2026-09-24 00:00) UTC are traded (5 anchor years
  Y0..Y4 = [anchor, anchor+365d), anchors 2021-09-24..2025-09-24, keyed by T).
- Market data up to 2026-09-24 00:00 UTC is read per the assignment (all five
  years are research data; any PROMISING result needs prospective validation
  before real money). Disclosed against RULES.md 2 / VF_COMMON hidden-year
  conventions.
- Resources: one process, one coin's full H/L in RAM at a time (float32);
  all-five-coins 1m opens/closes held as float32 arrays for the n detector;
  RAM < 3 GB.

## Exact causal definitions (frozen)

1. Bar open: O_c(T) = 1m `open` of coin c at minute T (no ffill; NaN =
   missing). sigma_4h(c,T): simple returns r_b = O_b/O_{b-1} - 1 of 4h bar
   opens; sigma = std(r over 360 bars ending at T-1, min_periods 120,
   ddof=1) = v293/oc_dipexit/oc_b1deeper definition. Known at the bar open T
   (excludes the bar itself). Bars with non-finite O, sg <= 0 or NaN are
   skipped (no rungs that bar). Bid levels are placed at minute 5 at the
   latest; nothing before minute 6 can fill (user 5-minute rule respected).
2. Base rung level (static, both arms): lv(a,T,k) = O_a(T) * (1 - k*sg_a(T)).
3. Correlation count at minute m (v399/oc_b1deeper-exact, used for sizing
   only): n(a,T,m) = number of OTHER majors b != a with finite O_b(T),
   finite C_b(T+m-1), finite sg_b(T) > 0 AND
   C_b(T+m-1) <= O_b(T) * (1 - 2.5*sg_b(T)). C uses the 1m `close` at minute
   T+m-1 (last fully closed minute; no cross-bar ffill, within-bar NaN stays
   NaN = not flushing). Own coin never counted (0..4). Flush at exactly 2.5
   sigma counts (<=).
4. Arms per candidate rung (bar T, coin a, depth k), static level lv:
   (a) BASE: resting limit BUY at lv, live offsets 16..238 inclusive. Fill at
       FIRST offset f with low(T+f) < lv (STRICT trade-through). Fill price =
       lv. n_fill = n(a,T,f). size_mult = 1/(1+n_fill) (B1, both arms).
   (b) EARLY: resting limit BUY at the SAME lv, live offsets 6..238
       inclusive. Fill at FIRST offset f with low(T+f) < lv (STRICT). Fill
       price = lv. n_fill = n(a,T,f) at its OWN fill minute. size_mult =
       1/(1+n_fill). Only difference vs BASE is the wider live window.
5. Post-fill exits (long), oc_b1deeper/oc_dipexit D0 replica measured from the
   fill price px = lv: sl = px*(1-4*sg), bl = px*(1-8*sg), tp = px*(1+1.0*sg).
   Evaluated on minutes t in f+1..239 then timeout at 240 (next-bar open o2 =
   1m open at T+240): backstop touch (first t with low(t) <= bl) exits at
   min(bl,open(t)) taker; else TP touch (first t with high(t) > tp, STRICT)
   exits at tp maker; else close5 stop (clock minutes m with (m+1)%5==0,
   first m with close(m) <= sl) exits at open(m+1) (or o2 if m=239) taker;
   else timeout at o2 taker + funding 0.0001 if (T+4h).hour in (0,8,16).
   Priority stop-first: backstop wins ties (kb<=ks and kb<=kt); else TP wins
   only if strictly earlier (kt<ks); else stop; else timeout. A stop and TP
   in the same minute -> stop wins. Fees: fill maker 0.0002; TP leg maker
   0.0002 (total 2*maker on TP); stop/backstop/time legs taker 0.00055. Net
   returns are fractions of px. Fills whose exit price is missing (NaN open,
   NaN o2 on a stop-at-239/timeout path) give NaN net and are DROPPED per arm.
6. Weights: w = size_mult per kept fill. PRIMARY comparison renormalises per
   anchor year to equal mean exposure within arm: w' = w / mean(w over that
   arm's fills in that year) (mean 1; single-fill year -> w' = 1). Only
   ALLOCATION/price quality is tested, not mean exposure. Raw
   (non-renormalised) sums are reported descriptively.
7. Daily sums per arm per year: group w'*y by EXIT date (calendar UTC date of
   T+x, x = exit offset, 240 = next-bar open date). Yearly sum S = sum of
   daily sums. Worst day W = min daily sum. Cumulative path over exit dates
   sorted ascending from 0: C_k = cumsum; maxDD = max(0, max_{p<q}(C_p-C_q))
   in w'*y units (0 when monotone non-decreasing). Win rate = fraction of
   kept fills with y > 0 strictly. Efficiency E = S / maxDD (NaN when
   maxDD == 0). Marginal slice: EARLY fills with f in 6..15 — count, mean net
   (equal-weight, raw y), win rate per year (diagnoses whether the extra
   window's fills are winners net of costs).

## Decision rule (fixed, from the assignment's NEW idea)

Per anchor year Y0..Y4, with renormalised weights: S_BASE(Y), S_EARLY(Y),
DD_BASE(Y), DD_EARLY(Y). PASS_sum(Y) iff S_EARLY(Y) > S_BASE(Y) (strictly
higher; equal fails; NaN -> FAIL). PASS_dd(Y) iff DD_EARLY(Y) <=
DD_BASE(Y) (not worse; equal passes; NaN -> FAIL). PROMISING iff
(a) PASS_sum in >= 4 of 5 years AND (b) PASS_dd in >= 4 of 5 years.
Otherwise NOT PROMISING. One-line verdict in REPORT.md. Descriptive only:
fills, win rate, marginal 6-15 mean, raw sums, worst days, full-path sums/DD,
efficiency S/maxDD.

## Protocol (fixed)

- PLAN.md written before any outcome computation. Then scripts: `early.py`
  (pure-numpy core: n vector, static-level fill over a generic window,
  D0-from-fill exit — same maths as oc_b1deeper/deeper.py), `run.py`
  (per-coin loop, per-arm fill ledger + exit-day sums -> results.json).
  Outputs: results.json, REPORT.md (tables + one-line verdict). Tests:
  `tests/test_oc_earlystart.py` (synthetic hand checks: window edges 6/16,
  strict trade-through, n at own fill minute, D0 exit maths + causality:
  fill uses only m-1 closes; sigma excludes the bar).
- No commits; no edits outside research/tournament/oc_earlystart/
  (+ tests/test_oc_earlystart.py).
