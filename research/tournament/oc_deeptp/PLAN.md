# oc_deeptp PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

Idea #27: quick exit for deep rungs. oc_contrib diagnostic: deep 4.0 / 5.0
sigma rungs lose every year (stops + timeouts), shallow rungs earn.

## Hypothesis (fixed here)

Deep dip rungs (depth >= 4.0 sigma) fall through the agent TP (1.0 sigma)
too often and die in stops/timeouts. A quicker take-profit of 0.5 sigma on
deep rungs only (limit, maker; everything else unchanged) rescues deep-rung
P&L without giving up the shallow-rung upside, so the whole ladder with
quick deep exits beats BOTH the all-TP-1.0 ladder AND the ladder with deep
rungs removed, at no worse tail. Direction pre-registered: QUICK beats BASE
and NODEEP on yearly size-weighted sums at no worse maxDD. Fixed rule, zero
fitted parameters: deep = k in {4.0, 5.0}; TP multiple mu = 0.5 on deep
rungs in QUICK, mu = 1.0 everywhere in BASE, deep rungs absent in NODEEP.

## Data (fixed here, all in repo - no fetch)

- 1m klines: `data/raw/btc_intraday_20260924` (BTC),
  `data/raw/majors_intraday_20260924` (ETH/SOL/BNB/XRP). Minutes used:
  t < 2026-09-24 00:00 UTC. Missing minutes (NaN) never fill, never trigger
  an exit touch, and never count as flushing.
- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- Rungs k in {2.5, 3.0, 3.5, 4.0, 5.0} (R2 depths). Deep = k >= 4.0.
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
   ddof=1) = v293/oc_b1deeper definition. Known at the bar open T. Bars with
   non-finite O, sg <= 0 or NaN are skipped (no rungs that bar).
2. Rung level: lv(a,T,k) = O_a(T) * (1 - k*sg_a(T)). Resting limit BUY at lv,
   live offsets 16..238 inclusive. Fill at FIRST offset f with low(T+f) < lv
   (STRICT trade-through). Fill price px = lv. Same fills for BASE and QUICK;
   NODEEP keeps only the shallow (k < 4.0) fills. At most one fill per
   (bar, coin, k). Fill uses only minutes <= f of the same bar.
3. Correlation count at minute m (live window offsets 16..238 inclusive,
   v399/oc_b1deeper-exact): n(a,T,m) = number of OTHER majors b != a with
   finite O_b(T), finite C_b(T+m-1), finite sg_b(T) > 0 AND
   C_b(T+m-1) <= O_b(T) * (1 - 2.5*sg_b(T)). C uses the 1m `close` at
   minute T+m-1 (last fully closed minute; no cross-bar ffill, within-bar
   NaN stays NaN = not flushing). Own coin never counted (0..4). Flush at
   exactly 2.5 sigma counts (<=). Size w = 1/(1+n_fill) with n_fill at the
   OWN fill minute (B1 size, kept for all three variants).
4. Post-fill exits (long), oc_b1deeper D0 replica measured from the fill
   price px = lv, with TP multiple mu (mu = 1.0 agent-TP-proxy, mu = 0.5
   quick): sl = px*(1-4*sg), bl = px*(1-8*sg), tp(mu) = px*(1+mu*sg).
   Evaluated on minutes t in f+1..239 then timeout at 240 (next-bar open
   o2 = 1m open at T+240): backstop touch (first t with low(t) <= bl)
   exits at min(bl,open(t)) taker; else TP touch (first t with high(t) >
   tp(mu), STRICT) exits at tp(mu) maker; else close5 stop (clock minutes
   m with (m+1)%5==0, first m with close(m) <= sl) exits at open(m+1)
   (or o2 if m=239) taker; else timeout at o2 taker + funding 0.0001 if
   (T+4h).hour in (0,8,16). Priority stop-first: backstop wins ties
   (kb<=ks and kb<=kt); else TP wins only if strictly earlier (kt<ks);
   else stop; else timeout. A stop and TP in the same minute -> stop wins.
   Fees: fill maker 0.0002; TP leg maker 0.0002 (total 2*maker on TP);
   stop/backstop/time legs taker 0.00055. Net returns are fractions of px.
   Fills whose exit price is missing (NaN open, NaN o2 on a stop-at-239 /
   timeout path) give NaN net and are DROPPED per variant.
5. Variants (whole ladder, fixed):
   (a) BASE: all 5 rungs, mu = 1.0 everywhere (agent-TP-proxy = D0).
   (b) QUICK: all 5 rungs, mu = 1.0 on shallow (k < 4.0), mu = 0.5 on deep
       (k >= 4.0). Fills/sizes identical to BASE; only deep-rung exit nets
       differ (same race with a nearer tp).
   (c) NODEEP ("deep rungs removed"): only shallow rungs (k < 4.0),
       mu = 1.0. A strict subset of BASE fills.
6. Weights: w = size_mult per kept fill. PRIMARY comparison renormalises
   per anchor year per variant to equal mean exposure within variant-year:
   w' = w / mean(w over that variant's fills in that year) (mean 1;
   single-fill year -> w' = 1). Only allocation/exit quality is tested, not
   mean exposure. Raw (non-renormalised) sums are reported descriptively.
   BASE and QUICK share identical fills/weights, so their renormalisation
   factor is identical within a year; NODEEP renormalises over its own
   (shallow-only) fills.
7. Daily sums per variant per year: group w'*y by EXIT date (calendar UTC
   date of T+x, x = exit offset, 240 = next-bar open date). Yearly sum S =
   sum of daily sums. Worst day W = min daily sum. Cumulative path over
   exit dates sorted ascending from 0: C_k = cumsum; maxDD = max(0,
   max_{p<q}(C_p-C_q)) in w'*y units (0 when monotone non-decreasing).
   Win rate = fraction of kept fills with y > 0 strictly (equal-weight,
   descriptive). Deep-subset table (k >= 4.0 fills only, BASE nets vs QUICK
   nets on the SAME fills, raw w*y sums + means + wins) is descriptive.
8. Replica check: BASE fills must match oc_b1deeper B1 (5498 fills;
   per-coin 1067/1126/952/1179/1174) exactly; any mismatch is investigated
   before scoring (no silent divergence).

## Decision rule (fixed, from the assignment)

Per anchor year Y0..Y4, renormalised whole-ladder sums S_BASE(Y),
S_QUICK(Y), S_NODEEP(Y) and maxDDs DD_BASE(Y), DD_QUICK(Y), DD_NODEEP(Y).
PASS_sum(Y) iff S_QUICK(Y) >= S_BASE(Y) AND S_QUICK(Y) >= S_NODEEP(Y)
(not lower; equal passes; NaN -> FAIL). PASS_dd(Y) iff DD_QUICK(Y) <=
DD_BASE(Y) AND DD_QUICK(Y) <= DD_NODEEP(Y) (not worse; equal passes;
NaN -> FAIL). PROMISING iff (a) PASS_sum in >= 4 of 5 years AND
(b) PASS_dd in >= 4 of 5 years. Otherwise NOT PROMISING. One-line verdict
in REPORT.md. Descriptive only: deep-subset BASE-vs-QUICK, win rates, raw
sums, worst days, full-path sums/DD. The rule has zero fitted parameters,
so sequential and leave-one-year-out scoring coincide (same fixed rule, no
refit); per-year consistency above is the stability read (covers the
default >= 4/5 same-sign + >= 4/5 LOOY gate).

## Protocol (fixed)

- PLAN.md written before any outcome computation. Then scripts:
  `quick.py` (pure-numpy core: n vector, static fill, mu-parameterised
  D0-from-fill exit), `run.py` (per-coin loop, per-fill BASE/QUICK nets +
  exit-day sums -> results.json). Outputs: results.json, REPORT.md (tables
  + one-line verdict). Tests: `tests/test_oc_deeptp.py` (synthetic hand
  checks: mu=0.5 TP nearer/cheaper, stop-first, backstop priority, funding;
  causality: fill uses only m-1 closes; sigma excludes the bar).
- No commits; no edits outside research/tournament/oc_deeptp/
  (+ tests/test_oc_deeptp.py).
