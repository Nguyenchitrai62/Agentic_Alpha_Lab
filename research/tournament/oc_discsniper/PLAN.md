# oc_discsniper PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

Idea #75 (docs/opencode/IDEAS2_20261006.md idea 6): spot-perp DISCOUNT sniper.

## Hypothesis (fixed here)

A deep perp discount to the spot index (premium < 0) reflects perp-only forced
selling and should mean-revert. Buying that discount as a short-hold perp-long
sleeve with exit at premium recovery harvests a mechanical snapback through a
trigger (premium z) and a holding (minutes to 4h) distinct from the sigma-depth
dip ladder. Direction pre-registered: the sleeve has positive 4-phase-mean sum
in >= 4/5 years, beats seeded placebo (>= p95) and is uncorrelated with the dip
sleeve (corr < 0.5). Single fixed rule, no fitted parameters (z = -2 only).

## Inputs (fixed here, read-only, never edited)

- Premium-index klines: `data/raw/binance_premium_20260928/*_premium_1m.parquet`
  (1m granularity verified: open_time 1-min cadence, columns
  open/high/low/close as premium fractions; ~3.53M rows/coin from 2020-01-01).
  15-min mean premium is built from the 1m `close` (see below). No fetch.
- Perp 1m klines: `data/raw/btc_intraday_20260924` (BTC),
  `data/raw/majors_intraday_20260924` (ETH/SOL/BNB/XRP), columns
  open/high/low/close. Minutes used: t < 2026-09-24 00:00 UTC. NaN minutes
  never fill, never trigger an exit touch, never count in premium means
  (a 15-min window with any non-finite close is NaN).
- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- Market data up to 2026-09-24 00:00 UTC is read per the assignment (all five
  years are research data; any PROMISING result needs prospective validation
  before real money). Disclosed against RULES.md 2 / VF_COMMON hidden-year
  conventions (this assignment explicitly overrides the old 2025-09-24 cut).
- Resources: one process, one coin's full 1m OHLC in RAM at a time (float32);
  premium closes held as float32; 4-phase loop sequential; RAM < 3 GB.
  The compute run is wrapped with `scripts/heavy_slot.py run`.

## Grids and years (frozen)

- START = 2020-08-01 00:00 UTC. Phases p in {0,1,2,3}: bar starts
  T_{p,j} = START + p hours + 4h*j. Each phase is scored alone; the
  4-phase mean per year is primary.
- Traded bars: T in [2021-09-24 00:00, 2026-09-24 00:00) UTC (keyed by T).
- Anchors A_k = 2021-09-24 .. 2025-09-24 UTC. Years Y_k = [A_k, A_{k+1}) for
  k = 0..3, Y_4 = [A_4, A_4+365d) == [A_4, CUTOFF). Year attribution is by
  ENTRY bar T (exits at T+240 may spill a day over the boundary but stay in
  the entry year, same as oc_b1deeper).
- CUTOFF = 2026-09-24 00:00 UTC. Bars needing O(T+240) past CUTOFF are
  skipped (no forward open). 1m/premium minutes at/after CUTOFF are never
  used (reindexed grid ends at CUTOFF, exit minute 240 uses the open AT
  CUTOFF which exists as the last index row; bars with T+240 > CUTOFF are
  skipped so no exit needs data past CUTOFF).

## Exact causal definitions (frozen)

1. Minute grid: full 1-min UTC index from START to CUTOFF inclusive
   (CUTOFF row exists for timeout opens). O/H/L/C per coin from 1m klines
   (no ffill; missing = NaN). Premium close P_c(m) per coin from
   premium-index 1m `close` (no ffill; missing = NaN).
2. 15-min mean premium: p15_c(m) = mean(P_c(m-14..m)) (15 closes, all must be
   finite else NaN). Causal per minute (uses closes up to m only).
3. Discount z at bar T (strictly before T): let i = index of minute T.
   cur = p15_c(i-1) (uses premium minutes T-15..T-1). trailing = p15_c values
   at minutes [i-1441, i-1) = [T-1441min, T-2min] (1440 overlapping 15-min
   means, all strictly before T, current excluded by slicing before i-1).
   mean24 = nanmean(trailing) (need >= 1200 finite else NaN);
   std24 = nanstd(trailing, ddof=1) (need finite and > 0 else NaN).
   z_c(T) = (cur - mean24) / std24. NaN when cur NaN, short history, or
   std <= 0 / non-finite. Uses only premium closes at minutes < T.
4. sigma_4h(c,T,p): per coin per phase, bar opens Ob = 1m `open` at phase bar
   starts. Simple returns r_b = Ob_b/Ob_{b-1} - 1; sigma = std(r over 360
   bars ending at T-1, min_periods 120, ddof=1) = v293/oc_b1deeper
   definition, shift(1). Known at T. Bars with non-finite O(T), sg <= 0 or
   NaN are skipped (no trigger that bar).
5. TRIGGER (fixed, one parameter): at bar T, coin c, if z_c(T) finite and
   z_c(T) < -2.0 (strict) and sigma valid and O_c(T) finite > 0, place ONE
   perp BUY limit at lim = O_c(T) * (1 - 0.001) (10 bps below minute-0
   price). No other trigger, no re-entry inside the bar.
6. FILL (executable, minute-5 rule): live offsets m = 5..59 inclusive
   (valid 60 min: minutes T..T+60 exclusive; first 5 min banned for the
   pipeline). Fill at FIRST m with low(T+m) < lim (STRICT trade-through;
   NaN low never fills). Fill price = lim. Missing O(T+m) later does not
   undo a fill. Unfilled orders expire (no trade, no market fallback).
   Fee at fill: maker 0.0002.
7. Exits (long only, from the fill minute f in 5..59, px = lim):
   sl = px * (1 - 4*sg) where sg = sigma_4h(c,T,p).
   Scan m in f+1..239 (offsets from T; 240 = next-bar open O2 = 1m open at
   T+240):
   (a) STOP (close5, market taker 0.055%): first m with (m+1)%5 == 0 (bar
       minutes; T is a multiple of 5 min for all 4 hourly-shifted phases so
       this equals the clock 5-min grid) AND close(T+m) <= sl (NaN close
       never triggers). Exit at open(T+m+1) (or O2 if m = 239) taker.
   (b) PREMIUM recovery (limit maker 0.02%): first m with p15_c(T+m) >= 0
       (STRICT >= 0; NaN never triggers; p15 uses premium closes up to
       minute T+m, exit one minute later so causal). Exit at open(T+m+1)
       (or O2 if m = 239) maker. This is a guaranteed next-minute-open
       fill at the maker fee (disclosed simplification: no limit
       trade-through is demanded on the exit; the fee marks it as limit).
   (c) TIMEOUT: at O2 = open(T+240) market taker.
   Priority stop-first: let ms = stop trigger minute or None, mp = premium
   trigger minute or None. If ms is not None and (mp is None or ms <= mp):
   stop; elif mp is not None: premium; else timeout. Same-minute tie goes
   to the stop. A stop and premium in the same minute is scored as a stop.
   Fills whose exit open is NaN give NaN net and are DROPPED (with a
   counter; same as oc_b1deeper per-arm drop rule).
8. Funding (gate): longs pay 0.0001 per 8h settlement held. Settlements at
   00:00, 08:00, 16:00 UTC. Count settlements s with T_fill < s <= T_exit
   (T_fill = T+f minutes, T_exit = T+x minutes, x in 1..240; x = 240 is
   T+240). Subtract 0.0001 * count from the net. (For a <= 4h hold the
   count is 0 or 1; timeouts at a settling open match the oc_b1deeper dip
   convention.)
9. Net return per filled trade: y = exit_px/px - 1 - fee_fill - fee_exit
   - funding, with fee_fill = 0.0002 (maker), fee_exit = 0.0002 on premium
   exits (total 2*maker) or 0.00055 on stop/timeout legs (total
   maker+taker). Fractions of px. Portfolio contribution c = 0.25 * y
   (size = 0.25 x equity per coin, majors only; no leverage, no
   compounding inside the sums).
10. Daily sums per (phase, year): group c by EXIT date (calendar UTC date of
    T+x; x = 240 uses the T+240 date). Yearly sum S = sum of daily sums
    (portfolio units; raw sum of y = S/0.25). Worst day W = min daily sum.
    Cumulative path over exit dates ascending from 0: maxDD = max drawdown
    of the cumulative path (0 when monotone non-decreasing). Win rate =
    fraction of kept fills with y > 0 strictly (equal-weight). Trades n =
    kept fills. 4-phase-mean per year: S_bar(Y) = mean_p S_{p,Y} (same for
    n/win/W/DD as descriptive means; correlation/overlap pooled below).
11. Dip reference (G2 dip sleeve, oc_b1deeper replica): exact D0-from-level
    exits (TP = lv*(1+sg), sl 4sg close5 with the same (m+1)%5 rule,
    backstop 8sg, timeout next-bar open; maker 0.0002/taker 0.00055; settle
    funding on timeout) on R2 depths k in {2.5,3.0,3.5,4.0,5.0} with live
    offsets 16..238 STRICT low < lv and B1 sizes w = 1/(1+n_fill), n =
    other majors with C(T+m-1) <= O(T)*(1-2.5*sg(T)) (v399-exact, same as
    oc_b1deeper/oc_placebo_dip). Rebuilt per phase in THIS study (same 1m
    arrays, same sigma grids) so dip daily P&L exists on all 4 phases.
    Dip daily sums use w*y grouped by exit date (renormalisation NOT
    applied; correlation is scale-free and overlap uses fills).
12. Correlation (daily P&L, disc vs dip): per (phase, exit-date) daily sums
    d_disc, d_dip (missing dates filled 0 within the 5y span). Overall r =
    Pearson over all (phase, date) pairs in [2021-09-24, 2026-09-24)
    (pooled; single number for the gate). Per-year r likewise restricted
    to exit dates in Y_k (descriptive). If either series has zero variance
    (e.g. no disc trades), r = NaN -> gate FAIL.
13. Overlap share: for each kept disc fill (coin c, fill minute Tf = T+f),
    overlapped iff EXISTS a kept dip B1 fill of the SAME coin with
    |Tf - Td| <= 240 min. Share = overlapped / n (pooled 5y for the
    report context; per (phase, year) descriptively). Dip fills include
    all 5 rungs.
14. Placebo (300 seeded rules): per (phase, year, coin) let K = number of
    REAL trigger bars (z < -2 with valid sigma/O, regardless of fill).
    Placebo rule r (r = 0..299, seed 20261006): sample K DISTINCT random
    bars WITHOUT replacement from the eligible universe of that
    (phase, year, coin) = trade bars with valid sigma and finite O(T)
    (selection uses only bar ids + seed, never returns/prices/outcomes).
    Sampling via numpy RandomState(20261006 + r) sequential without
    replacement (order: phases, years, coins; each cell draws K indices).
    Each sampled bar gets the IDENTICAL entry/exit pipeline (same
    lim formula, same 5..59 fill scan, same stop/premium/timeout race,
    same fees/funding, same 0.25 sizing, same NaN-drop rule). Real 5y
    total R = sum_Y S_bar(Y) (sum of yearly 4-phase means, portfolio
    units). Placebo totals R_r likewise. Percentile = mean_r(R_r <= R)
    * 100 (empirical CDF, 0..100). Gate needs >= 95.

## Decision rule (fixed, from the assignment)

- Primary per year: S_bar(Y) = 4-phase-mean sum of c (portfolio units).
- PROMISING only if ALL three hold: (a) S_bar(Y) > 0 (strictly) in >= 4/5
  years, AND (b) placebo percentile >= 95, AND (c) overall daily-P&L
  correlation with the dip sleeve < 0.5. Otherwise NOT PROMISING.
  One-line verdict in REPORT.md. Descriptive only: per-phase trades/win/
  sums/worst/DD, full pooled sums/DD, overlap shares, per-year r.
- The default tournament same-sign/LOYO rule is N/A by construction (fixed
  z = -2, no fitted threshold to leave out); the assignment's three-leg
  gate replaces it.

## Protocol (fixed)

- PLAN.md written before any outcome computation. Then scripts:
  `discsniper.py` (pure core: p15/z, fill scan, stop/premium/timeout race,
  D0/B1 dip replica, placebo sampler) and `run.py` (per-coin/per-phase
  loop -> fills ledgers -> results.json). Outputs: results.json,
  REPORT.md (tables + one-line verdict). Tests:
  `tests/test_oc_discsniper.py` (synthetic hand checks: z math, fill
  strictness + minute-5 ban, stop/premium priority + causality, funding
  count, placebo count-match; causality: z/sigma/limit use only minutes <
  T, premium exit uses p15 up to m with exit at m+1).
- No commits; no edits outside research/tournament/oc_discsniper/
  (+ tests/test_oc_discsniper.py).

## Post-hoc log

- (none yet; filled only if definitions change after outcomes are seen)
