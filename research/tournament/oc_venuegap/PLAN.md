# oc_venuegap PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

Diagnostic, no selection. Question: the S5 "Bybit prices" friction row costs
the deployment pick ~0.4-0.5 %/month vs Binance prices (v411/v421 ROBUST.md).
Find where that gap lives in the dip ladder.

## Hypothesis (fixed here, diagnostic only)

The venue gap concentrates in a subset of coins / R2 depths, carried by
(1) fills that one venue touches and the other does not (rung-level shift
via the 4h-open difference + intrabar wick differences), and (2) different
TP/stop/time exit splits on the rungs both venues fill. No directional
pre-claim about which coin; the script measures it.

## Data (fixed here, all in repo - no fetch)

- Binance 1m: `data/raw/btc_intraday_20260924` (BTC),
  `data/raw/majors_intraday_20260924` (ETH/SOL/BNB/XRP).
- Bybit 1m (the S5 store, see
  `research/parallel/rounds/parallel-20260906-r2/v411_audit/robust_v411.py`
  `BYBIT_DIR = data/raw/bybit_linear_1m_20261004`, `bybit_minutes()`):
  `{SYM}_1m.parquet` with `open_time` in ms epoch, `open/high/low/close`.
  Coverage: BTC/ETH/XRP from 2021-06-01, BNB from 2021-06-29, SOL from
  2021-10-15 (manifest.json); S5 runs from 2021-11-15, so every major is
  covered at the comparison start.
- Minutes used: t < 2026-09-24 00:00 UTC on BOTH venues (hard cap; Bybit file
  runs to 2026-10-03 but rows >= the cap are never loaded into a comparison).
- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- Rungs k in {2.5, 3.0, 3.5, 4.0, 5.0} (R2 depths, B1 replica).
- Bars: standard 4h grid, bar j covers [START + 4h*j, START + 4h*j + 4h) with
  START = 2020-08-01 00:00 UTC. Only bars with open T in
  [2021-11-15 00:00, 2026-09-24 00:00) UTC are compared (the S5 overlap
  window; anchor years Y0..Y4 = [anchor, anchor+365d), anchors 2021-09-24..
  2025-09-24, keyed by bar open T; Y0 is a short window from 2021-11-15 and
  is labelled as such).
- All five years are research data; any finding needs prospective validation
  before real money (disclosed vs RULES.md hidden-year rule).
- Resources: one process; all-five-coins 1m opens/closes held as float32
  arrays for the venue-native n detector (same pattern as oc_b1deeper
  run.py, peak ~0.4 GB); H/L of ONE coin at a time; RAM < 3 GB.

## Exact causal definitions (frozen; B1 replica per venue, venue-native)

Per venue V in {binance, bybit}, per coin a, per bar open T, per depth k:

1. Bar open: O^V_c(T) = 1m `open` of venue V, coin c at minute T (no ffill;
   NaN = missing). sigma^V_4h(c,T): simple returns r_b = O_b/O_{b-1} - 1 of
   that venue's 4h bar opens; sigma = std(r over 360 bars ending at T-1,
   min_periods 120, ddof=1) = v293/oc_dipexit/oc_b1deeper definition. Known
   at the bar open T. Bars with non-finite O, sg <= 0 or NaN are skipped on
   that venue (no rungs that bar on that venue). Sigma needs pre-window
   history: Bybit history starts 2021-06/10, so early-T bars may skip on
   Bybit while Binance trades them (reported as coverage, not fills).
2. Rung level (venue-native): lv^V(a,T,k) = O^V_a(T) * (1 - k*sg^V_a(T)).
3. Correlation count at minute m (live offsets 16..238 inclusive, same as
   oc_b1deeper/B1): n^V(a,T,m) = number of OTHER majors b != a with finite
   O^V_b(T), finite C^V_b(T+m-1), finite sg^V_b(T) > 0 AND
   C^V_b(T+m-1) <= O^V_b(T) * (1 - 2.5*sg^V_b(T)), venue-native closes.
   Own coin never counted (0..4). Flush at exactly 2.5 sigma counts (<=).
4. B1 fill per venue: resting limit BUY at lv^V, live offsets 16..238. Fill
   at FIRST offset f^V with low^V(T+f^V) < lv^V (STRICT trade-through). Fill
   price = lv^V. n_fill^V = n^V(a,T,f^V). size_mult^V = 1/(1+n_fill^V) (B1).
   Fill uses only minute-m low vs the level known at T (causal).
5. Post-fill exits per venue (long), oc_b1deeper D0 replica from the ACTUAL
   fill price px^V = lv^V: sl = px*(1-4*sg^V), bl = px*(1-8*sg^V),
   tp = px*(1+1.0*sg^V), sg^V = sg^V_a(T). Evaluated on that venue's minutes
   t in f^V+1..239 then timeout at 240 (next-bar open o2^V = 1m open at
   T+240 on that venue): backstop touch (first t with low(t) <= bl) exits at
   min(bl,open(t)) taker; else TP touch (first t with high(t) > tp, STRICT)
   exits at tp maker; else close5 stop (clock minutes m with (m+1)%5==0,
   first m with close(m) <= sl) exits at open(m+1) (or o2 if m=239) taker;
   else timeout at o2 taker + funding 0.0001 if (T+4h).hour in (0,8,16).
   Priority stop-first: backstop wins ties (kb<=ks and kb<=kt); else TP wins
   only if strictly earlier (kt<ks); else stop; else timeout. Stop and TP in
   the same minute -> stop wins. Fees: fill maker 0.0002; TP leg maker
   0.0002 (total 2*maker on TP); stop/backstop/time legs taker 0.00055.
   Net returns are fractions of px^V. Fills whose exit price is missing
   (NaN open, NaN o2 on a stop-at-239/timeout path) give NaN net and are
   DROPPED on that venue (reported).
6. Pairing: the unit is (coin a, bar T, depth k) tradeable on at least one
   venue. Classes per rung: both-fill / binance-only / bybit-only / neither
   (neither counted for the denominator). Only bars tradeable on BOTH venues
   (finite O/sg/lv on both) enter the paired denominator; bars skipped on
   exactly one venue are reported as coverage asymmetry, not fill gaps.
7. Trade-through depth at the fill minute (per filled rung, that venue):
   d^V = (lv^V - low^V(T+f^V)) / lv^V in bps (strictly > 0 by construction).
   Mean d per (coin, depth, venue) + paired difference on both-fill rungs
   (d_bin - d_byb).
8. Open/level shift per paired bar: o_diff = (O_byb - O_bin)/O_bin in bps;
   lv_diff = (lv_byb - lv_bin)/lv_bin in bps per depth (same O ratio scaled
   by the venue sg difference). Reported as median/p90 per coin (all paired
   bars) to show how much of the fill gap is a mechanical level shift.
9. P&L per fill: net y^V (fraction of px^V, after fees/funding above).
   Yearly attribution by EXIT date (calendar UTC date of T+x, x = exit
   offset, 240 = next-bar open date). PRIMARY yearly P&L per
   (coin, depth, venue) = equal-weight sum S = sum(y) over kept fills; side
   row size-weighted S_w = sum(w*y), w = size_mult^V. Venue gap per
   (coin, depth, year) = S_bin - S_byb (positive = Binance earns more).
   Yearly totals aggregate over coins/depths. No renormalisation (this is a
   gap attribution, not an allocation test).
10. TP-hit comparison: TP rate per (coin, depth, venue) = share of kept
    fills exiting `tp`; paired exit-agreement on both-fill rungs
    (both-TP / bin-only-TP / byb-only-TP / neither-TP).

## Decision rule (fixed: DIAGNOSTIC, no PROMISING rule)

No PROMISING/NOT-PROMISING verdict (the assignment marks this DIAGNOSTIC, so
the default >=4/5 same-sign + >=4/5 leave-one-year-out rule does NOT apply).
The REPORT answers in plain words: (a) per-coin x depth table of fill-count
gap, trade-through depth gap, TP-hit gap, P&L gap per year; (b) the 4h-open
shift table; (c) which coins/rungs carry the venue gap; (d) whether routing
that subset to Binance (if the user had an account) would recover the
~0.4-0.5 %/month S5 drag, with the arithmetic shown. One-line verdict = the
(d) sentence.

## Protocol (fixed)

- PLAN.md written before any outcome computation. Then scripts: `venue.py`
  (pure-numpy core: n vector, static-level fill, D0-from-fill exit - B1
  copy), `run.py` (per-coin loop, venue-native bars/sigmas, paired ledger
  -> results.json). Outputs: results.json, REPORT.md (tables + one-line
  verdict). Tests: `tests/test_oc_venuegap.py` (synthetic hand checks +
  causality: fill uses strict low<level, sigma excludes the bar, Bybit cap
  at 2026-09-24, S5 start/overlap respected).
- No commits; no edits outside research/tournament/oc_venuegap/
  (+ tests/test_oc_venuegap.py).
