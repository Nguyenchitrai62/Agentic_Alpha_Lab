# oc_relflush PLAN (pre-registered BEFORE any outcome is computed, 2026-10-07)

Idea: inside a multi-coin flush, size the coin that overshoots the others more
(bot_only dip screen). Assignment: docs/opencode/OPENCODE_W_oc_relflush.md +
docs/opencode/OPENCODE_W_COMMON_20261007.md + AGENTS.md + docs/opencode/OPENCODE_VF_COMMON.md.

## Hypothesis (fixed here)

Deployed corr-aware sizing (v399 B1, idea oc_b1deeper baseline) cuts every rung to
w = 1/(1+n_fill), n_fill = number of OTHER majors >= 2.5 sigma below their own
4h bar open at minute f-1. It treats all coins of a flush alike. Closed variants
changed the SHAPE in n (oc_b1shape, oc_b1soft), the detector (oc_b1wide, oc_b1btc)
or the price (oc_b1deeper) — none used the cross-section INSIDE the flush.
Hypothesis: within a flush, the coin that has fallen further than the others
(in its own sigma units) holds an idiosyncratic overshoot on top of the market
move and rebounds more; the coin that lags the flush is more likely to catch
down. Direction pre-registered: R1 (up-weight high-rel, down-weight low-rel)
beats B1 on yearly 4-phase-mean sums at no worse maxDD; R2 (sign control,
mirrored tilts) must look like the mirror image of R1 for the mechanism to be
believed; R3 (smooth linear tilt) is the second candidate. Fixed thresholds and
multipliers, no fitted parameters.

## Replica (deployed baseline: D0 exits + B1 sizes, 4 clock phases; oc_placebo_dip-exact)

Exact replica of research/tournament/oc_placebo_dip/compute_placebo_dip.py
(D0 + B1; code copied into `core.py`, oc_placebo_dip NOT edited):

- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- 1m klines: data/raw/btc_intraday_20260924 (BTC),
  data/raw/majors_intraday_20260924 (others). Minutes used:
  t in [2020-08-01 00:00, 2026-09-24 00:00] UTC; t < 2026-09-24 00:00 traded.
  Missing minutes (NaN) never fill, never trigger an exit touch, never count
  as flushing; a fill whose exit price is NaN is dropped.
- Four clock phases p in {0,1,2,3}: 4h grid of bars covering
  [START + p*1h + 4h*j, START + p*1h + 4h*j + 4h) with
  START = 2020-08-01 00:00 UTC. Phase 0 == oc_dipexit grid exactly.
  Bar j has 240 minute offsets 0..239; next-bar open is offset 240. Only bars
  with open T in [2021-09-24 00:00, 2026-09-24 00:00) UTC are traded
  (5 years Y0..Y4 = [anchor, anchor+365d), anchors 2021-09-24..2025-09-24,
  keyed by bar-open T; Y4 = [2025-09-24, 2026-09-24)).
- sigma_4h per coin at bar open T (known at T): simple returns
  r_b = O_b / O_{b-1} - 1 of that phase's 4h bar opens;
  sigma(T) = std(r over 360 bars ending at T-1, min_periods 120, ddof=1)
  (= v293/oc_dipexit; shift(1) so the bar itself is excluded). Bars with
  non-finite O, sigma <= 0 or NaN are skipped (no rungs that bar).
- Rungs k in {2.5, 3.0, 3.5, 4.0, 5.0} (R2 depths). Level
  lv = O(T) * (1 - k*sigma(T)). Resting limit BUY at lv, live window offsets
  16..238 inclusive. Fill at the FIRST offset f with low(T+f) < lv (STRICT
  trade-through). Fill price = lv, maker 0.0002.
- B1 size (oc_b1deeper-exact, causal: uses only closes up to minute m-1):
  n(a,T,m) = number of OTHER majors b != a with finite O_b(T),
  finite C_b(T+m-1), finite sg_b(T) > 0 AND
  C_b(T+m-1) <= O_b(T) * (1 - 2.5*sg_b(T)) (<= counts; NaN = not flushing;
  own coin never counted, 0..4). At the fill minute f, n_fill = n(a,T,f);
  w_base = 1/(1+n_fill).
- Post-fill exits (long), oc_dipexit D0 replica from fill price lv:
  sl = lv*(1-4*sg), bl = lv*(1-8*sg), tp = lv*(1+1.0*sg), on minutes
  t in f+1..239 then timeout at 240 (next-bar open o2):
  backstop touch (first t with low(t) <= bl) exits at min(bl,open(t))
  taker 0.00055; else TP touch (first t with high(t) > tp, STRICT) exits
  at tp maker (total 2*maker with the fill leg); else close5 stop (clock
  minutes m with (m+1)%5==0, first m with close(m) <= sl) exits at
  open(m+1) (or o2 if m=239) taker; else timeout at o2 taker + funding
  0.0001 if (T+4h).hour in (0,8,16) (v293 settle rule; longs pay; no funding
  on intrabar exits). Priority stop-first: backstop wins ties
  (kb<=ks and kb<=kt); else TP wins only if strictly earlier (kt<ks);
  else stop; else timeout. Stop and TP in the same minute -> stop wins.
  Net returns are fractions of lv. Kept fills: filled on lv AND D0 y1.0
  finite. (Placebo additionally required y0.9/y1.1 finite for its TP-jitter
  legs; only y1.0 is needed here — oc_usdtdip/oc_expirydip showed this
  pairing differs nowhere on this grid; fidelity check below guards it.)
- Gate costs: maker 0.0002, taker 0.00055, longs pay 0.0001 per 8h settlement
  held (00/08/16 UTC), shorts N/A (long-only sleeve). Limit fills only on
  strict 1m trade-through; live window starts at offset 16 (no fill in the
  first 5 minutes after a 4h close is satisfied a fortiori).
- Budget/caps exactly as the replica (no re-normalisation): weights w used
  directly in w*y sums; no per-year/per-phase renormalisation.

## Relative-flush feature (fixed here, bot_only, minute f-1 only)

For a fill of coin i at minute f (offset 16..238, bar open T on the same
phase clock), using ONLY information up to minute f-1:

- P_x(f-1) = 1m `close` of coin x at minute T+f-1 (last fully closed minute;
  within-bar NaN stays NaN; no cross-bar ffill).
- O_x = 4h bar `open` of coin x at T (1m `open` at minute T, same phase grid).
- sigma_x = ladder sigma of coin x at T (as above).
- d_x = -log(P_x(f-1) / O_x) / sigma_x for every major x (5 values; own coin
  included). Non-finite O_x / P_x / sigma_x, O_x <= 0, P_x <= 0, sigma_x <= 0
  -> d_x = NaN (never flushing; rel falls back to 1.0 below).
- F = set of OTHER majors x != i with d_x >= 2.5 (the B1 flush set; up to
  log-vs-simple threshold sliver vs the n detector — disclosed; n_fill from
  the replica is authoritative for the 1/(1+n) base, F is authoritative for
  the rel mean).
- rel = d_i - mean_{x in F} d_x. Undefined (NaN) if d_i is NaN, F is empty,
  or any member d_x is NaN (cannot happen by construction) or the mean is
  non-finite -> tilt 1.0. Fills with n_fill = 0 keep w = 1 (no tilt even if
  rel is computable; same as 1/(1+0)*1).
- Variants (fixed; ONLY these three; all bot_only):
  - R1: w = 1/(1+n) * (1.5 if rel > +0.5; 0.75 if rel < -0.5; else 1).
  - R2 (sign control): w = 1/(1+n) * (0.75 if rel > +0.5; 1.5 if rel < -0.5; else 1).
  - R3: w = 1/(1+n) * clip(1 + 0.25*rel, 0.6, 1.4).
  Strict > / < at +-0.5 (equality -> 1.0); clip bounds inclusive.
  Same fills, same y1.0, same exit days as base in every arm (size-only
  change; membership identical across arms by construction).

## Scoring (fixed here)

- Daily sums per (arm, year, phase): group w*y by EXIT date (calendar UTC date
  of T+x, x = exit offset, 240 = next-bar open date). Yearly-phase sum S =
  sum of daily sums (= sum w*y); worst day W = min daily sum; cumulative path
  over exit dates sorted ascending from 0: maxDD = max drawdown of the cumsum
  (>= 0; 0 when monotone non-decreasing); trades n = kept fills; win =
  fraction of kept fills with y > 0 strictly (equal-weight; identical
  membership across arms).
- 4-phase means per year: Sbar(Y) = mean_p S(p,Y); DDbar(Y) = mean_p DD(p,Y).
  5y 4-phase-mean delta: dSum5y = sum_Y Sbar_rule(Y) - sum_Y Sbar_base(Y).
  Full pooled path (all phases, exit-date order) sum/DD as context only.
- Fidelity gate (from the assignment): reproduce the placebo base 5y
  4-phase-mean sum 7.718 first (tolerance 1e-3 per phase-0 raw leg and exact
  4-phase means 0.911/0.833/2.100/3.197/0.677 to 3 decimals); else STOP.
- DECISION (established dip-screen gate, calibrated on ALL FIVE years — the
  most recent year is part of it, labelled as such): PROMISING iff
  (a) Sbar_rule(Y) >= Sbar_base(Y) in >= 4/5 years AND
  (b) DDbar_rule(Y) <= DDbar_base(Y) + 0.01 (1 pp tolerance, placebo
  convention) in >= 4/5 years AND
  (c) 5y 4-phase-mean sum delta dSum5y >= +0.273 (pooled placebo p95,
  research/tournament/oc_placebo_dip). NaN on either side counts as FAIL.
  Applies separately to R1 and R3 (R2 is a sign control, never promoted).
- Protocol view (also reported): the same legs (a)+(b) on the four dev years
  only (Y0..Y3, >= 3/4 each leg); dSum_dev4 reported without a gate; choice
  among R1/R3 on dev4 only; R2 must look like the mirror image of R1
  (R2 gains where R1 loses and vice versa) for the mechanism to be believed.
  Engine-level %/month and DD<=20% criteria are NOT scored at this screen
  (w*y units); only if PROMISING does the leader decide on a 4-phase engine
  follow-up (do NOT run the engine here).
- Descriptives (5 years, pooled + per year): share of fills with n_fill >= 1;
  distribution of rel (counts/share in rel>+0.5 / |rel|<=0.5 / rel<-0.5, plus
  quantiles); mean y1.0 by rel tercile per year (terciles cut on the pooled
  rel distribution, applied per year; n_fill>=1 fills only); mismatch rate
  n_fill vs |F| (log-vs-simple sliver).

## Protocol / resources (fixed)

- PLAN.md written before any outcome computation. Then scripts: `core.py`
  (pure-numpy core: n vector, B1 size, D0-from-fill exit, rel/tilt helpers,
  no I/O), `compute_relflush.py` (per-coin loop over 4 phases, rel join,
  per-arm ledgers -> results.json, panel.parquet). Outputs: results.json,
  REPORT.md (tables + verdict). Tests: tests/test_oc_relflush.py (synthetic
  hand checks + causality: fill uses only m-1 closes; sigma excludes the bar;
  rel uses only minute f-1 closes; strict thresholds; NaN fallbacks; same
  membership all arms; R2 mirrors R1; R3 clip bounds).
- One process, one coin's H/L in RAM at a time; all-five-coins 1m O/C held as
  float32 arrays; RAM < 3 GB. Heavy run through the shared semaphore
  (scripts/heavy_slot.py, never --leader).
- Market data up to 2026-09-24 00:00 UTC is read per the assignment (all 5
  years are research data; any PROMISING result needs prospective validation
  before real money). Disclosed against RULES.md 2 / VF_COMMON hidden-year
  conventions. No commits; no edits outside research/tournament/oc_relflush/
  (+ tests/test_oc_relflush.py). Scratch only under research/tournament/
  oc_relflush/tmp/.

## Post-hoc log

- (none yet; filled only if definitions change after outcomes are seen)
