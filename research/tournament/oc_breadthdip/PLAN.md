# oc_breadthdip PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

Implements idea #64 EXACTLY as described in
`docs/opencode/OPENCODE_W_oc_breadthdip.md`. This PLAN is written before any
breadth-gated outcome is computed. Single fixed rule, no fitted parameter.

## Hypothesis (fixed here; same as oc_breadthbook, from oc_grindsignal)

`research/tournament/oc_grindsignal` finds the SOLE repeat extreme across the
4 big DD-episode starts is breadth pinned at 1.0 (E0/E2/E3 at the maximum,
E1 at 0.8; breadth 1.0 holds on 23.3% of grid bars; binomial p ~ 4% under
independence): drawdowns begin from fully extended bull-market tops, never
from weakness. Dip TP-share also runs hot (~88th pct) at those tops.
Pre-registered direction: when every major is extended (breadth = 1.0),
chasing dips adds late-cycle fills, so trimming dip rung sizes x0.8 cuts the
dip path's max drawdown at small yearly-P&L cost (most fills fall outside
breadth-on bars).

## Inputs (read-only, never edited)

- 1m klines: `data/raw/btc_intraday_20260924` (BTC),
  `data/raw/majors_intraday_20260924` (ETH/SOL/BNB/XRP). Minutes used:
  t < 2026-09-24 00:00 UTC. Missing minutes (NaN) never fill, never trigger
  an exit touch, and never count as flushing.
- Hourly bars for breadth only: `research/tournament/ext/hourly_ext.parquet`
  (hourly OHLC 35 coins, 2020-08-01 .. 2026-09-23 23:00 open). Majors only.
- Rung replica: `research/tournament/oc_b1deeper` code (B1 sizes; D0 exits),
  copied verbatim into this folder (`breadthdip.py` core). No parameter change.
- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- Rungs k in {2.5, 3.0, 3.5, 4.0, 5.0} (R2 depths, = oc_b1deeper RUNGS).
- Market data up to 2026-09-24 00:00 UTC is read per the assignment (all five
  years are research data; any PROMISING result needs prospective validation
  before real money). Disclosed against RULES.md 2 / VF_COMMON hidden-year
  conventions.
- Resources: one process, one coin's full H/L in RAM at a time (float32);
  all-five-coins 1m opens/closes held as float32 arrays for the n detector;
  hourly closes for breadth (< 50 MB); RAM < 3 GB.

## Exact causal definitions (frozen)

1. Bars: standard 4h grid, bar j covers [START + 4h*j, START + 4h*j + 4h) with
   START = 2020-08-01 00:00 UTC. Only bars with open T in
   [2021-09-24 00:00, 2026-09-24 00:00) UTC are traded (5 anchor years
   Y0..Y4 = [anchor, anchor+365d), anchors 2021-09-24..2025-09-24, keyed by
   the BAR OPEN T; a fill belongs to the year of its bar open).
2. Bar open: O_c(T) = 1m `open` of coin c at minute T (no ffill; NaN =
   missing). sigma_4h(c,T): simple returns r_b = O_b/O_{b-1} - 1 of 4h bar
   opens; sigma = std(r over 360 bars ending at T-1, min_periods 120,
   ddof=1) = v293/oc_dipexit/oc_b1deeper definition. Known at the bar open T.
   Bars with non-finite O, sg <= 0 or NaN are skipped (no rungs that bar).
3. Base rung level: lv(a,T,k) = O_a(T) * (1 - k*sg_a(T)).
4. Correlation count at minute m (live window offsets 16..238 inclusive,
   oc_b1deeper-exact): n(a,T,m) = number of OTHER majors b != a with
   finite O_b(T), finite C_b(T+m-1), finite sg_b(T) > 0 AND
   C_b(T+m-1) <= O_b(T) * (1 - 2.5*sg_b(T)). C uses the 1m `close` at
   minute T+m-1 (last fully closed minute; no cross-bar ffill, within-bar
   NaN stays NaN = not flushing). Own coin never counted (0..4). Flush at
   exactly 2.5 sigma counts (<=).
5. BASE (B1, oc_b1deeper arm (a) verbatim): resting limit BUY at lv, live
   offsets 16..238. Fill at FIRST offset f with low(T+f) < lv (STRICT
   trade-through). Fill price = lv. n_fill = n(a,T,f). Size w_base =
   1/(1+n_fill). Post-fill exits = D0 replica from the ACTUAL fill price px
   (= lv here): sl = px*(1-4*sg), bl = px*(1-8*sg), tp = px*(1+1.0*sg).
   Evaluated on minutes t in f+1..239 then timeout at 240 (next-bar open
   o2 = 1m open at T+240): backstop touch (first t with low(t) <= bl) exits
   at min(bl,open(t)) taker; else TP touch (first t with high(t) > tp,
   STRICT) exits at tp maker; else close5 stop (clock minutes m with
   (m+1)%5==0, first m with close(m) <= sl) exits at open(m+1) (or o2 if
   m=239) taker; else timeout at o2 taker + funding 0.0001 if (T+4h).hour in
   (0,8,16). Priority stop-first: backstop wins ties (kb<=ks and kb<=kt);
   else TP wins only if strictly earlier (kt<ks); else stop; else timeout.
   A stop and TP in the same minute -> stop wins. Fees: fill maker 0.0002;
   TP leg maker 0.0002 (total 2*maker on TP); stop/backstop/time legs taker
   0.00055. Net returns are fractions of px. Fills whose exit price is
   missing (NaN open, NaN o2 on a stop-at-239/timeout path) give NaN net and
   are DROPPED (same arm treatment for both arms).
6. BREADTH at the bar open T (new; causal; hourly only):
   - Daily close D_c(M) for midnight M (UTC) = `close` of the hourly bar
     with open t = M - 1h. NaN if that hourly bar is absent/NaN.
   - SMA200_c(M) = mean of D_c over the 200 midnights M-200d..M-1d (200
     values strictly before M). NaN unless all 200 daily closes are finite.
   - Coin-up_c(M) = 1 iff D_c(M) and SMA200_c(M) are both finite AND
     D_c(M) > SMA200_c(M) STRICTLY (equal is not up); else 0 (NaN inputs
     give 0 for the coin but mark breadth NaN per below).
   - M(T) = last midnight <= T (floor; if T is exactly 00:00, M(T) = T: the
     daily close ending at T is known at T). breadth(T) = (1/5)*sum_c
     coin-up_c(M(T)); breadth(T) = NaN unless all 5 majors have finite D
     and finite SMA200 at M(T). breadth_on(T) iff breadth(T) == 1.0 exactly
     (all five up); NaN -> OFF (unchanged sizes).
   - Causality: D(M) uses the hourly bar ending at M <= T; SMA200 uses only
     earlier days. No 1m, funding, or future data. Strictly known at T.
7. RULE arm: IDENTICAL fills, fill prices, nets, and exit dates as BASE (no
   re-timing, no extra/missed fills); only the weight changes:
   w_rule = w_base * 0.8 iff breadth_on(T), else w_base.
   (0.8 is the assignment-fixed constant; no fit.)
8. Aggregation (NO renormalisation — primary): per (arm, year Yi = bar-open
   year), daily sums group w*y by EXIT date (calendar UTC date of T+x, x =
   exit offset, 240 = next-bar open date). Yearly sum S = sum of daily sums.
   Worst day W = min daily sum. Cumulative path over exit dates sorted
   ascending from 0: C_k = cumsum; maxDD = max(0, max_{p<q}(C_p-C_q)) in w*y
   units (0 when monotone non-decreasing). Win rate = fraction of kept fills
   with y > 0 strictly (equal-weight, descriptive). Breadth-on share (per
   year + full): fill share = #{base fills with breadth_on}/n_base; bar
   share = #{traded bars with breadth_on}/#{traded bars}; weight share =
   sum(w_base over breadth_on fills)/sum(w_base).
   Full-path stats pool all 5 years the same way (exit-date daily sums).

## Decision rule (fixed, from the assignment)

Per anchor year Y0..Y4: S_base(Y), S_rule(Y), DD_base(Y), DD_rule(Y).
PASS_dd(Y) iff DD_rule(Y) <= DD_base(Y) (not worse; equal passes; NaN -> FAIL).
PASS_sum(Y) iff (S_base(Y) > 0 and S_rule(Y) >= 0.95*S_base(Y)) OR
(S_base(Y) <= 0 and S_rule(Y) >= S_base(Y)) (equal passes; NaN -> FAIL).
PROMISING iff (a) PASS_dd in >= 4 of 5 years AND (b) PASS_sum in >= 4 of 5
years. Otherwise NOT PROMISING. One-line verdict in REPORT.md. Descriptive
only: fills, win rate, raw sums, worst days, full-path sums/DD, breadth-on
shares.

## Protocol (fixed)

- PLAN.md written before any outcome computation. Then scripts:
  `breadthdip.py` (pure-numpy core: verbatim oc_b1deeper n/size/fill/D0 +
  breadth helper on hourly daily closes), `run_breadthdip.py` (per-coin loop,
  breadth series precomputed from hourly_ext, per-arm exit-day sums ->
  results.json). Outputs: results.json, REPORT.md (tables + one-line
  verdict). Tests: `tests/test_oc_breadthdip.py` (synthetic hand checks:
  breadth strict-gt/equal/NaN/midnight-floor/causality, 0.8 scaling, DD/sum
  helpers, fill strictness; plus file/column checks on hourly_ext).
- No commits; no edits outside research/tournament/oc_breadthdip/
  (+ tests/test_oc_breadthdip.py).

## Post-hoc log

- (none yet; filled only if definitions change after outcomes are seen)
