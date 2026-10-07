# oc_marktrig PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

Idea 6 of docs/opencode/IDEAS3_20261006.md (= mark-trigger stops, execution,
BOT): oc_stopslip diagnostic finds 7.2% of Bybit stops never touched on
Binance (venue wicks stop out last-price triggers) while Bybit supports
mark-price triggers; mark (index + premium MA) wicks less than last, so
triggering stops on mark cuts false stop-outs at unchanged protection.

## Hypothesis (fixed here)

Triggering the dip-rung close5 4-sigma stop and the 8-sigma backstop on a
reconstructed mark price instead of the last price raises the yearly
size-weighted rung sum at no worse tail. Pre-registered direction: the
mark-trigger rule beats the last-price base on 4-phase-mean yearly sums
with maxDD not worse and worst day not worse. Fixed rule, no fitted
parameters: single 5-minute premium mean, levels unchanged, TP unchanged.

## Replica (deployed baseline D0 + B1 sizes, exact oc_dipexit / oc_b1deeper)

- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- 1m price klines: `data/raw/btc_intraday_20260924` (BTC),
  `data/raw/majors_intraday_20260924` (others), columns
  open_time/open/high/low/close. Minutes used: t < 2026-09-24 00:00 UTC;
  the timeout/next-minute open at exactly 2026-09-24 00:00 is allowed as an
  exit price only (oc_dipexit convention). Missing minutes (NaN) never fill
  and never trigger an exit touch; a fill whose exit price is NaN is dropped.
- 1m premium index: `data/raw/binance_premium_20260928/{SYM}_premium_1m.parquet`
  (SYM in BTC/ETH/SOL/BNB/XRP + USDT), `close` column as the premium fraction
  (e.g. -0.000777). Rows with open_time >= 2026-09-24 00:00 UTC are dropped at
  load. Missing minutes (NaN) give NaN marks (never trigger).
- Four clock phases: 4h grid from START = 2020-08-01 00:00 UTC + p*1h,
  p in {0,1,2,3}. Phase 0 == oc_dipexit grid exactly. Bar j of phase p covers
  [START + p*1h + 4h*j, +4h). Only bars with open T in
  [2021-09-24 00:00, 2026-09-24 00:00) UTC are traded. Anchor years Y0..Y4
  keyed by bar-open T: Y_k = [A_k, A_{k+1}) for k = 0..3,
  Y_4 = [A_4, 2026-09-24), A = 2021-09-24..2025-09-24 UTC
  (identical to oc_dipexit / oc_fillttl; "+365d" in the assignment).
- sigma_4h(c,T): simple returns r_b = O_b/O_{b-1} - 1 of 4h bar opens on the
  phase's own grid; sigma = std(r over 360 bars ending at T-1, min_periods
  120, ddof=1) = v293/oc_dipexit definition, computed per (phase, coin).
  Known at the bar open T. Bars with non-finite O, sg <= 0 or NaN are skipped.
- Rungs k in {2.5, 3.0, 3.5, 4.0, 5.0} (R2 depths). Level
  lv = O(T) * (1 - k*sg(T)). Resting limit BUY, live window offsets 16..238
  inclusive. Fill at the FIRST offset f with low(T+f) < lv (STRICT
  trade-through). Fill price = lv, fee maker 0.0002. At most one fill per
  (phase, bar, coin, k).
- B1 size (oc_b1deeper-exact): n(a,T,m) = number of OTHER majors b != a with
  finite O_b(T), finite C_b(T+m-1), finite sg_b(T) > 0 AND
  C_b(T+m-1) <= O_b(T)*(1 - 2.5*sg_b(T)) (<= counts; v399-exact; own coin
  never counted). w = 1/(1+n_fill) at the fill minute f. Fills (lv, f, w)
  are IDENTICAL across BASE and MARK arms; only the post-fill stop triggers
  differ, so weights are identical on every paired rung.
- Post-fill exits BASE (long), oc_dipexit D0 replica from the fill price px
  (= lv): sl = px*(1-4*sg), bl = px*(1-8*sg), tp = px*(1+1.0*sg). Evaluated
  on minutes t in f+1..239 then timeout at 240 (next-bar open o2):
  backstop touch (first t with low(t) <= bl) exits at min(bl,open(t)) taker;
  else TP touch (first t with high(t) > tp, STRICT) exits at tp maker
  (2*maker round-trip); else close5 stop (clock minutes m with (m+1)%5==0 on
  bar-relative offsets 4,9,...,239 -- equals the global 5-min clock since
  every phase base (0/60/120/180) is a multiple of 5 -- first m with
  close(m) <= sl) exits at open(m+1) (or o2 if m=239) taker; else timeout at
  o2 taker + funding 0.0001 if (T+4h).hour in (0,8,16) (v293 settle rule;
  longs pay; no funding on intrabar exits). Priority stop-first: backstop
  wins ties (kb<=ks and kb<=kt); else TP wins only if strictly earlier
  (kt<ks); else stop; else timeout. A stop and TP in the same minute ->
  stop wins. Net returns are fractions of px. Fees: fill maker 0.0002; TP leg
  maker 0.0002 (total 2*maker on TP); stop/backstop/time legs taker 0.00055.

## MARK rule (fixed, trigger only; levels, TP, costs unchanged)

- Reconstructed mark at minute t (absolute), per coin:
  prem(t) = premium-index 1m `close` at minute t (fraction; NaN if missing).
  prem_ma5(t) = mean of finite prem(s) for s in [t-4, t] (trailing 5-minute
  mean including the trigger minute; strictly causal: only premium <= t
  enters; if none of the 5 is finite, prem_ma5 = NaN). mark(t) =
  close(t) * (1 + prem_ma5(t)) with the price 1m `close` at t; NaN if either
  leg is NaN (NaN marks never trigger).
- MARK levels identical to BASE (sl/bl/tp from the same px = lv, same sg).
  MARK-TP identical to BASE-TP (first t with high(t) > tp, STRICT, exit at
  tp, 2*maker). MARK-TIMEOUT identical to BASE (o2 taker + settle funding).
- MARK-CLOSE5: clock minutes m with (m+1)%5==0, first m in f+1..239 with
  finite mark(m) <= sl (mark replaces last close; NaN never fires). Exit at
  open(m+1) (or o2 if m=239) taker, net = px_exit/px-1-maker-taker
  (-0.0001 if x==240 and settling). Same market-next-open exit as BASE.
- MARK-BACKSTOP: first t in f+1..239 with finite mark(t) <= bl (mark-close
  replaces last low; wick touch is deliberately ignored: mark wicks less).
  Because mark(t) is known only at the close of minute t, the market exit is
  necessarily at the NEXT minute open: exit at open(t+1) (or o2 if t==239)
  taker, net = px_exit/px-1-maker-taker (-0.0001 if x==240 and settling).
  This differs causally from the BASE backstop (same-minute min(bl,open));
  the difference is disclosed and unavoidable: a close-based trigger cannot
  exit inside its own trigger minute.
- MARK priority stop-first on trigger indices (same shape as BASE): backstop
  wins ties (kb<=ks and kb<=kt); else TP wins only if strictly earlier
  (kt<ks); else stop; else timeout. A mark stop and TP in the same minute ->
  stop wins. Stop-first on same-bar SL/TP ties and the minute-5 rule are kept.
- Leakage: every mark trigger uses only price close(t) and premium <= t;
  sigma excludes the bar; n uses closes up to m-1; fills use strict
  trade-through; exits use minutes <= exit; no statistic is fitted on any
  test year (zero fitted parameters).

## Scoring (fixed here)

- Paired rungs: kept only if BASE net AND MARK net are both finite (same
  pairing rule as oc_dipexit across legs; fills identical, exits may differ
  in finiteness because MARK-backstop exits one minute later).
- Per (phase p, year Y, variant V in {BASE, MARK}): over kept paired fills:
  n = rung count; stop count = n_stop (close5 exits) + n_backstop
  (backstop exits), with the split reported; sum S = sum(w*y) (B1
  size-weighted, raw, return-fraction units; no renormalisation -- fills and
  weights are identical across arms, so renormalisation would scale both
  identically); win = fraction with y > 0 strictly (equal-weight,
  descriptive); daily sums group w*y by EXIT date (calendar UTC date of
  T+x, x = exit offset, 240 = next-bar open date = (T+4h).date()); worst day
  W = min daily sum; cumulative path over exit dates sorted ascending from
  0: maxDD = max_{peak<trough}(peak - trough) (>= 0, in w*y units).
- Avoided-stop decomposition (per phase-year, then 4-phase means): over
  paired rungs where BASE how in {stop, backstop} (base stopped): avoided =
  MARK how in {tp, time} (no mark stop); breakdown avoided_tp (MARK tp),
  avoided_time (MARK timeout), plus deeper (BASE close5 stop but MARK
  backstop: the mark ran deeper) and still_stop (MARK close5 stop) as
  context; the full 2x4 BASE-how x MARK-how confusion counts are stored in
  results.json. Rates use base-stop denominators.
- 4-phase means per year: S_bar(Y) = mean_p S(p,Y); DD_bar(Y) = mean_p
  DD(p,Y); W_bar(Y) = mean_p W(p,Y); n_bar/stop_bar/avoided_bar = means
  across p=0..3. Per-phase sums are also reported (clock swing context).
- 5y sums: sum5y = sum_Y S_bar(Y) per variant; dSum5y = sum5y_MARK -
  sum5y_BASE (context only, NOT a decision leg).
- Cascade table (10 worst days): pool all phases' kept rungs; group w*y by
  exit date per variant; take the 10 calendar-UTC exit dates with the
  smallest BASE pooled daily sum; per date report BASE sum, MARK sum, delta,
  BASE stops, MARK stops, BASE TPs, MARK TPs (counts pooled over phases).
- DECISION RULE (from the assignment, overrides the tournament default):
  PASS_sum(Y) iff S_bar_MARK(Y) >= S_bar_BASE(Y) (not lower; equal passes);
  PASS_dd(Y) iff DD_bar_MARK(Y) <= DD_bar_BASE(Y) (not worse; equal passes);
  PASS_wd(Y) iff W_bar_MARK(Y) >= W_bar_BASE(Y) (not worse; equal passes).
  PROMISING iff (a) PASS_sum in >= 4/5 years AND (b) PASS_dd in >= 4/5 years
  AND (c) PASS_wd in >= 4/5 years. Otherwise NOT PROMISING. One-line verdict
  in REPORT.md.
- Market data up to 2026-09-24 00:00 UTC is read per the assignment (all
  five years are research data; any PROMISING result needs prospective
  validation before real money). Disclosed against RULES.md 2 / VF_COMMON
  hidden-year conventions.

## Protocol / resources (fixed)

- PLAN.md written before any outcome computation (this file). Then scripts:
  `marktrig.py` (pure-numpy core: n vector, B1 size, BASE D0-from-fill exit,
  mark series builder, MARK-from-fill exit with next-open backstop), `run.py`
  (per-phase/per-coin loop, paired ledger + exit-day sums + avoided-stop
  confusion + cascade table -> results.json). Outputs: results.json,
  REPORT.md (tables + one-line verdict). Tests:
  `tests/test_oc_marktrig.py` (synthetic hand checks + causality: mark uses
  only premium <= t; BASE backstop on low vs MARK backstop on mark-close with
  next-open exit; close5 clock; stop-first ties; sigma excludes the bar;
  fill uses only m-1 closes).
- One process, one coin's H/L in RAM at a time; all-five-coins 1m O/C plus
  all-five-coins premium held as float32 arrays; RAM < 3 GB. Runs > 0.4 GB
  via `scripts/heavy_slot.py run`. No commits; no edits outside
  research/tournament/oc_marktrig/ (+ tests/test_oc_marktrig.py).
