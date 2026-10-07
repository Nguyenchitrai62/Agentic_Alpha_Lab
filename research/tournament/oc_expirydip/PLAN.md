# oc_expirydip PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

Idea #76 (= docs/opencode/IDEAS2_20261006.md idea 9: expiry-day dip-add / pin-flush buyer).

## Hypothesis (fixed here)

oc_expirybook halves BOOK exposure into monthly Deribit expiry (variance down,
P&L flat); the mirror image is untested: expiry pins create intraday
flush-and-recover prints that the R2 ladder (depths from 4h sigma) is too
shallow to catch. Hypothesis: ONE extra deep bid (5.0 sigma, base B1 size)
on Deribit monthly expiry days (00:00-12:00 UTC) buys that pin flush at no
worse tail, so the dip book with the extra rung beats the base dip book on
yearly sums at no worse drawdown. Fixed rule, no fitted parameters: single
depth (5.0 sigma), single day-window (expiry 00:00-12:00 UTC), base B1 size,
D0 exits.

## Replica (deployed baseline, exact oc_dipexit D0 + oc_b1deeper B1 sizes)

- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- 1m klines: `data/raw/btc_intraday_20260924` (BTC),
  `data/raw/majors_intraday_20260924` (others). Minutes used:
  t < 2026-09-24 00:00 UTC. Missing minutes (NaN) never fill, never trigger
  an exit touch, never count as flushing; a fill whose exit price is NaN
  is dropped.
- Four clock phases: 4h grid from START = 2020-08-01 00:00 UTC + p*1h,
  p in {0,1,2,3}. Phase 0 == oc_dipexit grid exactly. Bar j of phase p
  covers [START + p*1h + 4h*j, +4h). Only bars with open T in
  [2021-09-24 00:00, 2026-09-24 00:00) UTC are traded. Anchor years
  Y0..Y4 keyed by bar-open T: Y_k = [A_k, A_{k+1}) for k = 0..3,
  Y_4 = [A_4, 2026-09-24), A = 2021-09-24..2025-09-24 UTC
  (identical to oc_dipexit / oc_placebo_dip; "+365d" in the assignment).
- sigma_4h(c,T): simple returns r_b = O_b/O_{b-1} - 1 of 4h bar opens on the
  phase's own grid; sigma = std(r over 360 bars ending at T-1, min_periods
  120, ddof=1) = v293/oc_dipexit definition, computed per (phase, coin).
  Known at the bar open T. Bars with non-finite O, sg <= 0 or NaN are
  skipped (no rungs that bar).
- Rungs k in {2.5, 3.0, 3.5, 4.0, 5.0} (R2 depths). Level
  lv = O(T) * (1 - k*sg(T)). Resting limit BUY, live window offsets
  16..238 inclusive. Fill at the FIRST offset f with low(T+f) < lv (STRICT
  trade-through). Fill price = lv, fee maker 0.0002.
- B1 size (oc_b1deeper-exact): n(a,T,m) = number of OTHER majors b != a
  with finite O_b(T), finite C_b(T+m-1), finite sg_b(T) > 0 AND
  C_b(T+m-1) <= O_b(T)*(1 - 2.5*sg_b(T)) (<= counts; v399-exact; own coin
  never counted). w = 1/(1+n_fill) at the fill minute f.
- Post-fill exits (long), oc_dipexit D0 replica from the fill price px:
  sl = px*(1-4*sg), bl = px*(1-8*sg), tp = px*(1+1.0*sg). Evaluated on
  minutes t in f+1..239 then timeout at 240 (next-bar open o2):
  backstop touch (first t with low(t) <= bl) exits at min(bl,open(t))
  taker; else TP touch (first t with high(t) > tp, STRICT) exits at tp
  maker (2*maker round-trip); else close5 stop (clock minutes m with
  (m+1)%5==0, first m with close(m) <= sl) exits at open(m+1) (or o2 if
  m=239) taker; else timeout at o2 taker + funding 0.0001 if
  (T+4h).hour in (0,8,16) (v293 settle rule; longs pay; no funding on
  intrabar exits). Priority stop-first: backstop wins ties (kb<=ks and
  kb<=kt); else TP wins only if strictly earlier (kt<ks); else stop;
  else timeout. A stop and TP in the same minute -> stop wins.
  Net returns are fractions of px. Kept only if the y1.0 net is finite.
- Market data up to 2026-09-24 00:00 UTC is read per the assignment (all
  five years are research data; any PROMISING result needs prospective
  validation before real money). Disclosed against RULES.md 2 / VF_COMMON
  hidden-year conventions.

## Expiry calendar + extra rung (fixed here, zero leakage)

- Expiry calendar (pure function of year/month, no market input):
  E(y,m) = last Friday of month m (date), for 2021-01 .. 2026-09.
  Friday == weekday 4; back = (last_day.weekday() - 4) % 7.
- Expiry window on bar-open time T (half-open): in_exp(T) iff T.date()
  is a monthly expiry date AND T.time() in [00:00, 12:00) UTC. For phase 0
  this is exactly the 4h bars opening 00:00, 04:00, 08:00 per the
  assignment; for phases 1/2/3 it is the 3 bars opening inside the same
  12h window (01/05/09, 02/06/10, 03/07/11). The calendar is known years
  in advance: zero leakage by construction.
- RULE (fixed): on bars with in_exp(T), per coin, add ONE extra rung bid
  at k = 5.0 sigma: level lvx = O(T)*(1 - 5.0*sg(T)) (identical to the
  base 5.0 rung level), same live window 16..238, fill iff low < lvx
  (STRICT), fill price lvx, size wx = 1/(1+nx) with nx = n(a,T,f) at its
  own fill minute (base B1 size rule), exits = D0 replica from lvx
  (TP 1.0 sigma, close5 stop 4 sigma, 8 sigma backstop, timeout at the
  next 4h open; same fees/funding/priority). All other bars unchanged;
  the base 5.0 rung is always kept, so on an expiry bar that fills 5.0
  the rule holds TWO 5.0-sigma positions (double 5.0 exposure that bar).
  An extra rung whose y1.0 net is non-finite is dropped (same as base).
- BASE = all base rungs (5 depths x filled bars). RULE = BASE + extra
  rungs. Year of a rung (base or extra) = bar-open year of its bar.

## Scoring (fixed here)

- Per (phase p, year Y): S = sum(w*y) over rungs in that cell (base-only
  for BASE; base+extra for RULE); daily sums by EXIT date (calendar UTC
  date of T+x, x = exit offset, 240 = next-bar date = (T+4h).date());
  worst day W = min daily sum; maxDD = max_{peak<trough}(peak - trough)
  of the cumulative daily-sum path from 0 (>= 0, in w*y units); n = fill
  count; win = fraction of fills with y > 0 strictly (descriptive).
- 4-phase means per year: S_bar(Y) = mean_p S(p,Y);
  DD_bar(Y) = mean_p DD(p,Y); W_bar(Y) = mean_p W(p,Y). Extra-rung
  stats per year (4-phase mean sums/counts + pooled win rate) reported
  descriptively.
- 5y sums: sum5y = sum_Y S_bar(Y) per variant; dSum5y = sum5y_RULE -
  sum5y_BASE. dDDmean = mean_Y(DD_rule - DD_base); full pooled path DD
  (all phases concatenated by exit date) as context.
- DECISION RULE (from the assignment, overrides the tournament default):
  PASS_sum(Y) iff S_bar_RULE(Y) >= S_bar_BASE(Y);
  PASS_dd(Y) iff DD_bar_RULE(Y) <= DD_bar_BASE(Y) + 0.01 (1 pp tolerance,
  oc_placebo_dip convention). PROMISING iff (a) PASS_sum in >= 4/5 years
  AND (b) PASS_dd in >= 4/5 years AND (c) dSum5y >= +0.273 (pooled
  placebo p95, research/tournament/oc_placebo_dip). Otherwise
  NOT PROMISING. One-line verdict in REPORT.md. The default LOYO leg is
  N/A by construction: the rule has no fitted parameter (pure calendar +
  fixed 5.0 depth/size), so there is nothing to leave out (same rationale
  as oc_expirybook).
- The BOT book (forward_v205.research_books_d2, see
  research/diagnostics/r2_decompose5/r2_decompose5.py) is shared context
  only; this screen gates the dip-leg delta (base vs rule) exactly as
  the placebo gate was calibrated (w*y units).

## Protocol / resources (fixed)

- PLAN.md written before any outcome computation. Then scripts:
  `expirydip.py` (pure-numpy core: n vector, B1 size, D0-from-fill exit,
  expiry calendar), `run.py` (per-phase/per-coin loop, base + extra
  ledgers + exit-day sums -> results.json). Outputs: results.json,
  REPORT.md (tables + one-line verdict). Tests:
  `tests/test_oc_expirydip.py` (synthetic hand checks + causality:
  expiry calendar dates, window membership needs no market data, fill
  uses only m-1 closes, sigma excludes the bar, extra duplicates 5.0).
- One process, one coin's H/L in RAM at a time; all-five-coins 1m O/C
  held as float32 arrays; RAM < 3 GB. Runs > 0.4 GB via
  `scripts/heavy_slot.py run`. No commits; no edits outside
  research/tournament/oc_expirydip/ (+ tests/test_oc_expirydip.py).
