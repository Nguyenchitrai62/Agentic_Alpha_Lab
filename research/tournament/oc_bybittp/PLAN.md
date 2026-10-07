# oc_bybittp PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

Diagnostic, no selection. Follow-up to oc_bookvenue + oc_venuegap.
oc_bookvenue (deployment R2B1D17BF engine) finds the S5 Bybit-vs-Binance drag
rides the dip ladder: fewer Bybit TPs (TP rate -0.4/-0.6pp, -34/-59 TPs
across phases s0/s2). oc_venuegap's static-B1 replica finds dip rungs almost
venue-insensitive (total gap only +0.52 rung-y units, TP 55.8/55.8%).
This study zooms into the B1-replica TP divergence itself: for every rung
whose TP fills on one venue and not the other, how far away was the other
venue's tape, and what did the miss become.

## Hypothesis (fixed here, diagnostic only)

Divergent-TP rungs are near-misses: the non-TP venue's high comes within a
few bps of its own TP level, and the miss later exits as timeout (not stop).
If so, a TP placed a few bps inside the level would recover most Bybit
misses at a small per-TP cost on Binance. No directional pre-claim about
which coin or which offset (1/2/3/5 bps); the script measures it. Any offset
is a HYPOTHESIS for a later pre-registered test only — nothing here changes
a rule.

## Data (fixed here, all in repo - no fetch)

- Binance 1m: `data/raw/btc_intraday_20260924` (BTC),
  `data/raw/majors_intraday_20260924` (ETH/SOL/BNB/XRP).
- Bybit 1m (the S5 store, see
  `research/parallel/rounds/parallel-20260906-r2/v411_audit/robust_v411.py`
  `BYBIT_DIR = data/raw/bybit_linear_1m_20261004`, `bybit_minutes()`, same as
  oc_venuegap): `{SYM}_1m.parquet` with `open_time` in ms epoch,
  `open/high/low/close`. Coverage BTC/ETH/XRP from 2021-06-01, BNB from
  2021-06-29, SOL from 2021-10-15 (manifest.json).
- Minutes used: t < 2026-09-24 00:00 UTC on BOTH venues (hard cap; Bybit file
  runs to 2026-10-03 but rows >= the cap are never compared).
- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- Rungs k in {2.5, 3.0, 3.5, 4.0, 5.0} (R2 depths, oc_b1deeper replica).
- Bars: standard 4h grid, bar j covers [START + 4h*j, START + 4h*j + 4h) with
  START = 2020-08-01 00:00 UTC. Only bars with open T in
  [2021-11-15 00:00, 2026-09-24 00:00) UTC are compared (the S5 overlap
  window; anchor years Y0..Y4 = [anchor, anchor+365d), anchors 2021-09-24..
  2025-09-24, keyed by EXIT date; Y0 is a short window from 2021-11-15 and is
  labelled as such).
- Market data up to 2026-09-24 00:00 UTC is read per the assignment (all five
  years are research data; any finding needs prospective validation before
  real money; disclosed vs RULES.md hidden-year rule).
- Resources: one process; all-five-coins 1m opens/closes per venue held as
  float32 arrays for the venue-native n detector (oc_b1deeper pattern);
  H/L of ONE coin x TWO venues at a time; RAM < 3 GB.

## Exact causal definitions (frozen; oc_b1deeper B1 replica per venue)

Per venue V in {binance, bybit}, per coin a, per bar open T, per depth k:

1. Bar open: O^V_c(T) = 1m `open` of venue V, coin c at minute T (no ffill;
   NaN = missing). sigma^V_4h(c,T): simple returns r_b = O_b/O_{b-1} - 1 of
   that venue's 4h bar opens; sigma = std(r over 360 bars ending at T-1,
   min_periods 120, ddof=1) = v293/oc_dipexit/oc_b1deeper definition. Known
   at the bar open T. Bars with non-finite O, sg <= 0 or NaN are skipped on
   that venue (no rungs that bar on that venue).
2. Rung level (venue-native): lv^V(a,T,k) = O^V_a(T) * (1 - k*sg^V_a(T)).
3. Correlation count at minute m (live offsets 16..238 inclusive, same as
   oc_b1deeper B1): n^V(a,T,m) = number of OTHER majors b != a with finite
   O^V_b(T), finite C^V_b(T+m-1), finite sg^V_b(T) > 0 AND
   C^V_b(T+m-1) <= O^V_b(T) * (1 - 2.5*sg^V_b(T)), venue-native closes.
   Own coin never counted (0..4). Flush at exactly 2.5 sigma counts (<=).
   (n is recorded for the ledger; exits do not depend on it.)
4. B1 fill per venue: resting limit BUY at lv^V, live offsets 16..238. Fill
   at FIRST offset f^V with low^V(T+f^V) < lv^V (STRICT trade-through). Fill
   price = lv^V. Size w^V = 1/(1+n_fill^V) recorded as side info only.
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
   venue. PRIMARY set = both-fill rungs with both exits kept (finite net on
   both venues). Classes: both-TP / bin-only-TP / byb-only-TP / neither-TP.
   Single-venue fills with a TP are counted separately (fill-gap TPs) and do
   NOT enter the near-miss denominator.
7. Near-miss distance (per divergent both-fill rung, measured on the NON-TP
   venue U with its OWN tape and its OWN tp^U): let Hmax^U = max high over
   minutes f^U+1..239 (NaN-skipped; -inf when all NaN -> miss = NaN,
   reported). miss_bps^U = (tp^U - Hmax^U)/tp^U * 1e4. Positive = shortfall
   (high never reached TP); negative = high DID exceed TP but the exit was
   stop-first (backstop at kb <= kt, tie or earlier). Distribution per coin
   (pooled over depths and years): n, median/p25/p75/p90, mean, share with
   miss <= {1,2,3,5,10,25} bps, share negative. Exit-split of the non-TP side
   (stop/backstop/time shares) per coin, plus per-year counts.
8. TP-inside offsets (hypothesis arithmetic only, exact replay): for
   d in {1,2,3,5} bps, tp(d)^V = tp^V * (1 - d/1e4); sl/bl unchanged; exits
   re-evaluated with the SAME priority/fees/funding on each venue's OWN
   tape (causal: tighter TP is known at fill). Report per coin and overall:
   (a) Bybit recovery: of bin-only-TP rungs, share where Bybit exit becomes
   `tp` under tp(d) (recovered), and the residual miss count; (b) Binance
   cost: of Binance base-TP rungs, share still `tp` under tp(d) plus the
   mean net-return shave in bps (ret(d)-ret(0), negative = cost) over rungs
   that stay TP; (c) Binance side effect: of Binance base-non-TP rungs,
   share converting to `tp` under tp(d) (symmetric bonus, so the Bybit gain
   is not overstated as venue-specific). Also report the same recovery in
   the byb-only-TP direction as a symmetry row.
9. P&L context (side rows only): equal-weight sums S = sum(y) per venue and
   the gap, by year and overall, to anchor the TP counts to oc_venuegap
   scale. No renormalisation.

## Decision rule (fixed: DIAGNOSTIC, no PROMISING rule)

No PROMISING/NOT-PROMISING verdict (the assignment marks this DIAGNOSTIC, so
the default >=4/5 same-sign + >=4/5 leave-one-year-out rule does NOT apply).
The REPORT answers: (a) per-coin near-miss distance distribution for
bin-only-TP rungs (and the symmetric byb-only-TP row); (b) what each miss
became (timeout/stop/backstop split); (c) per-coin x offset recovery table
for Bybit plus the Binance per-TP cost and Binance conversion side row;
(d) which single TP-inside offset best trades Bybit recovery against Binance
cost — as a HYPOTHESIS for a later pre-registered test only. One-line
verdict = the (d) sentence.

## Protocol (fixed)

- PLAN.md written before any outcome computation. Then scripts: `core.py`
  (pure-numpy: n vector, static-level fill, D0-from-fill exit with a
  tp-scale hook, max-high miss — oc_b1deeper/oc_venuegap copy), `run.py`
  (per-coin loop, venue-native bars/sigmas, paired ledger + near-miss +
  offset replay -> results.json). Outputs: results.json, REPORT.md (tables
  + one-line verdict). Tests: `tests/test_oc_bybittp.py` (synthetic hand
  checks + causality: strict fill, sigma excludes the bar, stop-first tie,
  miss sign, tighter-TP monotonic recovery, Bybit cap, overlap start).
- No commits; no edits outside research/tournament/oc_bybittp/
  (+ tests/test_oc_bybittp.py).
