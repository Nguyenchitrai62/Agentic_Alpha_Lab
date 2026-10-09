# oc_presample PLAN (pre-registered BEFORE any outcome is computed, 2026-10-07)

## Purpose (labelled PRE-SAMPLE, fixed rules, no tuning)

Replay the G2 dip sleeve with FROZEN rules on Binance SPOT 1m data from
2017-08 .. 2020-08, a span no selection ever saw (all dip-sleeve rules were
chosen on 2020-08 .. 2026-09 data). Covers the 2018 bear market (-80 %),
the most dangerous regime for a long-rebound ladder. Answers one question:
was the dip sleeve profitable with DD <= 20 % in 2018 and 2019 under the
fixed rules? No parameter may be changed after seeing any pre-sample number;
any extra row is labelled post-hoc. Single fixed variant; no selection.

## Data (frozen before replay)

- Source: Binance SPOT 1m klines, public archive
  https://data.binance.vision/data/spot/monthly/klines/<SYM>/1m/<SYM>-1m-YYYY-MM.zip
  (+ .CHECKSUM, sha256 verified per zip before unzip).
- Symbols: BTCUSDT (first month 2017-08, HEAD-probed 200), ETHUSDT (2017-08),
  BNBUSDT (2017-11; 2017-10 404), XRPUSDT (2018-05; 2018-04 404).
  Range per symbol: first month available .. 2020-09 inclusive (2020-09 kept
  only so bars opening in August can time out at the September open; no rung
  is opened on a bar with open >= 2020-09-01).
- SOL: no spot data before 2020-08 -> replay uses the FOUR coins above
  (stated; B1 n counts only coins present, NaN coins never count/trigger).
- Artefacts (ONLY data/raw/spot_1m_presample_20261007/): one parquet per
  symbol with columns open_time (UTC), o, h, l, c, volume + manifest.json
  (months, rows, sha256 per zip, first/last bar, gap list). Gaps: minutes
  missing from the archive reindexed as NaN; reported per symbol (count,
  longest run, list of runs > 60 min). Missing minutes never fill, never
  trigger an exit touch, never count as flushing; a fill whose timeout open
  is NaN is dropped (NaN ret skipped), exactly as the replica.

## Replica (G2 dip sleeve, isolated, dip-only; verbatim copy of oc_crash2020)

- 4h grid: ORIGIN = 2020-01-01 00:00 UTC, bar j of phase s covers
  [ORIGIN + s h + 4h*j, +4h) for ALL integer j (negative j extends the grid
  back to 2017, so the s=0 grid is identical to oc_crash2020's grid on
  overlapping dates). Phases s in {0,1,2,3}. Bar offsets 0..239 minutes;
  next-bar open is offset 240.
- sigma_4h per coin per phase at bar j (known at the bar OPEN): simple
  returns r_b = O_b / O_{b-1} - 1 of 4h bar opens; sigma(j) = std(r over the
  360 bars ending at j-1, min_periods 120, ddof=1) = oc_dipexit/v293
  definition, i.e. crash.compute_sigma verbatim. NOTE: the assignment text
  says "log returns"; the frozen choice is the replica's simple-return
  sigma so the copy reproduces oc_crash2020 bit-for-bit (the log/simple
  difference is second-order for 4h moves). Bars with non-finite O_j or
  sigma <= 0/NaN are skipped. Warm-up: no trading before (first finite bar
  open of that coin) + 60 days; equivalently sigma needs >= 120 bars and the
  60-day rule binds first only for XRP/BNB early months (logged per coin).
- Rungs k in {2.5, 3.0, 3.5, 4.0, 5.0} (R2 depths). Level lv = O_j*(1-k*sg).
  Resting limit BUY, live window offsets 16..238 (no fill in minutes 0..15
  exactly as the replica). Fill at FIRST f with low(f) < lv (STRICT
  trade-through). Fill price = lv, maker 0.0002. At most one fill per
  (bar, coin, k).
- Correlation count at the fill (B1, v399-exact, causal, coins-present-only):
  n(a,T,f) = number of OTHER majors b (of the 4 available) with finite
  O_b(T), finite C_b(T+f-1), finite sg_b(T) > 0 AND
  C_b(T+f-1) <= O_b(T)*(1-2.5*sg_b(T)) (only closes up to minute f-1).
- Sizing (G2 wiring, agents OFF): per-rung notional as fraction of bar-open
  equity E: w = mult*kd*u, mult = 1/(1+n_fill) (B1), kd = 1.7 (G2 dial),
  u = 0.25*1.75/4/1.657 (engine constants; v221 size_mult 1.75). R2 agent
  size = 1.0 (no walk-forward tables exist pre-2020; labelled). Scale and
  governor = 1.0 (labelled).
- Risk budget (engine-exact): candidates of a bar processed in (f, r, a)
  order; keep iff risk_open + w*(4*sg+gap) <= 0.442 (= 0.26*1.7), gap = 0.02;
  risk_open sums w*(4*sg+gap) of rungs still open (exit offset > f).
- Arm: G2 ONLY (budget + gross cap G = 2.0 per phase sub-account:
  room = 2.0 - sum of open notionals; w = min(w, room); skip if
  room <= 1e-12). NOCAP is NOT re-run (oc_crash2020 showed G2 == NOCAP
  bit-for-bit in all 40 cells; labelled).
- Post-fill exits (long), oc_dipexit D0 replica from lv:
  sl = lv*(1-4*sg), bl = lv*(1-8*sg), tp = lv*(1+1*sg), evaluated on
  t in f+1..239 then timeout at 240: backstop touch (first low <= bl) exits
  at min(bl, open(t)) taker; else TP touch (first high > tp, STRICT) exits
  at tp maker+mfill; else close5 stop (clock (m+1)%5 == 0, first close <= sl)
  exits at open(m+1) (or o2 if m == 239) taker; else timeout at next-bar
  open o2 taker + funding 0.0001 iff (T+4h).hour in (0,8,16). Priority
  stop-first (backstop wins ties kb <= ks, kt; else TP only if kt < ks;
  else stop). Same-minute stop+TP -> stop. Gate fees: maker 0.0002,
  taker 0.00055. Ret fractions of lv. NaN exit price -> rung dropped.
- Spot-vs-perp caveat (labelled on every table): fills/exits are evaluated
  on SPOT prices while fees/funding are the perp gate costs
  (maker 0.0002 / taker 0.00055, longs pay 0.0001 per 8h settlement held,
  shorts n/a - dip sleeve is long-only).

## Years and equity (PRE-SAMPLE labelled; reference rows labelled)

- Pre-sample years (each, per phase, equity starts 1.0 flat, compounds per
  bar within the year, reset per year):
  Y2018 = 2018-01-01 .. 2018-12-31, Y2019 = 2019-01-01 .. 2019-12-31,
  Y2020p = 2020-01-01 .. 2020-08-31 (rungs opened on bars with open in the
  interval; exits may realise in the first bar of the next month).
  Y2017 = first-trading-date .. 2017-12-31 as ONE separate row (only
  BTC/ETH, BNB from its warm-up date if inside 2017; XRP absent).
- Reference rows (same code, same G2 arm, 4-phase, equity reset per year):
  R1 = 2021-09-24 .. 2022-09-23, R2 = 2022-09-24 .. 2023-09-23,
  R3 = 2023-09-24 .. 2024-09-23, R4 = 2024-09-24 .. 2025-09-23,
  R5 = 2025-09-24 .. 2026-09-23. These reuse the EXISTING perp-intraday
  1m store (data/raw/btc_intraday_20260924, data/raw/majors_intraday_20260924)
  for the reference leg only; pre-sample years use the new spot store.
  The two stores overlap 2020-01 .. 2020-08: no cross-contamination (separate
  runs, separate tables).
- Fidelity gate (BEFORE any pre-sample number is looked at): run the copied
  core on oc_crash2020 window W1 (2020-03-12, 10-day sim) from the OLD
  perp store and require bit-for-bit agreement with results.json cells
  W1_covid0312|s{0..3}|G2 (end_equity, fills, stops, checksum fields). If it
  mismatches, stop and report; no pre-sample replay.

## Metrics (per year x phase + 4-phase mean)

- Per (year, phase): %/month geometric on full equity =
  100*(E_end^(30.4375/N_days) - 1), N_days = calendar days of the year
  interval (366 for 2016-style leap coverage as applicable: 2018:365,
  2019:365, 2020p:243, 2017-partial: actual days, R-years: 365/366 per span);
  max DD % from 1m-marked equity M(t) = bar-open E*(1+sum w*(C(t)/lv-1))
  including open positions (peak-to-trough on the running peak from 1.0);
  fills, stops (close5+backstop), TPs, timeouts, win rate = fraction of fills
  with ret > 0 (after costs), worst calendar day (UTC, min of daily marked
  returns), worst minute (timestamp of min M), peak gross notional
  (start-equity units), end equity.
- 4-phase mean: arithmetic mean of the per-phase %/month, DD, win rate;
  sums for counts; min for worst minute/day reported as range. (Mean-of-mins
  is a pessimistic proxy of the true 1/4-equity mix; labelled.)
- Key question (bold in REPORT): was the dip sleeve profitable with
  DD <= 20 % in 2018 and 2019 under the fixed rules?

## Data fix disclosure (post-PLAN, pre-outcome, 2026-10-07; no outcome seen)

While packing the spot archive (BEFORE any replay number was computed) two
archive artefacts were found in the 2017-12 / 2018-01 / 2018-02 monthly files
of BTC/ETH/BNB (XRP starts 2018-05, clean):
(a) 21602 rows per symbol carry sub-minute open_time offsets (+20.799 s BTC,
+20.81 s ETH, +21.82 s BNB for the Dec-2017 chunk; +~14.8-15.8 s for a
~1201-row Feb-2018 chunk). 99.6/99.0/75.2 % of them (BTC/ETH/BNB) are REAL
klines with real prices and volume (e.g. BTC 2017-12-05: 60/60 minutes
present, all offset, real rally prices); flooring them to the minute
recovers the Dec-2017 rally instead of deleting it. Dropping them would
have created a fake 14-day December gap.
(b) A minority (BTC 81, ETH 213, BNB 5349 rows, all offset, clustered
2017-12-04 .. 2017-12-18) are flat zero-volume filler rows
(volume == 0 AND o == h == l == c, e.g. BTC 11478.0 for ~48 min on Dec-04):
the archive's backfill for dead minutes. These are dropped to NaN.
Frozen rule: floor offset rows with real content to the minute grid
(aligned row wins the single per-symbol floored/aligned collision);
drop flat zero-volume filler rows; genuine minute-aligned zero-volume
minutes are KEPT (longest aligned flat-vol0 run: 73 min, 2019-06-07).
The replay core is unchanged (no volume filter): a vol-0 carried low can
only re-touch a level an earlier real trade already touched, so any
residual effect is second-order and documented here.

## Protocol / resources

- PLAN.md written before any outcome computation (this file). Scripts live
  ONLY in research/tournament/oc_presample/: download_spot.py (fetch+verify),
  presample.py (pure-numpy core copied from crash.py + per-year driver ->
  results.json). Outputs: results.json, REPORT.md (tables + 3-line
  Vietnamese verdict), results ledger checksum. Scratch under tmp/ only.
- RAM: one coin's 1m slice per year-chunk in RAM at a time (float32);
  per-year sequential bars. If a step is expected > 0.4 GB it goes through
  scripts/heavy_slot.py (tag oc_presample, never --leader). One process.
- Tests: tests/test_oc_presample.py (synthetic hand checks: strict fill,
  stop-first, funding, budget cut, cap cut; causality: sigma excludes the
  bar, n uses only closes up to f-1; truncation: pre-sample store covers
  only bars < 2020-09-01 openings). Run with
  .venv/Scripts/python.exe -m pytest tests/test_oc_presample.py -q.
- Leakage statement (fixed-rule replay, no fitting): no parameter is fit on
  any data here; all rule constants are copied from the 2020-08..2026-09
  research window, hence pre-sample years are out-of-sample for the RULES
  (in the "no selection saw them" sense) but the rules ARE in-sample for the
  reference R-years (labelled). Feature timing (sigma/n/fill/exit),
  fit windows (none) and fill timing are checked in REPORT.md.
- No commits; no edits outside research/tournament/oc_presample/
  (+ data/raw/spot_1m_presample_20261007/, tests/test_oc_presample.py).
  Git is read-only.
