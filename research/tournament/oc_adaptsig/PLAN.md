# oc_adaptsig PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

Idea #25: vol-adaptive dip sigma.

## Hypothesis (fixed here)

oc_crashfreq: in the worst one-bar dip losses ALL 25 rungs (5 coins x 5 depths)
fill and most stop out. The 360-bar sigma4 (v293 definition: pct_change of 4h
opens, rolling 360 std, shifted 1) is stale when volatility jumps, so rungs sit
too close, stops too tight, and the n detector too blind in fast vol.
Hypothesis: sigma_eff = max(sigma360, sigma42) widens rung levels, the
close-stop, the backstop and the TP, and desensitises the correlation count, in
fast-vol bars, cutting same-bar stop cascades at no worse drawdown and better
capital efficiency. Direction pre-registered: ADAPT (sigma_eff) beats BASE
(sigma360) on yearly maxDD (not worse) and efficiency sum/maxDD (better).
Fixed rule, no fitted parameters: 360 vs 42 bars, min_periods 120 vs 30,
max(), F=2.5, M_SL 4, backstop 8, TP 1.0.

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
   missing). Returns r_b = O_b/O_{b-1} - 1 of 4h bar opens.
   sg360_c(T) = std(r over 360 bars ending at T-1, min_periods 120, ddof=1)
   = v293/oc_b1deeper definition, shifted 1, known at the bar open T.
   sg42_c(T) = std(r over the last 42 bars ending at T-1 (7 days),
   min_periods 30, ddof=1), shifted 1, known at the bar open T.
   sg_eff_c(T) = max(sg360, sg42) when both finite; = sg360 when only sg360
   finite. Bars with non-finite O, sg360 <= 0/NaN are skipped (no rungs that
   bar, either arm). Bars where sg42 is NaN use sg_eff = sg360 (counted as
   NOT adaptive in the share statistic). sg_eff <= 0/NaN -> skip ADAPT rungs
   that bar (BASE still trades if its own sg360 is valid).
2. Rung level per arm: BASE lv = O_a(T)*(1 - k*sg360_a(T));
   ADAPT lv = O_a(T)*(1 - k*sg_eff_a(T)). Non-finite/lv <= 0 skipped.
3. Correlation count at minute m (live offsets 16..238 inclusive, same as
   oc_b1deeper/oc_dipexit): BASE n(a,T,m) counts OTHER majors b != a with
   finite O_b(T), finite C_b(T+m-1), finite sg360_b(T) > 0 AND
   C_b(T+m-1) <= O_b(T)*(1 - 2.5*sg360_b(T)).
   ADAPT n_eff(a,T,m) uses sg_eff_b(T) in the same formula (F=2.5 fixed).
   C uses the 1m `close` at minute T+m-1 (last fully closed minute; no
   cross-bar ffill, within-bar NaN stays NaN = not flushing). Own coin never
   counted (0..4). Flush at exactly 2.5 sigma counts (<=). v399-exact.
4. Arms per candidate rung (bar T, coin a, depth k), B1 static-bid replica:
   resting limit BUY at the arm's lv, live offsets 16..238. Fill at FIRST
   offset f with low(T+f) < lv (STRICT trade-through). Fill price = lv.
   n_fill = the arm's own n at f. size_mult = 1/(1+n_fill) (B1, both arms).
5. Post-fill exits (long), oc_b1deeper D0 replica measured from the ACTUAL
   fill price px (= the arm's lv) with the arm's OWN sigma
   (sg360 for BASE, sg_eff for ADAPT): sl = px*(1-4*sg), bl = px*(1-8*sg),
   tp = px*(1+1.0*sg). Evaluated on minutes t in f+1..239 then timeout at
   240 (next-bar open o2 = 1m open at T+240): backstop touch (first t with
   low(t) <= bl) exits at min(bl,open(t)) taker; else TP touch (first t with
   high(t) > tp, STRICT) exits at tp maker; else close5 stop (clock minutes
   m with (m+1)%5==0, first m with close(m) <= sl) exits at open(m+1)
   (or o2 if m=239) taker; else timeout at o2 taker + funding 0.0001 if
   (T+4h).hour in (0,8,16). Priority stop-first: backstop wins ties
   (kb<=ks and kb<=kt); else TP wins only if strictly earlier (kt<ks); else
   stop; else timeout. A stop and TP in the same minute -> stop wins. Fees:
   fill maker 0.0002; TP leg maker 0.0002 (total 2*maker on TP);
   stop/backstop/time legs taker 0.00055. Net returns are fractions of px.
   Fills whose exit price is missing (NaN open, NaN o2 on a stop-at-239 /
   timeout path) give NaN net and are DROPPED per arm.
6. Weights: w = size_mult per kept fill. PRIMARY comparison renormalises per
   anchor year per arm: w' = w / mean(w over that arm's fills in that year)
   (mean 1; single-fill year -> w' = 1). Only ALLOCATION/price quality is
   tested, not mean exposure. Raw (non-renormalised) sums reported
   descriptively. Efficiency is scale-invariant so identical on raw vs
   renormalised sums.
7. Daily sums per arm per year: group w'*y by EXIT date (calendar UTC date of
   T+x, x = exit offset, 240 = next-bar open date). Yearly sum S = sum of
   daily sums. Worst day W = min daily sum. Cumulative path over exit dates
   sorted ascending from 0: C_k = cumsum; maxDD = max(0, max_{p<q}(C_p-C_q))
   in w'*y units (0 when monotone non-decreasing). Efficiency E = S / maxDD;
   edge: DD == 0 -> E = +inf if S > 0, 0.0 if S <= 0; NaN S/DD -> NaN E.
   Win rate = fraction of kept fills with y > 0 strictly. Mean = mean(y).
8. Adaptive share: over coin-bar observations (sym, T) where the bar is
   BASE-tradable (finite O, finite sg360 > 0) AND sg42 finite, share =
   fraction with sg42 > sg360 (strictly). Reported per anchor year + full
   5y. Also report median(sg_eff/sg360) per year (descriptive).
9. Named-bar checks (descriptive, 4h grid from START): bars with open T on
   2024-01-03 (T = 00/04/08/12/16/20 UTC), 2023-08-17/18, 2024-03-05/06.
   Report per coin-bar sg360/sg42/sg_eff, fills per arm, and day sums.

## Decision rule (fixed, from the assignment)

Per anchor year Y0..Y4, renormalised weights: DD_base(Y), DD_adapt(Y),
E_base(Y), E_adapt(Y). PASS_dd(Y) iff DD_adapt(Y) <= DD_base(Y) (not worse;
equal passes; NaN -> FAIL). PASS_eff(Y) iff E_adapt(Y) >= E_base(Y)
(better-or-equal; equal passes; NaN (incl. -inf/NaN) -> FAIL; +inf >= +inf
passes as equal). PROMISING iff (a) PASS_dd in >= 4 of 5 years AND
(b) PASS_eff in >= 4 of 5 years. Otherwise NOT PROMISING. One-line verdict
in REPORT.md. Descriptive only: fills, win rate, raw sums, worst days,
full-path sums/DD, adaptive share, named bars.

## Protocol (fixed)

- PLAN.md written before any outcome computation. Then scripts: `adapt.py`
  (pure-numpy core: n vector, static-level fill, D0-from-fill exit, sigma
  helper), `run.py` (per-coin loop, per-arm fill ledger + exit-day sums ->
  results.json). Outputs: results.json, REPORT.md (tables + one-line
  verdict). Tests: `tests/test_oc_adaptsig.py` (synthetic hand checks +
  causality: fill uses only m-1 closes; sigma excludes the bar; eff = max).
- No commits; no edits outside research/tournament/oc_adaptsig/
  (+ tests/test_oc_adaptsig.py).
