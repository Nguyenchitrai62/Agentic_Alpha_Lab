# oc_b1wide PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

Idea #58: wider flush detector for B1 (signal only; trading stays majors-only).

## Hypothesis (fixed here)

v399-B1 shrinks a dip rung's size x 1/(1+n) at its fill minute, where n =
other MAJORS flushing at that minute. Hypothesis: counting a wider board —
the 5 alts BCH, DOT, ETC, XLM, ATOM — at half weight sharpens the flush
signal, so size x 1/(1+n_wide) with n_wide = n + 0.5*n_alt allocates less to
joint-flush fills (which keep falling) at no worse tail. Direction
pre-registered: B1-wide beats or ties base B1 on yearly size-weighted sums
at no worse maxDD. Fixed rule, no fitted parameters: 0.5 alt weight, 2.5
sigma threshold, same R2 depths and D0 exits as the oc_b1deeper replica.

## Data (fixed here, all in repo — no fetch)

- 1m klines: `data/raw/btc_intraday_20260924` (BTC),
  `data/raw/majors_intraday_20260924` (ETH/SOL/BNB/XRP),
  `data/raw/alts2020_intraday_20260930` (BCHUSDT, DOTUSDT, ETCUSDT, XLMUSDT,
  ATOMUSDT 1m files only). Minutes used: t < 2026-09-24 00:00 UTC. Missing
  minutes (NaN) never fill, never trigger an exit touch, and never count as
  flushing.
- Traded coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
  Alts are SIGNAL ONLY (sizing input); no alt positions, no alt fills.
- Rungs k in {2.5, 3.0, 3.5, 4.0, 5.0} (R2 depths).
- Bars: standard 4h grid, bar j covers [START + 4h*j, START + 4h*j + 4h) with
  START = 2020-08-01 00:00 UTC. Only bars with open T in
  [2021-09-24 00:00, 2026-09-24 00:00) UTC are traded (5 anchor years
  Y0..Y4 = [anchor, anchor+365d), anchors 2021-09-24..2025-09-24, keyed by T).
- Market data up to 2026-09-24 00:00 UTC is read per the assignment (all five
  years are research data; any PROMISING result needs prospective validation
  before real money). Disclosed against RULES.md 2 / VF_COMMON hidden-year
  conventions.
- Resources: one process, one traded coin's full H/L in RAM at a time
  (float32); all-ten-coins (5 majors + 5 alts) 1m opens/closes held as float32
  arrays for the n detector; RAM < 3 GB.

## Exact causal definitions (frozen)

1. Bar open: O_c(T) = 1m `open` of coin c at minute T (no ffill; NaN =
   missing). sigma_4h(c,T): simple returns r_b = O_b/O_{b-1} - 1 of 4h bar
   opens; sigma = std(r over 360 bars ending at T-1, min_periods 120,
   ddof=1) = v293/oc_dipexit/oc_b1deeper definition, applied identically to
   each alt. Known at the bar open T. Bars with non-finite O, sg <= 0 or NaN
   are skipped (no rungs that bar).
2. Base rung level: lv(a,T,k) = O_a(T) * (1 - k*sg_a(T)).
3. Majors flush count at minute m (live window offsets 16..238 inclusive,
   same as oc_b1deeper): n(a,T,m) = number of OTHER majors b != a with
   finite O_b(T), finite C_b(T+m-1), finite sg_b(T) > 0 AND
   C_b(T+m-1) <= O_b(T) * (1 - 2.5*sg_b(T)). C uses the 1m `close` at
   minute T+m-1 (last fully closed minute; no cross-bar ffill, within-bar
   NaN stays NaN = not flushing). Own coin never counted (0..4). Flush at
   exactly 2.5 sigma counts (<=). v399/oc_b1deeper-exact.
4. Alt flush count at minute m (same window, same rule per alt):
   n_alt(T,m) = number of the 5 alts d in {BCH, DOT, ETC, XLM, ATOM} with
   finite O_d(T), finite C_d(T+m-1), finite sg_d(T) > 0 AND
   C_d(T+m-1) <= O_d(T) * (1 - 2.5*sg_d(T)) (0..5; NaN = not flushing).
   Wide count: n_wide(a,T,m) = n(a,T,m) + 0.5*n_alt(T,m)
   (values 0, 0.5, ..., 6.5). Fixed 0.5 alt weight, fixed 2.5 sigma.
5. Arms per candidate rung (bar T, coin a, depth k) — IDENTICAL fills and
   exits, only the size weight differs (signal-only study):
   (a) Base B1: resting limit BUY at lv, live offsets 16..238. Fill at FIRST
       offset f with low(T+f) < lv (STRICT trade-through). Fill price = lv.
       n_fill = n(a,T,f). w_base = 1/(1+n_fill).
   (b) B1-wide: SAME rung, SAME fill minute f, SAME fill price lv, SAME
       D0 exit (below). n_wide_fill = n(a,T,f) + 0.5*n_alt(T,f) at its OWN
       fill minute f (alts read at C(T+f-1), i.e. minute f-1 closes).
       w_wide = 1/(1+n_wide_fill). No alt trading; fill set identical to
       base by construction (same f rule); only weights differ.
6. Post-fill exits (long), oc_b1deeper D0 replica measured from the fill
   price px = lv for BOTH arms: sl = px*(1-4*sg), bl = px*(1-8*sg),
   tp = px*(1+1.0*sg). Evaluated on minutes t in f+1..239 then timeout at
   240 (next-bar open o2 = 1m open at T+240): backstop touch (first t with
   low(t) <= bl) exits at min(bl,open(t)) taker; else TP touch (first t with
   high(t) > tp, STRICT) exits at tp maker; else close5 stop (clock minutes
   m with (m+1)%5==0, first m with close(m) <= sl) exits at open(m+1) (or
   o2 if m=239) taker; else timeout at o2 taker + funding 0.0001 if
   (T+4h).hour in (0,8,16). Priority stop-first: backstop wins ties
   (kb<=ks and kb<=kt); else TP wins only if strictly earlier (kt<ks);
   else stop; else timeout. A stop and TP in the same minute -> stop wins.
   Fees: fill maker 0.0002; TP leg maker 0.0002 (total 2*maker on TP);
   stop/backstop/time legs taker 0.00055. Net returns are fractions of px.
   Fills whose exit price is missing (NaN open, NaN o2 on a stop-at-239 /
   timeout path) give NaN net and are DROPPED (identically in both arms,
   since ret is shared).
7. Weights: PRIMARY comparison renormalises per anchor year to equal mean
   exposure within arm: w' = w / mean(w over that arm's fills in that year)
   (mean 1; single-fill year -> w' = 1). Only ALLOCATION quality is tested,
   not mean exposure. Raw (non-renormalised) sums reported descriptively.
8. Daily sums per arm per year: group w'*y by EXIT date (calendar UTC date of
   T+x, x = exit offset, 240 = next-bar open date). Yearly sum S = sum of
   daily sums. Worst day W = min daily sum. Cumulative path over exit dates
   sorted ascending from 0: C_k = cumsum; maxDD = max(0, max_{p<q}(C_p-C_q))
   in w'*y units (0 when monotone non-decreasing). Efficiency E = S/maxDD
   (descriptive; maxDD = 0 -> +inf if S > 0, 0.0 if S == 0, -inf if S < 0).
   Win rate = fraction of kept fills with y > 0 strictly (equal-weight,
   descriptive). Because fills are shared, n/win/mean-ret are identical
   across arms; only S/W/DD/E (weight-driven) can differ.

## Decision rule (fixed, from the assignment — overrides the default)

Per anchor year Y0..Y4, with renormalised weights: S_base(Y), S_wide(Y),
DD_base(Y), DD_wide(Y). PASS_dd(Y) iff DD_wide(Y) <= DD_base(Y) (not worse;
equal passes; NaN -> FAIL). PASS_sum(Y) iff S_wide(Y) >= 0.97*S_base(Y)
(sum at least 97% of base; equal passes; NaN -> FAIL; applied mechanically
even if S_base(Y) <= 0). PROMISING iff (a) PASS_dd in >= 4 of 5 years AND
(b) PASS_sum in >= 4 of 5 years. Otherwise NOT PROMISING. One-line verdict
in REPORT.md. Descriptive only: fills, win rate, raw sums, worst days,
efficiencies, full-path sums/DD, leave-one-year-out sums.

## Protocol (fixed)

- PLAN.md written before any outcome computation. Then scripts: `wide.py`
  (pure-numpy core: majors n vector, alt n vector, wide size mult, fill
  finder, D0-from-fill exit — oc_b1deeper replica), `run.py` (per-coin loop,
  shared fill ledger + both weight sets -> results.json). Outputs:
  results.json, REPORT.md (tables + one-line verdict). Tests:
  `tests/test_oc_b1wide.py` (synthetic hand checks: alt count incl. 0.5
  weight, shared-fill identity, exit replica spot check, renormalisation,
  decision-rule edges + causality: detection uses only m-1 closes; sigma
  excludes the bar).
- No commits; no edits outside research/tournament/oc_b1wide/
  (+ tests/test_oc_b1wide.py).
