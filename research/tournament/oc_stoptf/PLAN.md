# oc_stoptf PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

Idea #72 (motivated by research/diagnostics/oc_clockanat: the worst dip
losses are stop cascades where all rungs of a coin fill minutes before the
flush continues and stop together). Stop TIMEFRAME variants for dip rungs
are tested as exact counterfactuals on every filled rung.

## Hypothesis (fixed here)

The deployed close5 stop (4 sigma below the fill, checked on 5-minute
closes) may stop cascades too early (whipsaw) or too late (full flush).
Two fixed structural timeframe alternatives — S15 (slower, close15) and
S1 (faster, every 1m close) — change only WHEN the same 4-sigma level is
checked, so any difference is pure stop-timing, not level. Direction is
NOT pre-registered (two-sided test); a variant is PROMISING only under
the fixed decision rule below.

## Replica (deployed baseline D0, exact copy of oc_dipexit PLAN.md D0 + B1 sizes + 4 phases)

- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- 1m klines: data/raw/btc_intraday_20260924 (BTC),
  data/raw/majors_intraday_20260924 (others). Minutes used: t < 2026-09-24
  00:00 UTC. Missing minutes (NaN) never fill and never trigger an exit
  touch; a fill whose timeout open is NaN is dropped.
- Standard 4h grid per phase p in {0,1,2,3}: holding bar j covers
  [START_p + 4h*j, START_p + 4h*j + 4h) with START_p = 2020-08-01 00:00 UTC
  + p hours. Bar j has 240 minute offsets 0..239; next-bar open is offset
  240. Only bars with open in [2021-09-24 00:00, 2026-09-24 00:00) UTC are
  traded (5 years Y0..Y4 keyed by bar open: [anchor_i, anchor_{i+1}) with
  anchors 2021-09-24..2025-09-24 plus YEAR_END 2026-09-24; Y2
  (2023-09-24..2024-09-24) is 366d, others 365d — same year keying as
  oc_dipexit/oc_fillttl). Phase 0 == oc_dipexit grid exactly.
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
  minute f. Weight w = 1/(1+n_fill) (same for D0/S15/S1 on the same fill;
  fills are identical across variants, only stop exits differ). No
  renormalisation (PRIMARY = raw w*y sums; renormalisation would scale all
  three variants identically on paired fills).
- Post-fill exits (long), evaluated on minutes t in f+1..239 then timeout
  at 240: sl = lv*(1-4*sigma), bl = lv*(1-8*sigma), tp = lv*(1+1.0*sigma).
  - BACKSTOP (unchanged): first t with low(t) <= bl -> exit at
    min(bl, open(t))/lv-1-maker-taker (gap pays the open; min() worse for
    a long), taker 0.00055.
  - TP (unchanged, mu=1.0): first t with high(t) > tp (STRICT) -> exit at
    tp/lv-1-2*maker.
  - STOP (timeframe varies, see below): first clock minute m with
    close(m) <= sl -> exit at open(m+1) (or next-bar open o2 if m=239),
    net = px/lv-1-maker-taker.
  - TIMEOUT (unchanged): else exit at next-bar open o2,
    net = o2/lv-1-maker-taker-fund, fund = 0.0001 if (bar_open+4h).hour in
    (0,8,16) else 0 (v293 settle; longs pay; no funding on intrabar exits).
  - Priority stop-first (v293/oc_dipexit): backstop wins ties
    (kb<=ks and kb<=kt); else TP wins only if strictly earlier (kt<ks);
    else stop; else timeout. A stop and TP in the same minute -> stop wins.
- D0 (deployed baseline, close5): clock minutes m with (m+1)%5==0 on the
  bar offset clock (4,9,...,239; equals global (base+m+1)%5==0 since
  base%5==0 for all phases as shifts 0/60/120/180 are multiples of 5).

## Stop-timeframe variants (fixed, exactly two; level/fees/priority unchanged)

- S15 (close15 stop): clock minutes m with (m+1)%15==0 on the bar offset
  clock (14,29,...,239; equals the absolute-wall-clock 15-minute closes
  since base%15==0 for all phases as shifts 0/60/120/180 are multiples of
  15). First m with close(m) <= sl -> exit at open(m+1) (or o2 if m=239),
  taker 0.00055. Backstop/TP/timeout/levels/fees/funding/priority
  identical to D0 with this ks.
- S1 (close1 stop): EVERY 1m close. First t in f+1..239 with close(t) <=
  sl -> exit at open(t+1) (or o2 if t=239), taker 0.00055. Backstop/TP/
  timeout/levels/fees/funding/priority identical to D0 with this ks.
- Stop LEVEL unchanged at 4 sigma below the fill level (sl from lv),
  8-sigma backstop on 1m lows unchanged, TP 1 sigma unchanged, time exit
  at the next 4h open unchanged. Fills are identical across D0/S15/S1 by
  construction (same lv fill rule); only ks differs post-fill.
- Missing data: NaN closes never trigger a stop; a stop exit at a NaN open
  gives NaN net; timeout at NaN o2 gives NaN net. PAIRED rungs: kept only
  if D0, S15 and S1 nets are ALL finite (same pairing rule as oc_dipexit
  across legs). Weights w are identical across variants on a kept rung.

## Metrics (fixed; per phase, per year, size-weighted)

- Per (phase p, year Y, variant V): over kept paired fills: trades n =
  rung count; win = fraction with y>0 strictly (equal-weight); sum S =
  sum(w*y) (B1 size-weighted, raw, in return-fraction units); stop_n =
  count with how=="stop" (the timeframe stop); stop_mean_bps = 10000 *
  mean(y over stop exits) (NaN if stop_n==0); backstop_n = count with
  how=="backstop" (context); daily sums group w*y by EXIT date (calendar
  UTC date of T+x, x = exit offset, 240 = next-bar open date);
  worst day W = min daily sum; cumulative path over exit dates sorted
  ascending from 0: maxDD = max_{p<q}(C_p - C_q) (>=0, in w*y units).
- 4-phase mean per (year, variant): S_bar = mean_p S_p; n_bar, win_bar,
  stop_n_bar, stop_bps_bar, W_bar, DD_bar = means across p=0..3 of the
  per-phase metric.
- Cascade table (fixed): pool ALL phases' kept fills; daily sums of w*y by
  exit-date UTC per variant (sum across phases per day); take the 10 worst
  calendar days of D0 (most negative pooled D0 daily sums); report on each
  day the pooled D0 / S15 / S1 daily sums. Shows whether a variant
  mitigates the exact days that hurt D0 most.

## Decision rule (fixed, from the assignment; overrides the default same-sign/LOYO rule)

Per year Y0..Y4 on 4-phase means: PASS_sum(Y) iff S_bar_T(Y) >=
S_bar_D0(Y) (not lower; equal passes); PASS_dd(Y) iff DD_bar_T(Y) <=
DD_bar_D0(Y) + 0.01 (not worse by more than 1pp = 0.01 in w*y units).
Variant T (S15, S1) is PROMISING iff (a) PASS_sum in >= 4/5 years AND
(b) PASS_dd in >= 4/5 years. Otherwise NOT PROMISING. One-line verdict in
REPORT.md.

## Protocol / resources (fixed)

- PLAN.md written before any outcome computation. One process; majors 1m
  OHLC held as float32 (all-five-coins O/C plus current-coin H/L loop;
  RAM < 3 GB). No commits; no edits outside research/tournament/oc_stoptf/
  (+ tests/test_oc_stoptf.py).
- Market data up to 2026-09-24 00:00 UTC is read per the assignment (all 5
  years are research data; any PROMISING result needs prospective
  validation before real money). Disclosed against RULES.md 2 / VF_COMMON
  hidden-year conventions.
- Scripts: stoptf.py (pure-numpy core: n vector, B1 size, D0/S15/S1 exact
  outcomes), run.py (phase x coin loop, paired ledger + exit-day sums ->
  results.json). Outputs: results.json, REPORT.md (tables + one-line
  verdict).
