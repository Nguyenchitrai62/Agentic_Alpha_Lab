# oc_lowvolrung PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

Idea #33: regime-conditional extra shallow rung.

## Hypothesis (fixed here)

A 2.0-sigma rung added GLOBALLY raised drawdown (v401). Hypothesis: in calm
regimes dislocations are shallow (oc_recent: the most-recent year shows record
dip fills at ~1/10 the edge), so a shallow 2.0-sigma rung ADDED ONLY when the
coin is in a walk-forward low-volatility regime captures shallow-reversion
edge without the global-DD cost. Direction pre-registered: the augmented
ladder (baseline R2 rungs + gated 2.0 rung) beats the baseline ladder on
yearly size-weighted sums at no worse maxDD. Fixed rule, no fitted
parameters: the 2.0 rung exists only when the coin's sigma4 is in its
walk-forward LOWEST tercile (cut-offs from data strictly before the anchor
year); size = the 2.5-sigma rung's B1 rule x 1/(1+n); D0 exits.

## Data (fixed here, all in repo - no fetch)

- 1m klines: `data/raw/btc_intraday_20260924` (BTC),
  `data/raw/majors_intraday_20260924` (ETH/SOL/BNB/XRP). Minutes used:
  t in [2020-08-01 00:00, 2026-09-24 00:00] UTC. Missing minutes (NaN) never
  fill, never trigger an exit touch, and never count as flushing.
- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- Baseline rungs k in {2.5, 3.0, 3.5, 4.0, 5.0} (R2 depths). Extra rung k=2.0.
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
  RAM < 3 GB, single process (MEDIUM job).

## Exact causal definitions (frozen)

1. Bar open: O_c(T) = 1m `open` of coin c at minute T (no ffill; NaN =
   missing). sigma_4h(c,T): simple returns r_b = O_b/O_{b-1} - 1 of 4h bar
   opens; sigma = std(r over 360 bars ending at T-1, min_periods 120,
   ddof=1) = v293/oc_dipexit/oc_b1deeper definition. Known at the bar open T.
   Bars with non-finite O, sg <= 0 or NaN are skipped (no rungs that bar).
2. Walk-forward low-vol gate (per coin, per anchor year, causal): for anchor
   A_Y, cutoff q(c,Y) = 1/3 quantile (linear interpolation) of the finite
   sigma_c(T) values over grid bars with open T < A_Y (strictly before the
   anchor; finite-sigma bars only). The extra 2.0 rung is ARMED at bar T
   (in year Y, coin c) iff sigma_c(T) is finite and sigma_c(T) <= q(c,Y).
   q uses no data at/after A_Y. Baseline rungs are always armed.
3. Rung level: lv(a,T,k) = O_a(T) * (1 - k*sg_a(T)).
4. Correlation count at minute m (live window offsets 16..238 inclusive,
   oc_b1deeper-exact): n(a,T,m) = number of OTHER majors b != a with
   finite O_b(T), finite C_b(T+m-1), finite sg_b(T) > 0 AND
   C_b(T+m-1) <= O_b(T) * (1 - 2.5*sg_b(T)). C uses the 1m `close` at
   minute T+m-1 (last fully closed minute; no cross-bar ffill, within-bar
   NaN stays NaN = not flushing). Own coin never counted (0..4). Flush at
   exactly 2.5 sigma counts (<=).
5. Fill (B1 static-bid replica, oc_b1deeper arm (a), for baseline rungs AND
   the extra rung): resting limit BUY at lv, live offsets 16..238. Fill at
   FIRST offset f with low(T+f) < lv (STRICT trade-through). Fill price = lv.
   n_fill = n(a,T,f). size w = 1/(1+n_fill). No dynamic amendment (size-only
   B1; the deeper-price variant is NOT used here).
6. Post-fill exits (long), oc_b1deeper D0 replica measured from the fill
   price px = lv: sl = px*(1-4*sg), bl = px*(1-8*sg), tp = px*(1+1.0*sg).
   Evaluated on minutes t in f+1..239 then timeout at 240 (next-bar open
   o2 = 1m open at T+240): backstop touch (first t with low(t) <= bl)
   exits at min(bl,open(t)) taker; else TP touch (first t with high(t) > tp,
   STRICT) exits at tp maker; else close5 stop (clock minutes m with
   (m+1)%5==0, first m with close(m) <= sl) exits at open(m+1) (or o2 if
   m=239) taker; else timeout at o2 taker + funding 0.0001 if
   (T+4h).hour in (0,8,16). Priority stop-first: backstop wins ties
   (kb<=ks and kb<=kt); else TP wins only if strictly earlier (kt<ks);
   else stop; else timeout. A stop and TP in the same minute -> stop wins.
   Fees: fill maker 0.0002; TP leg maker 0.0002 (total 2*maker on TP);
   stop/backstop/time legs taker 0.00055. Net returns are fractions of px.
   Fills whose exit price is missing (NaN open, NaN o2 on a stop-at-239 /
   timeout path) give NaN net and are DROPPED.
7. Ladders: WITHOUT = all baseline-rung fills (5 depths); WITH = WITHOUT
   plus the gated extra-2.0 fills. Weights are RAW w = 1/(1+n_fill)
   (no renormalisation: both ladders share baseline exposure; the extra
   rung adds exposure, so rescaling would confound the comparison).
8. Daily sums per ladder per year: group w*y by EXIT date (calendar UTC date
   of T+x, x = exit offset, 240 = next-bar open date). Yearly sum S = sum of
   daily sums. Worst day W = min daily sum. Cumulative path over exit dates
   sorted ascending from 0: C_k = cumsum; maxDD = max(0, max_{p<q}(C_p-C_q))
   in w*y units (0 when monotone non-decreasing). Extra-rung standalone per
   year: fills n_x, win rate = fraction with y > 0 strictly, mean ret,
   raw sum sum(w*y).
9. Post-hoc changes: none allowed; any change after seeing outcomes is a new
   disclosed variant (none pre-registered; at most this single comparison).

## Decision rule (fixed, from the assignment's idea paragraph)

Per anchor year Y0..Y4, RAW weights: S_base(Y), S_with(Y), DD_base(Y),
DD_with(Y). PASS_sum(Y) iff S_with(Y) > S_base(Y) STRICTLY (higher; equal
fails; NaN or a year with zero extra fills -> FAIL). PASS_dd(Y) iff
DD_with(Y) <= DD_base(Y) (not worse; equal passes; NaN -> FAIL). PROMISING
iff (a) PASS_sum in >= 4 of 5 years AND (b) PASS_dd in >= 4 of 5 years.
Otherwise NOT PROMISING. One-line verdict in REPORT.md. Descriptive only:
extra-rung fills/win/mean/sum, worst days, full-path sums/DD, cut-offs and
armed shares, leave-one-year-out sums (no selection on LOO).

## Protocol (fixed)

- PLAN.md written before any outcome computation. Then scripts: `core.py`
  (vendored oc_b1deeper replica: n vector, static fill, D0-from-fill exit;
  no import from other workers' folders), `run.py` (cut-offs per coin-year,
  per-coin loop, baseline + gated-extra ledgers + exit-day sums ->
  results.json). Outputs: results.json, REPORT.md (tables + one-line
  verdict). Tests: `tests/test_oc_lowvolrung.py` (synthetic hand checks +
  causality: fill uses only m-1 closes; sigma excludes the bar; gate uses
  only pre-anchor sigma with <= boundary).
- No commits; no edits outside research/tournament/oc_lowvolrung/
  (+ tests/test_oc_lowvolrung.py).
