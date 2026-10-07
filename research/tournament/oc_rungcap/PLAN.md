# oc_rungcap PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

Idea #42: per-coin fill cap per bar (crash-bar guard).

## Hypothesis (fixed here)

oc_crashfreq: in crash bars all five rungs of a coin fill and stop together.
Hypothesis: capping a coin to at most 3 rung fills per 4h holding bar cuts
crash-bar clustering (shallower worst day / maxDD) at negligible cost to the
yearly size-weighted sum, because the 4th/5th rungs in the same bar are the
deepest, latest, most adversely-selected fills. Pre-registered direction: cap
(sum >= 97% of base) at no worse maxDD. Fixed rule, no fitted parameters.

## Universe and years (fixed)

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
   ddof=1) = v293/oc_dipexit/oc_b1deeper definition. Known at the bar open T.
   Bars with non-finite O, sg <= 0 or NaN are skipped (no rungs that bar).
2. Base rung level: lv(a,T,k) = O_a(T) * (1 - k*sg_a(T)). B1 (size only,
   oc_b1deeper arm B1 exact replica): resting limit BUY at lv, live offsets
   16..238. Fill at FIRST offset f with low(T+f) < lv (STRICT trade-through).
   Fill price = lv. n_fill = n(a,T,f) at its own fill minute (correlation
   count below). size w = 1/(1+n_fill).
3. Correlation count at minute m (live window offsets 16..238 inclusive,
   oc_b1deeper/v399-exact): n(a,T,m) = number of OTHER majors b != a with
   finite O_b(T), finite C_b(T+m-1), finite sg_b(T) > 0 AND
   C_b(T+m-1) <= O_b(T) * (1 - 2.5*sg_b(T)). C uses the 1m `close` at
   minute T+m-1 (last fully closed minute; no cross-bar ffill, within-bar
   NaN stays NaN = not flushing). Own coin never counted (0..4). Flush at
   exactly 2.5 sigma counts (<=).
4. Post-fill exits (long), oc_b1deeper D0 replica measured from the ACTUAL
   fill price px = lv: sl = px*(1-4*sg), bl = px*(1-8*sg),
   tp = px*(1+1.0*sg). Evaluated on minutes t in f+1..239 then timeout at
   240 (next-bar open o2 = 1m open at T+240): backstop touch (first t with
   low(t) <= bl) exits at min(bl,open(t)) taker; else TP touch (first t with
   high(t) > tp, STRICT) exits at tp maker; else close5 stop (clock minutes
   m with (m+1)%5==0, first m with close(m) <= sl) exits at open(m+1)
   (or o2 if m=239) taker; else timeout at o2 taker + funding 0.0001 if
   (T+4h).hour in (0,8,16). Priority stop-first: backstop wins ties
   (kb<=ks and kb<=kt); else TP wins only if strictly earlier (kt<ks);
   else stop; else timeout. A stop and TP in the same minute -> stop wins.
   Fees: fill maker 0.0002; TP leg maker 0.0002 (total 2*maker on TP);
   stop/backstop/time legs taker 0.00055. Net returns are fractions of px.
   Fills whose exit price is missing (NaN open, NaN o2 on a stop-at-239 /
   timeout path) give NaN net and are DROPPED (base and cap identically).
5. CAP rule (fixed, bot-executable): per (coin a, holding bar T), collect the
   base fills (up to 5, one per k). Order them by (fill offset f ASC,
   rung k ASC) — shallower rungs first on ties (price falls through shallow
   levels first; deterministic). Keep the FIRST 3; cancel the rest (removed
   rungs never fill, never exit, contribute 0). Bars with <= 3 fills are
   untouched. The cancellation uses only observed fill order within the bar
   (a bot sees fills 1..3 then cancels the remaining resting bids), so it is
   executable at minute granularity. Approximation disclosed: same-minute
   multi-level trade-throughs are serialised by k rather than all filling
   before a cancel can act (conservative: strict at-most-3).
6. Weights / scoring (PRIMARY = raw exposure, no renormalisation, because the
   cap changes exposure and the assignment tests cost vs base): w = size_mult
   per kept fill. Daily sums per arm per year: group w*y by EXIT date
   (calendar UTC date of T+x, x = exit offset, 240 = next-bar open date).
   Yearly sum S = sum of daily sums. Worst day W = min daily sum.
   Cumulative path over exit dates sorted ascending from 0: C_k = cumsum;
   maxDD = max(0, max_{p<q}(C_p - C_q)) in w*y units (0 when monotone
   non-decreasing). Win rate = fraction of kept fills with y > 0 strictly.
   Removed rungs: equal-weight mean(ret) and win rate (ret > 0 share), plus
   their w*y sum (drag removed). Side row only: renormalised (w' = w/mean(w
   per year-arm)) sums, to check the verdict does not hinge on exposure.

## Decision rule (fixed, from the assignment)

Per anchor year Y0..Y4 (raw w*y): S_base(Y), S_cap(Y), DD_base(Y),
DD_cap(Y). PASS_dd(Y) iff DD_cap(Y) <= DD_base(Y) (not worse; equal passes;
NaN -> FAIL). PASS_sum(Y) iff S_cap(Y) >= 0.97 * S_base(Y) (keeps >= 97%;
if S_base(Y) <= 0 require S_cap(Y) >= S_base(Y); NaN -> FAIL).
PROMISING iff (a) PASS_dd in >= 4 of 5 years AND (b) PASS_sum in >= 4 of 5
years. Otherwise NOT PROMISING. One-line verdict in REPORT.md. Descriptive
only: fills kept/removed per year, removed win/mean, worst days, full-path
sums/DD. The generic tournament default rule (same sign 4/5 + LOOY 4/5) is
superseded by this assignment-specific rule.

## Protocol (fixed)

- PLAN.md written before any outcome computation. Then scripts: `b1core.py`
  (vendored copy of oc_b1deeper deeper.py pure-numpy core: n vector, static
  fill, D0-from-fill exit, identical constants), `run_cap.py` (per-coin loop,
  B1 base ledger + per-(coin,bar) first-3 cap -> results.json). Outputs:
  results.json, REPORT.md (tables + one-line verdict). Tests:
  `tests/test_oc_rungcap.py` (synthetic hand checks: cap keeps first 3 by
  (f,k), <= 3 untouched, same-minute tie-break, scoring helpers).
- No commits; no edits outside research/tournament/oc_rungcap/
  (+ tests/test_oc_rungcap.py).
