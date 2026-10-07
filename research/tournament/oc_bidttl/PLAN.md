# oc_bidttl PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

Idea #77 = docs/opencode/IDEAS3_20261006.md idea 8: two-hour dip-bid expiry
(execution + capital). Single fixed variant (no fitting).

## Hypothesis (fixed here)

Dip rungs rest to the next 4h open; stale unfilled-after-2h bids sit through
regime change and pin gross-cap headroom. Cancelling an unfilled bid 120 min
after its live window opens (no replacement same bar) cuts stale late fills
at no worse tail, and any freed G-cap headroom is reusable by other coins'
rungs. Pre-registered direction: TTL (cap-adjusted) beats base (cap-adjusted)
on yearly 4-phase-mean sums at no worse maxDD by more than 1pp, with a 5y
effect above the placebo p95. Fixed rule, one parameter (120 min).

## Replica (deployed baseline, exact copy of oc_dipexit PLAN.md D0 + B1 sizes)

- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- 1m klines: data/raw/btc_intraday_20260924 (BTC),
  data/raw/majors_intraday_20260924 (others). Minutes used: t < 2026-09-24
  00:00 UTC. Missing minutes (NaN) never fill and never trigger an exit
  touch; a fill whose exit price is NaN gives NaN net and is DROPPED
  (base and TTL identically; single-leg pairing since TP is fixed 1.0).
- Four clock phases p in {0,1,2,3}: holding bar j covers
  [START_p + 4h*j, START_p + 4h*j + 4h) with START_p = 2020-08-01 00:00 UTC
  + p hours. Bar j has 240 minute offsets 0..239; next-bar open is offset
  240. Only bars with open in [2021-09-24 00:00, 2026-09-24 00:00) UTC are
  traded (5 years Y0..Y4 keyed by bar open: [anchor_i, anchor_{i+1}) with
  anchors 2021-09-24..2025-09-24 plus YEAR_END 2026-09-24; Y2 is 366d,
  others 365d). Phase 0 == oc_dipexit grid exactly.
- sigma_4h at bar j on phase p (known at the bar open): simple returns
  r_b = O_b / O_{b-1} - 1 of that phase's 4h bar opens; sigma(j) =
  std(r over 360 bars ending at j-1, min_periods 120, ddof=1) =
  v293/oc_dipexit Asset (pct_change().rolling(360).std().shift(1)). Bars
  with non-finite O_j or sigma<=0/NaN are skipped (no rungs that bar).
- Rungs k in {2.5, 3.0, 3.5, 4.0, 5.0} (R2 depths). Level
  lv = O_j * (1 - k*sigma(j)). Resting limit BUY at lv. Fill at the FIRST
  offset f with low(f) < lv (STRICT trade-through). Fill price = lv, fee
  maker 0.0002. At most one fill per (phase, bar, coin, k).
- B1 sizing (oc_b1deeper sizing exact): correlation count at live minute m,
  n(a,T,m) = number of OTHER majors b != a with finite O_b(T), finite
  C_b(T+m-1), finite sg_b(T) > 0 AND C_b(T+m-1) <= O_b(T)*(1-2.5*sg_b(T))
  (1m close at T+m-1, last fully closed minute; within-bar NaN stays NaN =
  not flushing; own coin never counted, 0..4; flush at exactly 2.5 sigma
  counts). n_fill = n at the fill minute f. Weight w = 1/(1+n_fill).
- Post-fill exits D0 (long, filled rungs unchanged by TTL), evaluated on
  minutes t in f+1..239 then timeout at 240: sl = lv*(1-4*sigma),
  bl = lv*(1-8*sigma), tp = lv*(1+1.0*sigma).
  - BACKSTOP: first t with low(t) <= bl -> exit at min(bl, open(t))/lv-1-
    maker-taker (gap pays the open; min() worse for a long), taker 0.00055.
  - TP: first t with high(t) > tp (STRICT) -> exit at tp/lv-1-2*maker.
  - CLOSE5 stop: clock minutes m with (m+1)%5==0 on the bar offset clock
    (4,9,...,239; equals the global 5-min clock since every phase shift
    0/60/120/180 is a multiple of 5); first m with close(m) <= sl -> exit
    at open(m+1) (or next-bar open o2 if m=239), net = px/lv-1-maker-taker.
  - TIMEOUT: else exit at next-bar open o2, net = o2/lv-1-maker-taker-fund,
    fund = 0.0001 if (bar_open+4h).hour in (0,8,16) else 0 (v293 settle;
    longs pay; no funding on intrabar exits).
  - Priority stop-first (v293): backstop wins ties (kb<=ks and kb<=kt);
    else TP wins only if strictly earlier (kt<ks); else stop; else timeout.
    Stop and TP in the same minute -> stop wins.

## TTL variant (fixed, one rule)

- BASE live window: offsets 16..238 inclusive (oc_dipexit exact).
- TTL live window: offsets 16..135 inclusive (120 minutes: 16..135; a bid
  still unfilled at the start of minute 136 = 120 min after the window
  opens at the start of minute 16 is cancelled, no replacement in the same
  bar). Fills with f >= 136 are "late fills" (lost under TTL). Filled
  rungs (f <= 135) keep the exact D0 exit above from the same lv.
- Bot-executable: cancel one resting bid per (phase, bar, coin, k) at a
  fixed clock time using only the placement timestamp; depths from
  trailing sigma360 <= bar close; minute-5 rule not applicable (live from
  16 > 5, kept).

## G = 2.0 gross cap (fixed, v421-style, both arms)

- Engine hook sleeve_gross_cap G = 2.0 replica (oc_rearm gross_cap_weights
  exact): per (phase, bar) candidate pool, order by (fill offset f ASC,
  rung k ASC, coin ASC); walk: open_w(f) = sum of kept weights with exit
  x > f (an exit at minute <= f is observably closed by f); room =
  2.0 - open_w(f); skipped when room <= 1e-12 (kept 0.0); else kept
  wk = min(w, room), appended as open until its x. Skipped fills never
  open. Equity = 1.0 constant per phase sub-account (w units); no
  cross-bar overlap exists (D0 exits x <= 240 = next-bar open), so pools
  are per-bar independent; phases never share cap.
- Wording disclosure: the assignment's "open dip notional + resting bids"
  is implemented as v421 does: sum(filled-open notional) + the new bid <=
  G at each fill (cut to room, skip when full). All 25 resting bids are
  NOT continuously charged against G (that would block everything from
  minute 16 and is not v421; v421 charges only taken/open rungs). The
  "freed headroom usable by other coins" mechanism is the walk order:
  a cancelled late fill never opens, so room it would have consumed stays
  available to later-processed fills (in practice TTL candidates are a
  subset of base, so extra fills are expected to be 0; reported exactly).
- PRIMARY scoring is cap-adjusted (wk*y). Uncapped w*y sums are a
  descriptive side row only.

## Metrics (fixed; per phase, per year, cap-adjusted)

- Per (phase p, year Y, arm A in {BASE, TTL}): over cap-kept fills
  (wk > 0, finite y): n = kept count; win = fraction with y > 0 strictly
  (equal-weight); sum S = sum(wk*y); daily sums group wk*y by EXIT date
  (calendar UTC date of T+x, x = exit offset, 240 = next-bar open date);
  worst day W = min daily sum; cumulative path over exit dates sorted
  ascending from 0: maxDD = max_{p<q}(C_p - C_q) (>= 0, in wk*y units).
- 4-phase mean per (year, arm): S_bar = mean_p S_p; DD_bar, W_bar, n_bar =
  means across p=0..3.
- Decomposition per year (cap-adjusted): LOST = base-kept fills with
  f >= 136 (count, win rate, sum wk*y; these are the late fills TTL
  cancels); EXTRA = TTL-kept fills absent from the base-kept set by
  (phase, bar, coin, k) key (count, sum wk*y; expected 0); sum delta =
  S_bar_TTL - S_bar_base; 5y sum delta dSum5y = sum_Y delta.
- Full-path reference: pooled all-phase exit-date path per arm (sum over
  all fills, one path) with its maxDD, for context only.

## Decision rule (fixed, from the assignment)

Per year Y0..Y4 on 4-phase means: PASS_sum(Y) iff S_bar_TTL(Y) >=
S_bar_BASE(Y) (not lower; equal passes); PASS_dd(Y) iff DD_bar_TTL(Y) <=
DD_bar_BASE(Y) + 0.01 (not worse by more than 1pp = 0.01 in wk*y units).
PROMISING iff (a) PASS_sum in >= 4/5 years AND (b) PASS_dd in >= 4/5
years AND (c) 5y sum delta dSum5y >= +0.273 (pooled placebo p95,
oc_placebo_dip). Otherwise NOT PROMISING. One-line verdict in REPORT.md.

## Protocol / resources (fixed)

- PLAN.md written before any outcome computation. Then scripts:
  bidttl.py (vendored pure-numpy core: n vector, static fill, D0 exit,
  G-cap walk; bit-identical constants to oc_b1deeper/oc_rearm),
  run.py (phase x coin loop, paired ledger + cap walk + exit-day sums ->
  results.json). Outputs: results.json, REPORT.md (tables + one-line
  verdict). Tests: tests/test_oc_bidttl.py (synthetic hand checks:
  TTL window 16..135 vs base 16..238 boundary, strict trade-through,
  close5 clock, stop-first priority, B1 size, cap walk cut/skip/order,
  scoring helpers).
- Market data up to 2026-09-24 00:00 UTC is read per the assignment (all
  five years are research data; any PROMISING result needs prospective
  validation before real money). Disclosed against RULES.md 2 / VF_COMMON
  hidden-year conventions.
- One process, one coin's H/L in RAM at a time; all-five-coins 1m O/C as
  float32; RAM < 3 GB. Runs > 0.4 GB wrapped with
  scripts/heavy_slot.py run --tag oc_bidttl.
- No commits; no edits outside research/tournament/oc_bidttl/
  (+ tests/test_oc_bidttl.py).
