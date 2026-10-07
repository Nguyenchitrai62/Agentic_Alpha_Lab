# oc_tpdecay PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

Idea #54: time-decaying dip take-profit.

## Hypothesis (fixed here)

Timeouts carry much of the dip losses. A filled rung's fixed +1.0-sigma TP is
often just out of reach inside its 4h holding bar, so the rung times out at the
next-bar open (taker + adverse drift). Hypothesis: decaying the TP level
linearly with time inside the holding bar — from 1.0 sigma at the fill minute
to 0.5 sigma at the bar end, re-posted as a resting limit each minute
(bot-executable) — converts some timeout losses / small timeout wins into
earlier maker TP fills at a slightly smaller gain, raising the yearly
size-weighted sum at no worse tail. Direction pre-registered: DECAY beats BASE
(fixed +1.0-sigma TP) on yearly size-weighted sums at no worse maxDD. Fixed
rule, no fitted parameters.

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
   ddof=1) = v293/oc_dipexit/oc_b1deeper definition. Known at the bar open T.
   Bars with non-finite O, sg <= 0 or NaN are skipped (no rungs that bar).
2. Base rung level: lv(a,T,k) = O_a(T) * (1 - k*sg_a(T)).
3. Correlation count at minute m (live window offsets 16..238 inclusive,
   same as oc_b1deeper/oc_dipexit): n(a,T,m) = number of OTHER majors b != a
   with finite O_b(T), finite C_b(T+m-1), finite sg_b(T) > 0 AND
   C_b(T+m-1) <= O_b(T) * (1 - 2.5*sg_b(T)). C uses the 1m `close` at
   minute T+m-1 (last fully closed minute; no cross-bar ffill, within-bar
   NaN stays NaN = not flushing). Own coin never counted (0..4). Flush at
   exactly 2.5 sigma counts (<=). v399-exact, copied from oc_b1deeper.
4. Fills (ONE shared fill set for both arms; rung replica = oc_b1deeper B1):
   resting limit BUY at lv, live offsets 16..238. Fill at FIRST offset f
   with low(T+f) < lv (STRICT trade-through). Fill price px = lv.
   n_fill = n(a,T,f). size w = 1/(1+n_fill) (B1 sizes, both arms).
   NaN lows never fill. A fill is kept only if its exit net is finite under
   BOTH arms (dropped per rung if either arm's exit price is missing, so the
   comparison stays paired).
5. Post-fill exits (long), D0 replica from px except the TP leg:
   sl = px*(1-4*sg), bl = px*(1-8*sg).
   BASE TP: tp_base = px*(1+1.0*sg), fixed.
   DECAY TP schedule (bot-executable, uses only px, sg, f — all known at the
   fill minute): for post-fill minute t in f+1..239,
   TP(t) = px * (1 + sg * (1.0 - 0.5*(t-f)/(240-f))).
   At t=f+1 the factor is just under 1.0; at t=239..240 it is ~0.5
   (exactly 0.5 at m=240). Re-posted as a resting limit each minute.
   Evaluated on minutes t in f+1..239 then timeout at 240 (next-bar open
   o2 = 1m open at T+240):
   backstop touch (first t with low(t) <= bl) exits at min(bl,open(t))
   taker; else TP touch — BASE: first t with high(t) > tp_base (STRICT)
   exits at tp_base maker; DECAY: first t with high(t) > TP(t) (STRICT,
   time-varying level) exits at TP(t) maker; else close5 stop (clock
   minutes m with (m+1)%5==0, first m with close(m) <= sl) exits at
   open(m+1) (or o2 if m=239) taker; else timeout at o2 taker + funding
   0.0001 if (T+4h).hour in (0,8,16). Priority stop-first: backstop wins
   ties (kb<=ks and kb<=kt); else TP wins only if strictly earlier
   (kt<ks); else stop; else timeout. A stop and TP in the same minute ->
   stop wins. Fees: fill maker 0.0002; TP leg maker 0.0002 (total 2*maker
   on TP); stop/backstop/time legs taker 0.00055. Net returns are fractions
   of px. Fills whose exit price is missing (NaN open, NaN o2 on a
   stop-at-239/timeout path) give NaN net and are DROPPED per rung (paired).
6. Weights: w = 1/(1+n_fill) per kept fill (identical for both arms by
   construction). PRIMARY comparison renormalises per anchor year to equal
   mean exposure pooled over both arms: w' = w / mean(w over kept fills in
   that year) (mean 1; single-fill year -> w' = 1). Paired fills => the same
   w' multiplies base and decay nets fill-by-fill; only EXIT quality is
   tested, not mean exposure. Raw (non-renormalised) sums reported
   descriptively.
7. Daily sums per arm per year: group w'*y by EXIT date (calendar UTC date of
   T+x, x = exit offset, 240 = next-bar open date). Yearly sum S = sum of
   daily sums. Win rate = fraction of kept fills with y > 0 strictly.
   Timeout share = fraction with how == "time". Worst day W = min daily sum.
   Cumulative path over exit dates sorted ascending from 0: C_k = cumsum;
   maxDD = max(0, max_{p<q}(C_p-C_q)) in w'*y units (0 when monotone
   non-decreasing).

## Decision rule (fixed, from the assignment)

Per anchor year Y0..Y4, with renormalised weights: S_base(Y), S_dec(Y),
DD_base(Y), DD_dec(Y). PASS_sum(Y) iff S_dec(Y) >= S_base(Y) (not lower;
equal passes; NaN -> FAIL). PASS_dd(Y) iff DD_dec(Y) <= DD_base(Y) (not
worse; equal passes; NaN -> FAIL). PROMISING iff (a) PASS_sum in >= 4 of 5
years AND (b) PASS_dd in >= 4 of 5 years. Otherwise NOT PROMISING. One-line
verdict in REPORT.md. Descriptive only: fills, win/timeout shares, worst
days, full-path sums/DD, leave-one-year-out sums (sum over 4 of 5 years,
base vs decay, 5 folds).

## Protocol (fixed)

- PLAN.md written before any outcome computation. Then scripts:
  `tpdecay.py` (pure-numpy core: n vector, B1 fill, base + decaying-TP
  exits), `run.py` (per-coin loop, paired fill ledger + exit-day sums ->
  results.json). Outputs: results.json, REPORT.md (tables + one-line
  verdict). Tests: `tests/test_oc_tpdecay.py` (synthetic hand checks:
  decay schedule endpoints, TP touch on decaying level, stop-first
  priority, timeout/funding parity, base-vs-decay conversion case +
  causality: fill uses only m-1 closes; sigma excludes the bar; TP(t)
  uses only px/sg/f).
- No commits; no edits outside research/tournament/oc_tpdecay/
  (+ tests/test_oc_tpdecay.py).
