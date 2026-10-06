# oc_depthtilt PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

Idea #78 (NEW): DEPTH-TILTED dip-rung sizing with the same nominal ladder.

POST-HOC ORIGIN (labelled): motivated by research/diagnostics/oc_saturation —
edge per unit notional ~0.19% at 2.5 sigma vs 0.51-0.58% at 5 sigma (deep
rungs earn more per unit filled notional). This study tests whether shifting
nominal size toward deep rungs raises the dip sleeve's total P&L at no worse
tail. It is a post-hoc-motivated, pre-registered fixed rule (no fitted
parameters).

## Hypothesis (fixed here)

Deep dip rungs have higher P&L per unit filled notional than shallow rungs,
so weighting the resting ladder toward deep rungs (same total nominal bid
notional per coin-bar) raises total P&L beyond what a constant exposure
uplift would give, at no worse drawdown. Direction pre-registered: the
depth-tilted rule beats the B1 base on yearly 4-phase-mean sums, beats its
exposure-matched control, at no worse maxDD by more than 1pp, with a 5y
effect above the placebo p95. Fixed weights, no fitting.

## Replica (deployed baseline: D0 exits + B1 sizes, 4 clock phases)

Exact replica of research/tournament/oc_dipexit/PLAN.md D0 with
oc_b1deeper B1 sizes, on all four clock phases (oc_bidttl/oc_placebo_dip
convention):

- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- 1m klines: data/raw/btc_intraday_20260924 (BTC),
  data/raw/majors_intraday_20260924 (others). Minutes used:
  t < 2026-09-24 00:00 UTC. Missing minutes (NaN) never fill, never trigger
  an exit touch, and never count as flushing; a fill whose exit price is
  NaN is dropped (base/rule/control share identical membership).
- Four clock phases p in {0,1,2,3}: holding bar j covers
  [START_p + 4h*j, START_p + 4h*j + 4h) with START_p = 2020-08-01 00:00 UTC
  + p hours. Bar j has 240 minute offsets 0..239; next-bar open is offset
  240. Only bars with open T in [2021-09-24 00:00, 2026-09-24 00:00) UTC
  are traded (5 years Y0..Y4 keyed by bar open: [anchor_i, anchor_{i+1})
  with anchors 2021-09-24..2025-09-24 plus YEAR_END 2026-09-24).
  Phase 0 == the oc_dipexit grid exactly.
- sigma_4h per coin at bar j on phase p (known at the bar open): simple
  returns r_b = O_b / O_{b-1} - 1 of that phase's 4h bar opens;
  sigma(j) = std(r over 360 bars ending at j-1, min_periods 120, ddof=1)
  (= v293/oc_dipexit Asset; shift(1) so the bar itself is excluded). Bars
  with non-finite O_j or sigma<=0/NaN are skipped (no rungs that bar).
- Rungs k in {2.5, 3.0, 3.5, 4.0, 5.0} (R2 depths). Level
  lv = O_j * (1 - k*sigma(j)). Resting limit BUY at lv, live window
  offsets 16..238 inclusive. Fill at the FIRST offset f with
  low(f) < lv (STRICT trade-through). Fill price = lv, maker 0.0002.
  At most one fill per (phase, bar, coin, k).
- B1 size (oc_b1deeper-exact, causal: uses only closes up to minute m-1):
  n(a,T,m) = number of OTHER majors b != a with finite O_b(T),
  finite C_b(T+m-1), finite sg_b(T) > 0 AND
  C_b(T+m-1) <= O_b(T)*(1-2.5*sg_b(T)) (<= counts; NaN = not flushing;
  own coin never counted, 0..4). At the fill minute f, n_fill = n(a,T,f);
  w_base = 1/(1+n_fill). Everything else unchanged.
- Post-fill exits D0 (long), from fill price lv: sl = lv*(1-4*sg),
  bl = lv*(1-8*sg), tp = lv*(1+1.0*sg), on minutes t in f+1..239 then
  timeout at 240 (next-bar open o2):
  backstop touch (first t with low(t) <= bl) exits at min(bl,open(t))
  taker 0.00055; else TP touch (first t with high(t) > tp, STRICT) exits
  at tp maker (total 2*maker with the fill leg); else close5 stop (clock
  minutes m with (m+1)%5==0 on the bar offset clock 4,9,...,239, first m
  with close(m) <= sl) exits at open(m+1) (or o2 if m=239) taker; else
  timeout at o2 taker + funding 0.0001 if (T+4h).hour in (0,8,16)
  (v293 settle rule; no funding on intrabar exits). Priority stop-first:
  backstop wins ties (kb<=ks and kb<=kt); else TP wins only if strictly
  earlier (kt<ks); else stop; else timeout. Stop and TP in the same
  minute -> stop wins. Net returns are fractions of lv. Fills with
  non-finite exit nets are DROPPED for all arms (identical membership).

## Depth-tilt rule (fixed, one frozen weight vector)

- Raw rung weight w_raw(k) = k / 2.5: 2.5 -> 1.0, 3.0 -> 1.2,
  3.5 -> 1.4, 4.0 -> 1.6, 5.0 -> 2.0 (sum 7.2).
- Renormalised per coin and bar (ex-ante exposure neutral): tilt
  t(k) = w_raw(k) / 7.2 * 5, so the SUM of nominal bid notional over the
  5-rung ladder equals the base ladder's sum (5.0 nominal units):
  t(2.5) = 0.69444444, t(3.0) = 0.83333333, t(3.5) = 0.97222222,
  t(4.0) = 1.11111111, t(5.0) = 1.38888889 (sum 5.0 exactly up to fp).
- Per kept fill (same lv, same f, same y, same n_fill as base — levels and
  fills are IDENTICAL across arms; only sizing differs):
  w_rule = w_base * t(k) = t(k) / (1+n_fill).
- Realised exposure WILL differ (deep rungs fill less often) — reported
  as realised filled notional per year/arm, plus P&L per unit filled
  notional. Bot-executable: static per-rung size multipliers, no amendment.
- The BOT book leg is held fixed (forward_v205.research_books_d2); only
  dip-rung sizing varies.

## G = 2.0 gross cap (fixed, v421-style, both arms + uncapped side row)

- Engine hook sleeve_gross_cap G = 2.0 replica (oc_rearm/oc_bidttl-exact):
  per (phase, bar) candidate pool, order by (fill offset f ASC, rung k ASC,
  coin ASC); walk: open_w(f) = sum of kept weights with exit x > f
  (an exit at minute <= f is observably closed by f); room = 2.0 - open_w;
  skipped when room <= 1e-12 (kept 0.0); else kept wk = min(w, room),
  appended as open until its x. Skipped fills never open. Equity = 1.0
  constant per phase sub-account; D0 exits x <= 240 so pools are per-bar
  independent; phases never share cap.
- Base pool walks with w_base -> wk_base; rule pool walks with w_rule ->
  wk_rule (same order key; kept sets may differ because weights differ).
- PRIMARY scoring is cap-adjusted (wk*y). Uncapped w*y sums are reported
  as a side row with the same decision legs computed descriptively.

## Exposure-matched control (fixed here)

- Per year Y (pooled across phases, PRIMARY capped regime):
  R(Y) = realised_rule(Y) / realised_base(Y), where realised(Y) = sum of
  cap-kept weights over all phases in that year (if realised_base == 0,
  R = 1.0). Control sums: S_ctrl_bar(Y) = R(Y) * S_base_bar(Y) (base ladder
  scaled by the rule's realised/base filled-notional ratio that year).
  Gain(Y) = S_rule_bar(Y) - S_ctrl_bar(Y) isolates ALLOCATION (tilt shape)
  from the year's mean-exposure difference. Uncapped analogue (same
  formula on uncapped realised/sums) reported as a side row.
- The control is an in-year diagnostic (uses the in-year ratio), not a
  tradable rule.

## Scoring (fixed here)

- Per (phase p, year Y, arm A in {BASE, RULE}): over cap-kept fills
  (wk > 0, finite y): n = kept count; realised N = sum(wk);
  S = sum(wk*y); ppf = S/N (P&L per unit filled notional; N == 0 -> NaN);
  win = fraction with y > 0 strictly (equal-weight; identical fill
  membership across arms before the cap walk); daily sums group wk*y by
  EXIT date (calendar UTC date of T+x, x = exit offset, 240 = next-bar
  open date); W = min daily sum; cumulative path over exit dates sorted
  ascending from 0: maxDD >= 0 in wk*y units.
- 4-phase means per (year, arm): S_bar, N_bar, W_bar, DD_bar, n_bar,
  win_bar = means across p=0..3; ppf_bar = S_bar / N_bar (ratio of means;
  per-phase ppf kept in results.json for audit).
- 5y deltas: dSum5y = sum_Y (S_rule_bar - S_base_bar) (capped PRIMARY;
  uncapped side row likewise). Full pooled path (all phases, exit-date
  order) per arm: sum/DD/win as context only.
- Fidelity: phase-0 uncapped base raw sums vs oc_placebo_dip ref
  [2.388052, 0.182865, 3.809764, 2.579274, 0.711509]; n_candidates should
  match the oc_bidttl ledger scale (~22312 across 4 phases, same replica).

## Decision rule (fixed, from the assignment; replaces the default
same-sign/LOYO rule — LOYO N/A by construction: fixed tilt, no in-year
fit to leave out)

On PRIMARY capped 4-phase means, per year Y0..Y4:
PASS_sum(Y) iff S_rule_bar(Y) >= S_base_bar(Y) (not lower; equal passes);
PASS_dd(Y) iff DD_rule_bar(Y) <= DD_base_bar(Y) + 0.01 (not worse by more
than 1pp = 0.01 in wk*y units); PASS_ctrl(Y) iff
S_rule_bar(Y) > S_ctrl_bar(Y) (strict; beats the exposure-matched
control). NaN on either side counts as FAIL.
PROMISING iff (a) PASS_sum in >= 4/5 years AND (b) PASS_dd in >= 4/5
years AND (c) 5y sum delta dSum5y >= +0.273 (pooled placebo p95,
oc_placebo_dip) AND (d) PASS_ctrl in >= 4/5 years. Otherwise
NOT PROMISING. One-line verdict in REPORT.md. Uncapped legs reported
descriptively (same four checks, no promotion power).

## Protocol / resources (fixed)

- PLAN.md written before any outcome computation. Then scripts:
  depthtilt.py (vendored pure-numpy core: n vector, static fill, D0 exit,
  G-cap walk, tilt vector; bit-identical constants to
  oc_b1deeper/oc_bidttl), run.py (phase x coin loop, paired ledger +
  cap walks + exit-day sums -> results.json, fills.parquet). Outputs:
  results.json, REPORT.md (tables + one-line verdict). Tests:
  tests/test_oc_depthtilt.py (synthetic hand checks: tilt vector sums to
  5, strict trade-through, close5 clock, stop-first priority, B1 size,
  cap walk cut/skip/order with tilted weights, control-ratio math,
  scoring helpers; causality: n uses only m-1 closes, sigma excludes the
  bar).
- Market data up to 2026-09-24 00:00 UTC is read per the assignment (all
  five years are research data; any PROMISING result needs prospective
  validation before real money). Disclosed against RULES.md 2 / VF_COMMON
  hidden-year conventions.
- One process, one coin's H/L in RAM at a time; all-five-coins 1m O/C as
  float32; RAM < 3 GB. Run > 0.4 GB wrapped with
  scripts/heavy_slot.py run --tag oc_depthtilt.
- No commits; no edits outside research/tournament/oc_depthtilt/
  (+ tests/test_oc_depthtilt.py).

## Post-hoc log

- (none yet; filled only if definitions change after outcomes are seen)
