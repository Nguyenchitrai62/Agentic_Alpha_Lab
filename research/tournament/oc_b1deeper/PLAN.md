# oc_b1deeper PLAN (pre-registered BEFORE any outcome is computed, 2026-10-05)

Idea #22: correlation-aware dip PRICE instead of (only) size.

## Hypothesis (fixed here)

v399-B1 shrinks a dip rung's size x 1/(1+n) at its fill minute, where n =
other majors flushing at that minute. Hypothesis: when the board is jointly
flushing, the dip is more likely to keep falling through the resting bid, so
moving the bid DEEPER while n >= 1 (instead of only shrinking size) gets a
better fill price / fewer bad fills at no worse tail. Direction
pre-registered: B1+deeper beats B1 (size only) on yearly size-weighted sums
at no worse maxDD. Fixed rule, no fitted parameters: while n >= 1 the rung's
bid is amended deeper (bot-executable: a bot can amend a resting bid every
minute); size x 1/(1+n) is kept exactly as B1.

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
- Resources: one process, one coin's full OHLC in RAM at a time (float32);
  all-five-coins 1m closes held as float32 arrays for the n detector;
  RAM < 3 GB.

## Exact causal definitions (frozen)

1. Bar open: O_c(T) = 1m `open` of coin c at minute T (no ffill; NaN =
   missing). sigma_4h(c,T): simple returns r_b = O_b/O_{b-1} - 1 of 4h bar
   opens; sigma = std(r over 360 bars ending at T-1, min_periods 120,
   ddof=1) = v293/oc_dipexit definition. Known at the bar open T. Bars with
   non-finite O, sg <= 0 or NaN are skipped (no rungs that bar).
2. Base rung level: lv(a,T,k) = O_a(T) * (1 - k*sg_a(T)).
3. Correlation count at minute m (live window offsets 16..238 inclusive,
   same as oc_dipexit): n(a,T,m) = number of OTHER majors b != a with
   finite O_b(T), finite C_b(T+m-1), finite sg_b(T) > 0 AND
   C_b(T+m-1) <= O_b(T) * (1 - 2.5*sg_b(T)). C uses the 1m `close` at
   minute T+m-1 (last fully closed minute; no cross-bar ffill, within-bar
   NaN stays NaN = not flushing). Own coin never counted (0..4). Flush at
   exactly 2.5 sigma counts (<=). This is v399_corr_dip_size.corr_size
   applied per minute (there: m = f-1 at the fill minute).
4. Arms per candidate rung (bar T, coin a, depth k):
   (a) B1 (size only): resting limit BUY at lv, live offsets 16..238. Fill
       at FIRST offset f with low(T+f) < lv (STRICT trade-through). Fill
       price = lv. n_fill = n(a,T,f). size_mult = 1/(1+n_fill).
   (b) B1+deeper: resting limit BUY amended each minute (bot-executable, uses
       only closes up to minute m-1): level in force at minute m is
       L(m) = lv * (1 - 0.5*n(a,T,m)*sg_a(T)) if n(a,T,m) >= 1 else lv.
       When n returns to 0 the bid goes back to lv. Fill at FIRST offset f
       with low(T+f) < L(f) (STRICT). Fill price = L(f) (deeper than or equal
       to lv). n_fill = n(a,T,f) at its OWN fill minute. size_mult =
       1/(1+n_fill) (kept as B1).
5. Post-fill exits (long), oc_dipexit D0 replica measured from the ACTUAL
   fill price px (px = lv for B1; px = L(f) for deeper): sl = px*(1-4*sg),
   bl = px*(1-8*sg), tp = px*(1+1.0*sg). Evaluated on minutes t in
   f+1..239 then timeout at 240 (next-bar open o2 = 1m open at T+240):
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
   kept fills with y > 0 strictly (equal-weight, descriptive except context).

## Decision rule (fixed, from the assignment)

Per anchor year Y0..Y4, with renormalised weights: S_B1(Y), S_deep(Y),
DD_B1(Y), DD_deep(Y). PASS_sum(Y) iff S_deep(Y) >= S_B1(Y) (not lower; equal
passes; NaN -> FAIL). PASS_dd(Y) iff DD_deep(Y) <= DD_B1(Y) (not worse; equal
passes; NaN -> FAIL). PROMISING iff (a) PASS_sum in >= 4 of 5 years AND
(b) PASS_dd in >= 4 of 5 years. Otherwise NOT PROMISING. One-line verdict in
REPORT.md. Descriptive only: fills, win rate, raw sums, worst days, full-path
sums/DD.

## Protocol (fixed)

- PLAN.md written before any outcome computation. Then scripts:
  `deeper.py` (pure-numpy core: n vector, dynamic-level fill, D0-from-fill
  exit), `run.py` (per-coin loop, per-arm fill ledger + exit-day sums ->
  results.json). Outputs: results.json, REPORT.md (tables + one-line
  verdict). Tests: `tests/test_oc_b1deeper.py` (synthetic hand checks +
  causality: fill uses only m-1 closes; sigma excludes the bar).
- No commits; no edits outside research/tournament/oc_b1deeper/
  (+ tests/test_oc_b1deeper.py).
