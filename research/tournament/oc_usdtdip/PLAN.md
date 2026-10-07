# oc_usdtdip PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

Idea #73 (NEW): USDT/USD premium as a DIP rung size tilt.

## Hypothesis (fixed here)

The USDT price vs $1.00 on a USD venue measures fiat inflow demand bidding
for stablecoin inventory (on-ramp pressure) vs redemption / risk-off outflow.
oc_premexpo found this signal ALPHA for book LONGS vs an exposure-matched
control (USDT 5y gain +0.049, positive 4/5 years, 5y placebo pct 99.4).
Hypothesis: the same slow inflow signal tilts dip-buying payoffs too, so
scaling dip-rung SIZES up when the USDT premium is elevated (z > 1) and down
when deeply negative (z < -1) raises the dip sleeve's total P&L at no
systematic drawdown cost. Direction pre-registered: the tilt beats the
size-only base on yearly 4-phase-mean sums at no worse maxDD, beyond what a
constant exposure uplift would give. Fixed multipliers, no fitted parameters.

Rule (fixed, from the assignment): rung sizes x1.2 when z > 1, x0.8 when
z < -1, else x1.0 (all coins, all depths), z taken at the bar open.

## Replica (deployed baseline: D0 exits + B1 sizes, 4 clock phases)

Exact replica of research/tournament/oc_dipexit/PLAN.md D0 (code reused
verbatim in `core.py`), with oc_b1deeper B1 sizes, on all four clock phases
(oc_placebo_dip convention):

- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- 1m klines: data/raw/btc_intraday_20260924 (BTC),
  data/raw/majors_intraday_20260924 (others). Minutes used:
  t < 2026-09-24 00:00 UTC. Missing minutes (NaN) never fill, never trigger
  an exit touch, and never count as flushing; a fill whose timeout open is
  NaN is dropped.
- Four clock phases p in {0,1,2,3}: 4h grid of bars covering
  [START + p*1h + 4h*j, START + p*1h + 4h*j + 4h) with
  START = 2020-08-01 00:00 UTC. Phase 0 == the oc_dipexit grid exactly.
  Bar j has 240 minute offsets 0..239; next-bar open is offset 240. Only
  bars with open T in [2021-09-24 00:00, 2026-09-24 00:00) UTC are traded
  (5 years Y0..Y4 = [anchor, anchor+365d), anchors 2021-09-24..2025-09-24,
  keyed by T; Y4 = [2025-09-24, 2026-09-24) = 365d).
- sigma_4h per coin at bar open T (known at T): simple returns
  r_b = O_b / O_{b-1} - 1 of that phase's 4h bar opens;
  sigma(T) = std(r over 360 bars ending at T-1, min_periods 120, ddof=1)
  (= v293/oc_dipexit; shift(1) so the bar itself is excluded). Bars with
  non-finite O, sigma <= 0 or NaN are skipped (no rungs that bar).
- Rungs k in {2.5, 3.0, 3.5, 4.0, 5.0} (R2 depths). Level
  lv = O(T) * (1 - k*sigma(T)). Resting limit BUY at lv, live window
  offsets 16..238 inclusive. Fill at the FIRST offset f with
  low(T+f) < lv (STRICT trade-through). Fill price = lv, maker 0.0002.
  At most one fill per (bar, k). Exit uses only minutes <= f of the bar
  for the fill and f+1..239 + next-bar open for the race.
- B1 size (oc_b1deeper-exact, causal: uses only closes up to minute m-1):
  n(a,T,m) = number of OTHER majors b != a with finite O_b(T),
  finite C_b(T+m-1), finite sg_b(T) > 0 AND
  C_b(T+m-1) <= O_b(T) * (1 - 2.5*sg_b(T)) (<= counts; NaN = not
  flushing; own coin never counted, 0..4). At the fill minute f,
  n_fill = n(a,T,f); w_base = 1/(1+n_fill).
- Post-fill exits (long), oc_dipexit D0 replica from fill price lv:
  sl = lv*(1-4*sg), bl = lv*(1-8*sg), tp = lv*(1+1.0*sg), on minutes
  t in f+1..239 then timeout at 240 (next-bar open o2):
  backstop touch (first t with low(t) <= bl) exits at min(bl,open(t))
  taker 0.00055; else TP touch (first t with high(t) > tp, STRICT) exits
  at tp maker (total 2*maker with the fill leg); else close5 stop (clock
  minutes m with (m+1)%5==0, first m with close(m) <= sl) exits at
  open(m+1) (or o2 if m=239) taker; else timeout at o2 taker + funding
  0.0001 if (T+4h).hour in (0,8,16) (v293 settle rule; no funding on
  intrabar exits). Priority stop-first: backstop wins ties
  (kb<=ks and kb<=kt); else TP wins only if strictly earlier (kt<ks);
  else stop; else timeout. Stop and TP in the same minute -> stop wins.
  Net returns are fractions of lv. Fills with non-finite exit nets are
  DROPPED (same fills dropped for base/rule/control, so membership is
  identical across arms).
- Kept fills: filled on lv AND D0 y1.0 finite. (oc_placebo_dip additionally
  required y0.9/y1.1 finite for its TP-jitter legs; they are not needed
  here, so only y1.0 finiteness is required. The level difference vs the
  placebo base is disclosed; the +0.273 gate below is an absolute delta.)

## USDT premium feature (oc_usdtprem-exact, fixed here)

- Source: data/raw/coinbase_usdt_20261006/USDT-USD_1h.parquet (Coinbase
  Exchange public REST candles, USDT-USD, granularity 3600; bar STARTs
  `t < 2026-09-24 00:00 UTC` only; manifest + sha recorded in results.json;
  Kraken fallback NOT used).
- prem[t] = close[t] - 1 (USDT priced in USD); mean24[t] = mean(prem[t-23..t]),
  rolling(24, min_periods=20); z[t] = (mean24[t] - mean(W)) / std(W, ddof=1),
  W = up to 2160 prior mean24 values (90 days of hourly samples, current
  excluded via .shift(1)), rolling(2160, min_periods=1728); std == 0 -> NaN.
- As-of (strict, hourly bars closed strictly before the 4h bar open,
  oc_usdtprem/oc_optctx convention): an hourly row with start t (end
  t+1h) is usable at T iff end <= T - 1s
  (searchsorted(ends_ns, Tns - 1e9, side='left') - 1). For 4h-aligned T the
  last usable hourly bar is [T-2h, T-1h] (1-2h staleness by design).
  z(T) = z of the last usable row (NaN if none / warm-up; never tilted).
  One signal per bar, applied to all 5 coins and all depths (market-wide).
- RULE (this idea, fixed multipliers): per kept fill on bar T,
  mult = 1.2 if z(T) > 1 else (0.8 if z(T) < -1 else 1.0); NaN z -> 1.0.
  w_rule = w_base * mult. z(T) uses only hourly bars ending strictly
  before T (causal by construction).

## Exposure-matched control (fixed here)

Per (year Y, phase p): avg_mult(Y,p) = mean per-fill mult over kept fills
in that year-phase cell (equal-weight; = 1.0 if the cell is empty).
w_ctrl = w_base * avg_mult(Y,p) (one constant per year-phase cell; same
fills, same y, only the size level is matched). 4-phase-mean control sums
therefore remove the year's mean-exposure difference within each phase, so
gain(Y) = Sbar_rule(Y) - Sbar_ctrl(Y) isolates TIMING. The control is an
in-year diagnostic (uses the in-year average), not a tradable rule.

## Scoring (fixed here)

- Daily sums per (arm, year, phase): group w*y by EXIT date (calendar UTC
  date of T+x, x = exit offset, 240 = next-bar open date). Yearly-phase sum
  S = sum of daily sums (= sum w*y); worst day W = min daily sum;
  cumulative path over exit dates sorted ascending from 0: maxDD = max
  drawdown of the cumsum (>= 0; 0 when monotone non-decreasing); trades n =
  kept fills; win = fraction of kept fills with y > 0 strictly
  (equal-weight; identical membership across arms, reported per arm).
- 4-phase means per year: Sbar(Y) = mean_p S(p,Y); DDbar(Y) = mean_p
  DD(p,Y); Wbar(Y) = mean_p W(p,Y); nbar(Y) = mean_p n(p,Y);
  winbar(Y) = mean_p win(p,Y). 5y 4-phase-mean delta:
  dSum5y = sum_Y Sbar_rule(Y) - sum_Y Sbar_base(Y). Full pooled path
  (all phases, exit-date order) sum/DD as context only.
- Tilt shares per (year, phase): share of kept FILLS with mult 1.2 (up) /
  0.8 (down); plus share of traded BARS (bars with valid O/sigma where
  rungs were live) with z > 1 / z < -1. 4-phase means reported; pooled-year
  averages in results.json for audit.
- DECISION RULE (assignment-specific, replaces the default same-sign/LOYO
  rule; LOYO N/A by construction — fixed z = +/-1 thresholds and fixed
  1.2/0.8 multipliers, no in-year fit to leave out): PROMISING only if
  (a) 4-phase-mean sum Sbar_rule(Y) >= Sbar_base(Y) in >= 4/5 years AND
      DDbar_rule(Y) <= DDbar_base(Y) + 0.01 (1 pp tolerance, placebo
      convention) in >= 4/5 years, AND
  (b) 5y 4-phase-mean sum delta dSum5y >= +0.273 (pooled placebo p95 from
      oc_placebo_dip), AND
  (c) gain over the exposure-matched control
      Sbar_rule(Y) - Sbar_ctrl(Y) > 0 (strict) in >= 4/5 years.
  NaN on either side counts as FAIL. One-line verdict in REPORT.md.

## Protocol / resources (fixed)

- PLAN.md written before any outcome computation. Then scripts: `core.py`
  (verbatim D0 outcome_mu + B1 n/size/fill core, no I/O), `compute_usdtdip.py`
  (per-coin loop over 4 phases, USDT z join, per-arm ledgers ->
  results.json), `panel.parquet` (per-fill rows: phase/sym/year/bar/rung/
  w_base/mult/w_rule/w_ctrl/y/exit-day). Outputs: results.json, REPORT.md
  (tables + one-line verdict). Tests: tests/test_oc_usdtdip.py (synthetic
  hand checks + causality: fill uses only m-1 closes; sigma excludes the
  bar; z as-of strictly before T; NaN-z never tilted; same membership all
  arms; control constant per year-phase).
- One process, one coin's H/L in RAM at a time; all-five-coins 1m O/C held
  as float32 arrays; hourly + 4h frames only otherwise. RAM < 3 GB. Heavy
  run through the shared semaphore (scripts/heavy_slot.py, never --leader).
- Market data up to 2026-09-24 00:00 UTC is read per the assignment (all 5
  years are research data; any PROMISING result needs prospective
  validation before real money). Disclosed against RULES.md 2 / VF_COMMON
  hidden-year conventions. No commits; no edits outside
  research/tournament/oc_usdtdip/ (+ tests/test_oc_usdtdip.py).

## Post-hoc log

- (none yet; filled only if definitions change after outcomes are seen)
