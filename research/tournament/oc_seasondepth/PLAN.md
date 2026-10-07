# oc_seasondepth PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

Idea #70: intraday-seasonal rung depth.

## Hypothesis (fixed here)

Rung levels are lv = O_j (1 - k sigma_4h(j)) with sigma from 4h bar opens, but
intraday volatility has a strong hour-of-week profile (US hours, Asia open,
weekends), so the same k is deep in quiet hours and shallow in loud ones.
Hypothesis: scaling the bar sigma by a walk-forward intraday-seasonality factor
s(h) (loud slot -> effectively deeper bid, quiet slot -> effectively shallower
bid, with TP/stops in the same effective units) improves the size-weighted rung
sum at no worse tail. Pre-registered direction: the seasonal rule beats the
base on 4-phase-mean yearly sums with maxDD not worse by more than 1 pp. Fixed
rule, no fitted parameters (exponent 1/2 shrinkage fixed below).

## Replica (deployed baseline D0 + B1 sizes, exact copies of frozen definitions)

- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- 1m klines: `data/raw/btc_intraday_20260924` (BTC),
  `data/raw/majors_intraday_20260924` (others). Minutes used: t < 2026-09-24
  00:00 UTC (assignment: all five years are research data; any PROMISING result
  needs prospective validation before real money; disclosed against RULES.md 2 /
  VF_COMMON hidden-year conventions).
  Missing minutes (NaN) never fill, never trigger an exit touch, never enter
  the n detector, and never enter the seasonal-factor means.
- 4 clock phases s in {0,1,2,3}h (dip results swing with the 4h phase, cf.
  oc_fillttl/oc_rearm): phase-s bar j covers
  [START_s + 4h*j, START_s + 4h*j + 4h) with
  START_s = 2020-08-01 00:00 UTC + s hours. Bar j has 240 minute offsets
  0..239; next-bar open is offset 240. Only bars with open T in
  [2021-09-24 00:00, 2026-09-24 00:00) UTC are traded (5 anchor years Y0..Y4
  keyed by bar open: [anchor_i, anchor_{i+1}) with anchors 2021-09-24..
  2025-09-24 plus YEAR_END 2026-09-24; Y2 (2023-09-24..2024-09-24) is 366d,
  others 365d -- same year keying as oc_dipexit/oc_fillttl).
  Phase 0 == oc_dipexit grid exactly.
- sigma_4h at bar j on phase s (known at the bar open): simple returns
  r_b = O_b / O_{b-1} - 1 of that phase's 4h bar opens; sigma(j) =
  std(r over 360 bars ending at j-1, min_periods 120, ddof=1) =
  v293/oc_dipexit Asset (pct_change().rolling(360).std().shift(1)). Bars with
  non-finite O_j or sigma <= 0/NaN are skipped (no rungs that bar).
- Rungs k in {2.5, 3.0, 3.5, 4.0, 5.0} (R2 depths).
- B1 sizing (oc_b1deeper static-bid arm, exact replica): correlation count at
  live minute m (offsets 16..238), n(a,T,m) = number of OTHER majors b != a
  with finite O_b(T), finite C_b(T+m-1), finite sg_b(T) > 0 AND
  C_b(T+m-1) <= O_b(T)*(1-2.5*sg_b(T)) (1m close at T+m-1, last fully closed
  minute; within-bar NaN stays NaN = not flushing; own coin never counted,
  0..4; flush at exactly 2.5 sigma counts). n_fill = n at the arm's OWN fill
  minute f. Weight w = 1/(1+n_fill). The n detector always uses BASE sigma_4h
  (not sigma_eff), identically for both arms.
- Post-fill exits (long), oc_dipexit D0 replica measured from the arm's ACTUAL
  fill price px with the arm's OWN sigma (sg for BASE, sg_eff for RULE):
  sl = px*(1-4*sg_arm), bl = px*(1-8*sg_arm), tp = px*(1+1.0*sg_arm).
  Evaluated on minutes t in f+1..239 then timeout at 240 (next-bar open o2 =
  1m open at T+240): backstop touch (first t with low(t) <= bl) exits at
  min(bl,open(t)) taker; else TP touch (first t with high(t) > tp, STRICT)
  exits at tp maker; else close5 stop (clock minutes m with (m+1)%5==0 on the
  bar offset clock, first m with close(m) <= sl) exits at open(m+1) (or o2 if
  m=239) taker; else timeout at o2 taker + funding 0.0001 if (T+4h).hour in
  (0,8,16). Priority stop-first: backstop wins ties (kb<=ks and kb<=kt); else
  TP wins only if strictly earlier (kt<ks); else stop; else timeout. A stop and
  TP in the same minute -> stop wins. Fees: fill maker 0.0002; TP leg maker
  0.0002 (total 2*maker on TP); stop/backstop/time legs taker 0.00055. Net
  returns are fractions of px. Fills whose exit price is missing (NaN open,
  NaN o2 on a stop-at-239/timeout path) give NaN net and are DROPPED per arm.
- BASE arm (D0+B1): lv = O_j*(1-k*sg). Resting limit BUY at lv, live offsets
  16..238. Fill at FIRST offset f with low(T+f) < lv (STRICT trade-through).
  Fill price px = lv. Exit with sg_arm = sg.
- RULE arm (seasonal): sg_eff = sg*sqrt(s) with s = s_c(A,q_bar) from the
  factor table below (s<=0/NaN/non-finite -> s = 1, i.e. identical to BASE for
  that bar). lv' = O_j*(1-k*sg_eff). Fill at FIRST offset f' with
  low(T+f') < lv' (STRICT). Fill price px' = lv'. Exit with sg_arm = sg_eff
  (sl/bl/tp in sigma_eff units). w' = 1/(1+n(f')) with the unchanged n
  detector evaluated at the rule arm's own fill minute.

## Seasonal factor s(h) (frozen, walk-forward, leakage-free)

- Weekly 4h slot of any minute m (UTC): q(m) = (((dow(m)*24 + hour(m))*60 +
  minute(m)) // 240) % 42, with dow Monday=0. 42 slots per week.
- 1m log return: r_m = ln(C_m / C_{m-1}) (1m closes, both must be finite;
  else the minute contributes nothing).
- Per coin c and anchor A in {2021-..-2025-09-24}: trailing window
  W_A = [A - 365 days, A) (strictly before the anchor; no test-year data).
  Slot mean M_c(A,q) = mean(|r_m| over m in W_A with q(m) = q);
  overall mean M_c(A) = mean(|r_m| over all m in W_A).
  Factor s_c(A,q) = M_c(A,q) / M_c(A); fallback s = 1.0 when either mean is
  non-finite/non-positive or the slot has no finite minutes.
- Table recomputed once per anchor year (5 anchors x 5 coins x 42 slots =
  1050 factors). For a bar with open T in year of anchor A (year keying above),
  q_bar = q(T) and s = s_c(A, q_bar). The factor is known at the bar open
  (uses only data < A <= T). No clipping beyond the s=1 fallback (the 1/2
  exponent is the shrinkage); the factor range per anchor is reported.
- BOT book context: forward_v205.research_books_d2 (see
  research/diagnostics/r2_decompose5/r2_decompose5.py) is the deployed BOT
  book; this study varies only the dip-rung depth ceteris paribus (D0 exits,
  B1 sizes, R2 depths), so no book engine is run.

## Metrics (fixed; per phase, per year, size-weighted, raw exposure primary)

- Per (phase p, year Y, arm V) over that arm's OWN kept fills (unpaired arms;
  a rung kept iff that arm filled and its net is finite): trades n = fill
  count; win = fraction with y > 0 strictly (equal-weight); sum S =
  sum(w*y) (B1 size-weighted, raw, in return-fraction units); daily sums group
  w*y by EXIT date (calendar UTC date of T+x, x = exit offset, 240 = next-bar
  open date); worst day W = min daily sum; cumulative path over exit dates
  sorted ascending from 0: maxDD = max(0, max_{p<q}(C_p - C_q)) in w*y units
  (0 when monotone non-decreasing).
- 4-phase mean per (year, arm): S_bar = mean_p S_p; n_bar, win_bar, W_bar,
  DD_bar = means across p = 0..3 of the per-phase metric.
- Factor range per anchor A: per coin min/max of s_c(A,q) over q = 0..41
  (plus global min/max and the sqrt(s) effective-sigma multiplier range).
- Side row only: renormalised sums per (phase, year, arm) with w' =
  w / mean(w) (exposure-neutral, oc_b1deeper convention), to check the verdict
  does not hinge on exposure.

## Decision rule (fixed, from the assignment; overrides the generic default)

Per year Y0..Y4 on 4-phase means: PASS_sum(Y) iff S_bar_RULE(Y) >=
S_bar_BASE(Y) (not lower; equal passes); PASS_dd(Y) iff DD_bar_RULE(Y) <=
DD_bar_BASE(Y) + 0.01 (not worse by more than 1 pp = 0.01 in w*y units).
The RULE is PROMISING iff (a) PASS_sum in >= 4 of 5 years AND (b) PASS_dd in
>= 4 of 5 years. Otherwise NOT PROMISING. One-line verdict in REPORT.md. The
generic tournament default rule (same sign 4/5 + leave-one-year-out 4/5) is
superseded by this assignment-specific rule.

## Protocol / resources (fixed)

- PLAN.md written before any outcome computation. One process; majors 1m O/C
  held as float32 (all five coins) plus one coin's H/L at a time; RAM < 3 GB.
  No commits; no edits outside research/tournament/oc_seasondepth/
  (+ tests/test_oc_seasondepth.py).
- Scripts: seasondepth.py (pure-numpy core: seasonal-factor table, n vector,
  static fill, D0-from-fill exit with arm sigma, scoring helpers), run.py
  (phase x coin loop, per-arm ledgers + exit-day sums + factor ranges ->
  results.json). Outputs: results.json, REPORT.md (tables + one-line
  verdict).
