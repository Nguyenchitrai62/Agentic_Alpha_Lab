# oc_rungspace PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

Idea #37: wider dip rung spacing.

## Hypothesis (fixed here)

Current R2 rungs sit at 2.5/3.0/3.5/4.0/5.0 sigma4 and in big flushes all 25
fills fire together (oc_crashfreq concentration), stacking correlated tail
risk. Hypothesis: spacing the ladder wider — 2.5/3.25/4.0/5.0/6.0 sigma —
keeps the near-rung hit rate (first rung identical at 2.5) while cutting
joint full-ladder fills in flushes, so the yearly size-weighted sum is not
lower and the daily-sum-path drawdown is not worse. Fixed rule, ONE
alternative, no fitted parameters: same per-rung B1 size x 1/(1+n), same D0
exits (TP 1.0 sigma above the fill, close-stop 4 sigma below the fill,
backstop 8 sigma below the fill). Direction pre-registered: WIDE beats BASE
on yearly sums at no worse maxDD.

## Data (fixed here, all in repo - no fetch)

- 1m klines: `data/raw/btc_intraday_20260924` (BTC),
  `data/raw/majors_intraday_20260924` (ETH/SOL/BNB/XRP). Minutes used:
  t < 2026-09-24 00:00 UTC. Missing minutes (NaN) never fill, never trigger
  an exit touch, and never count as flushing.
- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- Arms: BASE k in {2.5, 3.0, 3.5, 4.0, 5.0} (R2 depths); WIDE k in
  {2.5, 3.25, 4.0, 5.0, 6.0} (ONE alternative, fixed).
- Bars: standard 4h grid, bar j covers [START + 4h*j, START + 4h*j + 4h) with
  START = 2020-08-01 00:00 UTC. Only bars with open T in
  [2021-09-24 00:00, 2026-09-24 00:00) UTC are traded (5 anchor years
  Y0..Y4 = [anchor, anchor+365d), anchors 2021-09-24..2025-09-24, keyed by T).
- Market data up to 2026-09-24 00:00 UTC is read per the assignment (all five
  years are research data; any PROMISING result needs prospective validation
  before real money). Disclosed against RULES.md 2 / VF_COMMON hidden-year
  conventions.
- Resources: one process, one coin's full H/L in RAM at a time (float32);
  all-five-coins 1m opens/closes held as float32 arrays; RAM < 3 GB.

## Exact causal definitions (frozen; oc_b1deeper replica, only RUNGS differ)

1. Bar open: O_c(T) = 1m `open` of coin c at minute T (no ffill; NaN =
   missing). sigma_4h(c,T): simple returns r_b = O_b/O_{b-1} - 1 of 4h bar
   opens; sigma = std(r over 360 bars ending at T-1, min_periods 120,
   ddof=1) = v293/oc_dipexit definition. Known at the bar open T. Bars with
   non-finite O, sg <= 0 or NaN are skipped (no rungs that bar).
2. Rung level: lv(a,T,k) = O_a(T) * (1 - k*sg_a(T)), k from the arm's set.
3. Correlation count at minute m (live window offsets 16..238 inclusive,
   same as oc_dipexit/oc_b1deeper): n(a,T,m) = number of OTHER majors
   b != a with finite O_b(T), finite C_b(T+m-1), finite sg_b(T) > 0 AND
   C_b(T+m-1) <= O_b(T) * (1 - 2.5*sg_b(T)). C uses the 1m `close` at
   minute T+m-1 (last fully closed minute; no cross-bar ffill, within-bar
   NaN stays NaN = not flushing). Own coin never counted (0..4). Flush at
   exactly 2.5 sigma counts (<=). v399-exact, same as oc_b1deeper.
4. Fill per candidate rung (bar T, coin a, depth k, static B1 bid): resting
   limit BUY at lv, live offsets 16..238. Fill at FIRST offset f with
   low(T+f) < lv (STRICT trade-through). Fill price = lv. n_fill = n(a,T,f)
   at the fill minute. size_mult = 1/(1+n_fill). Both arms use this same
   static-bid B1 fill; the ONLY difference between arms is the rung set.
5. Post-fill exits (long), oc_dipexit D0 replica measured from the fill
   price px = lv: sl = px*(1-4*sg), bl = px*(1-8*sg), tp = px*(1+1.0*sg).
   Evaluated on minutes t in f+1..239 then timeout at 240 (next-bar open
   o2 = 1m open at T+240): backstop touch (first t with low(t) <= bl)
   exits at min(bl,open(t)) taker; else TP touch (first t with high(t) > tp,
   STRICT) exits at tp maker; else close-stop (clock minutes m with
   (m+1)%5==0, first m with close(m) <= sl) exits at open(m+1) (or o2 if
   m=239) taker; else timeout at o2 taker + funding 0.0001 if (T+4h).hour
   in (0,8,16). Priority stop-first: backstop wins ties (kb<=ks and
   kb<=kt); else TP wins only if strictly earlier (kt<ks); else stop; else
   timeout. A stop and TP in the same minute -> stop wins. Fees: fill maker
   0.0002; TP leg maker 0.0002 (total 2*maker on TP); stop/backstop/time
   legs taker 0.00055. Net returns are fractions of px. Fills whose exit
   price is missing (NaN open, NaN o2 on a stop-at-239/timeout path) give
   NaN net and are DROPPED per arm.
6. Weights: w = size_mult per kept fill. PRIMARY comparison renormalises per
   anchor year to equal mean exposure within arm: w' = w / mean(w over that
   arm's fills in that year) (mean 1; single-fill year -> w' = 1). Only
   spacing quality is tested, not mean exposure. Raw (non-renormalised)
   sums are reported descriptively.
7. Daily sums per arm per year: group w'*y by EXIT date (calendar UTC date of
   T+x, x = exit offset, 240 = next-bar open date). Yearly sum S = sum of
   daily sums. Worst day W = min daily sum. Cumulative path over exit dates
   sorted ascending from 0: C_k = cumsum; maxDD = max(0, max_{p<q}(C_p-C_q))
   in w'*y units (0 when monotone non-decreasing). Win rate = fraction of
   kept fills with y > 0 strictly (equal-weight).
8. Full-ladder bars: a (bar T, coin a) counts as all5 for an arm iff all 5
   k of that arm's set have a KEPT fill (finite exit net) in that bar.
   Reported per anchor year per arm (ALL5) plus full total. Fills dropped
   for NaN exits do not count toward all5.

## Decision rule (fixed, from the assignment)

Per anchor year Y0..Y4, with renormalised weights: S_base(Y), S_wide(Y),
DD_base(Y), DD_wide(Y). PASS_sum(Y) iff S_wide(Y) >= S_base(Y) (not lower;
equal passes; NaN -> FAIL). PASS_dd(Y) iff DD_wide(Y) <= DD_base(Y) (not
worse; equal passes; NaN -> FAIL). PROMISING iff (a) PASS_sum in >= 4 of 5
years AND (b) PASS_dd in >= 4 of 5 years. Otherwise NOT PROMISING. One-line
verdict in REPORT.md. Descriptive only: fills, win rate, raw sums, worst
days, full-path sums/DD, ALL5 counts.

## Protocol (fixed)

- PLAN.md written before any outcome computation. Then scripts:
  `rungspace.py` (pure-numpy core: n vector, static-level fill,
  D0-from-fill exit; byte-identical maths to oc_b1deeper deeper.py), `run.py`
  (per-coin loop over both rung sets, per-arm fill ledger + exit-day sums ->
  results.json). Outputs: results.json, REPORT.md (tables + one-line
  verdict). Tests: `tests/test_oc_rungspace.py` (synthetic hand checks:
  rung levels, strict fill, n detector, D0 exits, all5 counting,
  causality: fill uses only m-1 closes; sigma excludes the bar).
- No commits; no edits outside research/tournament/oc_rungspace/
  (+ tests/test_oc_rungspace.py).
