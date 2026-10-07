# oc_btclead PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

Idea #41: BTC-lead alt dip levels.

## Hypothesis (fixed here)

In market-wide flushes BTC usually moves first and alts follow with higher
beta. A static alt dip bid at lv gets filled too early (before the alt
follows BTC down), then rides the alt leg down. Hypothesis: when BTC has
already flushed >= 1.5 of its own 4h sigma below its bar open, move the alt
resting bid deeper proportional to the alt's BTC beta times the BTC drop
(in sigma units), so the alt bid fills at a better price / skips fills that
would immediately go against. Direction pre-registered: BTC-lead beats the
B1 (size-only) base on yearly size-weighted sums at no worse maxDD. Fixed
rule, no fitted parameters beyond the walk-forward beta (fit strictly before
the bar, frozen window below).

## Data (fixed here, all in repo - no fetch)

- 1m klines: `data/raw/btc_intraday_20260924` (BTC),
  `data/raw/majors_intraday_20260924` (ETH/SOL/BNB/XRP). Minutes used:
  t < 2026-09-24 00:00 UTC. Missing minutes (NaN) never fill, never trigger
  an exit touch, never count as flushing, and never trigger the BTC-lead
  shift.
- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- Rungs k in {2.5, 3.0, 3.5, 4.0, 5.0} (R2 depths, oc_b1deeper replica).
- Bars: standard 4h grid, bar j covers [START + 4h*j, START + 4h*j + 4h) with
  START = 2020-08-01 00:00 UTC. Only bars with open T in
  [2021-09-24 00:00, 2026-09-24 00:00) UTC are traded (5 anchor years
  Y0..Y4 = [anchor, anchor+365d), anchors 2021-09-24..2025-09-24, keyed by T).
- Market data up to 2026-09-24 00:00 UTC is read per the assignment (all five
  years are research data; any PROMISING result needs prospective validation
  before real money). Disclosed against RULES.md 2 / VF_COMMON hidden-year
  conventions.
- Resources: one process, one coin's full H/L in RAM at a time (float32);
  all-five-coins 1m opens/closes held as float32 arrays for the n detector
  and the BTC-lead signal; RAM < 3 GB.

## Exact causal definitions (frozen)

1. Bar open: O_c(T) = 1m `open` of coin c at minute T (no ffill; NaN =
   missing). sigma_4h(c,T): simple returns r_b = O_b/O_{b-1} - 1 of 4h bar
   opens; sigma = std(r over 360 bars ending at T-1, min_periods 120,
   ddof=1) = v293/oc_dipexit/oc_b1deeper definition. Known at the bar open T.
   Bars with non-finite O, sg <= 0 or NaN are skipped (no rungs that bar).
2. Beta (walk-forward, causal, frozen): for alt a vs BTC, let R be simple
   returns of 4h bar opens (same series as sigma). beta_a(T) = OLS slope
   Cov(R_a, R_BTC) / Var(R_BTC) over the 180 returns immediately before the
   bar: R[T-180 .. T-1] in bar-index terms (i.e. returns ending at bar j-1
   for bar j), min_periods 60, ddof=1. If fewer than 60 finite paired
   returns, or Var(R_BTC) <= 0 / non-finite, beta = NaN -> treated as 1.0
   for the level rule (documented fallback; no fitting). Raw beta is
   clipped to [0, 3] (no leverage inversion, no explosive beta; momentum
   crash protection). Uses only bar opens strictly before T.
3. Base rung level: lv(a,T,k) = O_a(T) * (1 - k*sg_a(T)).
4. Correlation count at minute m (live window offsets 16..238 inclusive,
   same as oc_b1deeper / oc_dipexit): n(a,T,m) = number of OTHER majors
   b != a with finite O_b(T), finite C_b(T+m-1), finite sg_b(T) > 0 AND
   C_b(T+m-1) <= O_b(T) * (1 - 2.5*sg_b(T)). C uses the 1m `close` at
   minute T+m-1 (last fully closed minute; no cross-bar ffill, within-bar
   NaN stays NaN = not flushing). Own coin never counted (0..4). Flush at
   exactly 2.5 sigma counts (<=). This is v399_corr_dip_size.corr_size
   applied per minute.
5. BTC-lead signal at minute m (uses only closes up to minute m-1):
   s_BTC(m) = (O_BTC(T) - C_BTC(T+m-1)) / (O_BTC(T) * sg_BTC(T)) = BTC drop
   in sigma units (positive when down). Requires finite O_BTC(T),
   sg_BTC(T) > 0, finite C_BTC(T+m-1). BTC-flushed(m) iff s_BTC(m) >= 1.5,
   i.e. C_BTC(T+m-1) <= O_BTC(T) * (1 - 1.5*sg_BTC(T)) (exact boundary
   counts, same convention as n).
   Alt-not-yet-at-rung(m) iff finite C_a(T+m-1) AND C_a(T+m-1) > lv(a,T,k)
   (alt close has not yet reached its own rung; NaN -> condition FALSE, no
   shift). Rationale: once the alt is already at its rung the early-fill
   risk has materialised; the bid stays where the base rule put it.
6. Arms per candidate rung (bar T, coin a, depth k):
   (a) BASE = B1 (size only, oc_b1deeper replica): resting limit BUY at lv,
       live offsets 16..238. Fill at FIRST offset f with low(T+f) < lv
       (STRICT trade-through). Fill price = lv. n_fill = n(a,T,f).
       size_mult = 1/(1+n_fill).
   (b) BTC-LEAD: BTC's own rungs UNCHANGED (identical to BASE for
       a = BTCUSDT). For alts a in {ETH,SOL,BNB,XRP}: resting limit BUY
       amended each minute (bot-executable, uses only closes up to m-1):
       level in force at minute m is
         L(m) = lv * (1 - 0.5*beta_clip(a,T)*s_BTC(m)*sg_a(T))
       if (BTC-flushed(m) AND alt-not-yet-at-rung(m) AND all of
       beta_clip, s_BTC, sg_a finite with sg_a > 0 and L(m) > 0 and
       L(m) < lv), else L(m) = lv.
       When the condition turns false the bid goes back to lv (up only,
       never above lv: L(m) = min(L(m), lv)). Fill at FIRST offset f with
       low(T+f) < L(f) (STRICT). Fill price = L(f) (deeper than or equal
       to lv). n_fill = n(a,T,f) at its OWN fill minute (same n detector
       as BASE). size_mult = 1/(1+n_fill) (kept as B1).
7. Post-fill exits (long), oc_dipexit D0 replica measured from the ACTUAL
   fill price px (px = lv for BASE; px = L(f) for BTC-LEAD): sl =
   px*(1-4*sg), bl = px*(1-8*sg), tp = px*(1+1.0*sg). Evaluated on minutes
   t in f+1..239 then timeout at 240 (next-bar open o2 = 1m open at T+240):
   backstop touch (first t with low(t) <= bl) exits at min(bl,open(t))
   taker; else TP touch (first t with high(t) > tp, STRICT) exits at tp
   maker; else close5 stop (clock minutes m with (m+1)%5==0, first m with
   close(m) <= sl) exits at open(m+1) (or o2 if m=239) taker; else timeout
   at o2 taker + funding 0.0001 if (T+4h).hour in (0,8,16). Priority
   stop-first: backstop wins ties (kb<=ks and kb<=kt); else TP wins only if
   strictly earlier (kt<ks); else stop; else timeout. A stop and TP in the
   same minute -> stop wins. Fees: fill maker 0.0002; TP leg maker 0.0002
   (total 2*maker on TP); stop/backstop/time legs taker 0.00055. Net returns
   are fractions of px. Fills whose exit price is missing (NaN open, NaN o2
   on a stop-at-239/timeout path) give NaN net and are DROPPED per arm.
8. Weights: w = size_mult per kept fill. PRIMARY comparison renormalises per
   anchor year to equal mean exposure within arm: w' = w / mean(w over that
   arm's fills in that year) (mean 1; single-fill year -> w' = 1). Only
   ALLOCATION/price quality is tested, not mean exposure. Raw
   (non-renormalised) sums are reported descriptively.
9. Daily sums per arm per year: group w'*y by EXIT date (calendar UTC date of
   T+x, x = exit offset, 240 = next-bar open date). Yearly sum S = sum of
   daily sums. Worst day W = min daily sum. Cumulative path over exit dates
   sorted ascending from 0: C_k = cumsum; maxDD = max(0, max_{p<q}(C_p-C_q))
   in w'*y units (0 when monotone non-decreasing). Win rate = fraction of
   kept fills with y > 0 strictly (equal-weight, descriptive except context).

## Decision rule (fixed, from the assignment)

Per anchor year Y0..Y4, with renormalised weights: S_base(Y), S_lead(Y),
DD_base(Y), DD_lead(Y). PASS_sum(Y) iff S_lead(Y) >= S_base(Y) (not lower;
equal passes; NaN -> FAIL). PASS_dd(Y) iff DD_lead(Y) <= DD_base(Y) (not
worse; equal passes; NaN -> FAIL). PROMISING iff (a) PASS_sum in >= 4 of 5
years AND (b) PASS_dd in >= 4 of 5 years. Otherwise NOT PROMISING. One-line
verdict in REPORT.md. Supplementary (default template): LOYO_sum(i) =
sum_{Y != i}(S_lead - S_base) >= 0; holds in >= 4/5 reported descriptively;
the verdict above is already a same-sign >= 4/5 rule on both metrics, and a
LOYO failure is noted as a caveat. Descriptive only: fills, win rate, raw
sums, worst days, full-path sums/DD, per-coin fills.

## Protocol (fixed)

- PLAN.md written before any outcome computation. Then scripts:
  `btclead.py` (pure-numpy core: n vector, BTC sigma-drop vector,
  beta-clip + dynamic-level fill, D0-from-fill exit), `run.py` (per-coin
  loop, per-arm fill ledger + exit-day sums -> results.json). Outputs:
  results.json, REPORT.md (tables + one-line verdict). Tests:
  `tests/test_oc_btclead.py` (synthetic hand checks + causality: fill/signal
  use only m-1 closes; sigma/beta exclude the bar; BTC boundary; alt-gate;
  level never above lv).
- No commits; no edits outside research/tournament/oc_btclead/
  (+ tests/test_oc_btclead.py).
