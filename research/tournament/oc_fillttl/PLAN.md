# oc_fillttl PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

Idea #68 (motivated by research/tournament/oc_phasedisp): single-clock
results swing because the dip time exit is tied to the 4h clock. A rung
filled at bar minute f is closed at the next 4h open (offset 240), so a
late fill gets only 240-f minutes to rebound. Hypothesis: a FILL-RELATIVE
time exit (fixed holding time from the fill) restores rebound time to late
fills, raises the size-weighted rung sum at no worse tail, and lowers the
dispersion across clock phases.

## Replica (deployed baseline D0, exact copy of oc_dipexit PLAN.md D0)

- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- 1m klines: data/raw/btc_intraday_20260924 (BTC),
  data/raw/majors_intraday_20260924 (others). Minutes used: t <= 2026-09-24
  00:00 UTC. Missing minutes (NaN) never fill and never trigger an exit
  touch; a fill whose timeout open is NaN is dropped.
- Standard 4h grid per phase p in {0,1,2,3}: holding bar j covers
  [START_p + 4h*j, START_p + 4h*j + 4h) with START_p = 2020-08-01 00:00 UTC
  + p hours. Bar j has 240 minute offsets 0..239; next-bar open is offset
  240. Only bars with open in [2021-09-24 00:00, 2026-09-24 00:00) UTC are
  traded (5 years Y0..Y4 keyed by bar open: [anchor_i, anchor_{i+1}) with
  anchors 2021-09-24..2025-09-24 plus YEAR_END 2026-09-24; Y2
  (2023-09-24..2024-09-24) is 366d, others 365d — same year keying as
  oc_dipexit). Phase 0 == oc_dipexit grid exactly.
- sigma_4h at bar j on phase p (known at the bar open): simple returns
  r_b = O_b / O_{b-1} - 1 of that phase's 4h bar opens; sigma(j) =
  std(r over 360 bars ending at j-1, min_periods 120, ddof=1) =
  v293/oc_dipexit Asset (pct_change().rolling(360).std().shift(1)). Bars
  with non-finite O_j or sigma<=0/NaN are skipped.
- Rungs k in {2.5, 3.0, 3.5, 4.0, 5.0} (R2 depths). Level
  lv = O_j * (1 - k*sigma(j)). Resting limit BUY at lv, live window offsets
  16..238 inclusive. Fill at the FIRST offset f with low(f) < lv (STRICT
  trade-through). Fill price = lv, fee maker 0.0002. At most one fill per
  (phase, bar, coin, k). Fill uses only minutes <= f of the same bar.
- B1 sizing (oc_b1deeper sizing, static-bid arm): correlation count at live
  minute m, n(a,T,m) = number of OTHER majors b != a with finite O_b(T),
  finite C_b(T+m-1), finite sg_b(T) > 0 AND
  C_b(T+m-1) <= O_b(T)*(1-2.5*sg_b(T)) (1m close at T+m-1, last fully
  closed minute; within-bar NaN stays NaN = not flushing; own coin never
  counted, 0..4; flush at exactly 2.5 sigma counts). n_fill = n at the fill
  minute f. Weight w = 1/(1+n_fill) (same for D0/T240/T120 on the same
  fill; fills are identical across variants, only exits differ). No
  renormalisation (PRIMARY = raw w*y sums; renormalisation would scale all
  three variants identically on paired fills).
- Post-fill exits D0 (long), evaluated on minutes t in f+1..239 then
  timeout at 240: sl = lv*(1-4*sigma), bl = lv*(1-8*sigma),
  tp = lv*(1+1.0*sigma).
  - BACKSTOP: first t with low(t) <= bl -> exit at min(bl, open(t))/lv-1-
    maker-taker (gap pays the open; min() worse for a long), taker 0.00055.
  - TP: first t with high(t) > tp (STRICT) -> exit at tp/lv-1-2*maker.
  - CLOSE5 stop: clock minutes m with (m+1)%5==0 on the bar offset clock
    (4,9,...,239; equals global (base+m+1)%5==0 since base%5==0 for all
    phases as shifts 0/60/120/180 are multiples of 5); first m with
    close(m) <= sl -> exit at open(m+1) (or next-bar open o2 if m=239),
    net = px/lv-1-maker-taker.
  - TIMEOUT: else exit at next-bar open o2, net = o2/lv-1-maker-taker-fund,
    fund = 0.0001 if (bar_open+4h).hour in (0,8,16) else 0 (v293 settle;
    longs pay; no funding on intrabar exits).
  - Priority stop-first (v293): backstop wins ties (kb<=ks and kb<=kt);
    else TP wins only if strictly earlier (kt<ks); else stop; else timeout.
    Stop and TP in the same minute -> stop wins.
- D0 (deployed): as above.

## Fill-relative variants (fixed, exactly two; TP/stop/backstop unchanged)

- T240: time exit at fill minute + 240. x_time = f+240 (offsets relative to
  the bar open; max 478). Signals evaluated on t in f+1..x_time-1 on the
  continuous 1m tape (may extend into the next bar and the bar after; NaN
  minutes never trigger). Levels sl/bl/tp identical to D0 (from lv, mu=1).
  Close5 clock extended with the same rule (t+1)%5==0 on bar-relative
  offsets (== global 5-min clock since base%5==0). Priority identical
  (backstop > TP-strictly-earlier > stop > time). Time exit: px =
  open(x_time) (1m open at bar_open + x_time minutes), net =
  px/lv-1-maker-taker-fund_ext, taker 0.00055.
- T120: at least 120 minutes. x_time = max(240, f+120) (for f<=120 this is
  240, i.e. identical to D0 by construction; for f>120 it is f+120, max
  358). Same race/fees/clock/priority as T240 with this x_time.
- Funding (longs pay): fund_ext = 0.0001 * (# of 00:00/08:00/16:00 UTC
  settlement timestamps ts with t_fill < ts <= t_exit) when the exit is
  via TIME; 0 for TP/stop/backstop exits (D0 convention extended: D0
  timeout funding equals this count, which is 1 iff the next-bar open is a
  settlement hour and 0 otherwise, since any 4h window holds at most one
  8h settlement; T240 holds exactly 240 min so at most one settlement;
  T120 holds 120..224 min so at far most one).
- Missing data: NaN lows/highs/closes never trigger; a stop exit at a NaN
  open gives NaN net; a time exit at a NaN/missing open (including
  x_time beyond the 2026-09-24 00:00 tape) gives NaN net. PAIRED rungs:
  kept only if D0, T240 and T120 nets are ALL finite (same pairing rule as
  oc_dipexit across E-legs). Weights w are identical across the three
  variants on a kept rung.

## Metrics (fixed; per phase, per year, size-weighted)

- Per (phase p, year Y, variant V): over kept paired fills: trades n =
  rung count; win = fraction with y>0 strictly (equal-weight); sum S =
  sum(w*y) (B1 size-weighted, raw, in return-fraction units); daily sums
  group w*y by EXIT date (calendar UTC date of T+x, x = exit offset,
  240 = next-bar open date; T240 exits may date to the next day);
  worst day W = min daily sum; cumulative path over exit dates sorted
  ascending from 0: maxDD = max_{p<q}(C_p - C_q) (>=0, in w*y units).
- 4-phase mean per (year, variant): S_bar = mean_p S_p; n_bar, win_bar,
  W_bar, DD_bar = means across p=0..3 of the per-phase metric.
- Phase dispersion per (year, variant): D = max_p S_p - min_p S_p (>=0,
  max-min of the four yearly size-weighted sums).
- Gross-exposure note (same coin, next bar): next-bar live window offsets
  [256,478] relative to the current bar (= 240+16 .. 240+238). For each
  kept fill with exit offset x and fill f, held = x - f minutes covering
  [f+1, x); overlap = max(0, min(x,479) - max(f+1,256)). Share =
  sum(overlap)/sum(held) per (year, variant) pooled over phases (plus
  share of fills with any overlap as context). D0 can overlap only via a
  stop-at-239/timeout at 240? No: D0 x<=240 <256, so D0 overlap is 0 by
  construction (reported as 0.000). T120 overlaps only when f>136
  (x=f+120>256); T240 always overlaps unless stopped/TPed before 256.

## Decision rule (fixed, from the assignment; overrides the default)

Per year Y0..Y4 on 4-phase means: PASS_sum(Y) iff S_bar_T(Y) >=
S_bar_D0(Y) (not lower; equal passes); PASS_dd(Y) iff DD_bar_T(Y) <=
DD_bar_D0(Y) + 0.01 (not worse by more than 1pp = 0.01 in w*y units);
PASS_disp(Y) iff D_T(Y) < D_D0(Y) (strictly lower dispersion). Variant T
is PROMISING iff (a) PASS_sum in >= 4/5 years AND (b) PASS_dd in >= 4/5
years AND (c) PASS_disp in >= 3/5 years. Otherwise NOT PROMISING.
One-line verdict in REPORT.md.

## Protocol / resources (fixed)

- PLAN.md written before any outcome computation. One process; majors 1m
  OHLC held as float32 (all-five-coins O/C plus current-coin H/L loop;
  RAM < 3 GB). No commits; no edits outside research/tournament/oc_fillttl/
  (+ tests/test_oc_fillttl.py).
- Market data up to 2026-09-24 00:00 UTC is read per the assignment (all 5
  years are research data; any PROMISING result needs prospective
  validation before real money). Disclosed against RULES.md 2 / VF_COMMON
  hidden-year conventions.
- Scripts: fillttl.py (pure-numpy core: n vector, B1 size, D0/T240/T120
  exact outcomes + funding count + overlap), run.py (phase x coin loop,
  paired ledger + exit-day sums -> results.json). Outputs: results.json,
  REPORT.md (tables + one-line verdict).
