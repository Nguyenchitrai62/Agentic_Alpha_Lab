# oc_qbasis PLAN (pre-registered BEFORE any outcome is computed)

Question: does the Binance quarterly-futures basis — a leverage/euphoria
proxy (high annualised basis = crowded longs) — observed strictly before T
separate good from bad outcomes for (a) the BOT book legs and (b) dip-rung
fills?

## Hypothesis (fixed here)

Euphoric basis (HIGH BTC quarterly-basis z-score at T) makes book LONGS and
dip fills worse. Expected sign is NEGATIVE for both primary spreads:
Hi-tercile mean minus Lo-tercile mean < 0. The short leg is reported
descriptively only (no signed expectation, not part of the rule).

## Data (fixed here, read-only)

- Basis: `artifacts/research/engine_real/qbasis_features_4h.parquet`
  (from `scripts/fetch_quarterly_basis.py`; public data.binance.vision;
  per coin per 4h bar: open_time, close_time, sym, qb_front = annualised
  front-delivery basis ln(F/perp)*365/DTE, qb_slope, qb_chg24, source).
  Raw delivery 1h klines live in `data/raw/qbasis_20261003/` (not loaded).
  No re-download. No 1m data is loaded.
- v351 context: `research/parallel/rounds/parallel-20260906-r2/v351/`
  (v351_quarterly_basis_member.py + v351_result.json): QB1 member beat M3 on
  dev4 but failed transfer (fold k=3 chose M3; QB1 DD 22.85 > M3 17.73).
  This study does NOT retrain members; it tests the raw regime signal.
- Books: `forward_v205.research_books_d2` rebuilt EXACTLY as
  `scripts/forward_v205.py` (same files/math as `oc_bookic/compute_bookic.py`
  and `oc_fundregime/analyze_fundregime.py`): o1 from member_A/Aq_O1_orders +
  member_B/Bq_tv, d2 = 0.8*o1 + 0.2*(D+Dq)/2, union index, missing -> 0.0;
  all from `artifacts/research/engine_real/`.
  Opens: `artifacts/research/engine_real/opens_v154.parquet`.
- Dips: `research/tournament/ext/fills_U_ext.parquet`; T = t_fill - f minutes;
  universe majors-R2 = sym in {BTC,ETH,SOL,BNB,XRP}USDT and x1 in
  {2.5,3.0,3.5,4.0,5.0}; outcome y1.0 only (exact net return, unit rung size).
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides the
  old RULES.md hidden-year cut; all five years are research data, findings
  still need prospective validation).

## Regime feature F(T) (exact, causal)

PRIMARY F(T) = BTC qb_front z-score vs trailing 90 days, using ONLY 4h rows
with close_time strictly before T:
- S(T) = BTCUSDT rows with close_time < T and qb_front non-NaN, sorted.
- v0(T) = qb_front at max close_time in S(T) (NaN if S empty).
- W(T) = qb_front values in S(T) with close_time in [T - 90d, T).
- F(T) = (v0 - mean(W)) / std(W, ddof=1) iff |W| >= 300 non-NaN and
  std(W) > 0, else NaN. Units: standard deviations.
- SECONDARY G(T) = same rule on ETHUSDT rows (descriptive tables only, same
  tercile method; NOT part of the PROMISING rule). Raw qb_front levels are
  reported as medians per tercile for context only.
- Valid span: BTC qb valid from 2020-06-11, so F(T) is valid from ~2020-09-09
  (90d warmup); covers all anchor years. No imputation, no fill-forward.
- Book bars: T = bar open_time (weight known at prior close -> causal).
  Dip rungs: T = t_fill - f minutes (4h-aligned bar open).

## Part (a) — book legs by basis tercile (exact)

- Grid: inner join of books index with opens index, sorted 4h
  (~2021-09-24 00:00 .. 2026-09-23 20:00 UTC; 2190 bars per literal anchor
  year, see below). w[t] known at the close of bar t.
- Next-bar gross P&L (no costs): pnl[t,s] = w[t,s] * (open[t+1,s]/open[t,s]-1).
  Last grid bar dropped (no forward return). Legs: long w>0, short w<0.
- Anchor years: Y_k = [A_k, A_k + 365d) on bar open_time,
  A in {2021-09-24 .. 2025-09-24} (literal +365d per assignment).
- Cut-offs q33/q67 = percentiles of F over BOOK GRID BAR TIMES t < A_k with F
  valid (strictly previous data only). Require >= 100 training times else the
  year is NaN (FAIL). Assign Lo: F <= q33, Hi: F > q67, Mid: else; NaN -> drop.
- Per year, per tercile, per leg: sum pnl (gross weight x return), n rows,
  per-row mean (bps = mean x 1e4).
- PRIMARY book effect E_book = mean_long(Hi) - mean_long(Lo) (bps). Expect < 0.
  A year counts as FAIL if < 30 long-leg rows in either Hi or Lo. Short leg:
  same table, descriptive only.

## Part (b) — dip y1.0 by basis tercile (exact)

- Same F(T); T = t_fill - f minutes per row.
- Per year: cut-offs q33/q67 = percentiles of F over DIP ROWS with T < A_k and
  F non-NaN (row-weighted; strictly previous data). Require >= 100 training
  rows else NaN (FAIL). Same Lo/Mid/Hi assignment; NaN F -> unassigned.
- Per year, per tercile: mean y1.0 (bps) + n.
- PRIMARY dip effect E_dip = mean(Hi) - mean(Lo) (bps). Expect < 0. FAIL if
  < 30 rows in either Hi or Lo.

## LOYO + decision rule (fixed here)

- LOYO: for held-out year h, training = rows of the OTHER 4 anchor years
  (book: grid bar times; dips: fill rows); cut-offs from training; spread_h =
  Hi mean - Lo mean in the held-out year (long-leg rows for books, y1.0 for
  dips). Require >= 30 rows per side else NaN (FAIL).
- DECISION (assignment rule, per primary effect): PASS iff (a) spread_year has
  the expected (negative) sign in >= 4 of 5 anchor years (NaN = fail), AND
  (b) spread_h is negative in >= 4 of 5 LOYO folds (NaN = fail).
- OVERALL verdict: PROMISING only if BOTH primaries (E_book and E_dip) PASS;
  exactly one passing = PARTIAL (not promising); none = NOT PROMISING.
- Cost context: dip y1.0 is net; book pnl is gross weight x return (before vol
  target, governor, fees, funding); round-trip cost ~4-8 bps as reference.

## Causality / alignment tests (tests/test_oc_qbasis.py)

- test_basis_strictly_before_T: 200 sampled T (bars + rungs); no qbasis row
  used has close_time >= T; truncate-all-qbasis-at-T leaves F unchanged
  (recompute on 5 sampled T).
- test_cutoffs_causal: year-k cut-offs use no time >= A_k; LOYO cut-offs for
  held-out h use no row of year h.
- test_counts: majors-R2 row count and per-year split logged; book grid bar
  count logged; qbasis BTC valid from 2020-06-11, F valid from ~2020-09-09.
- test_no_1m: analysis script never references intraday 1m / premium_1m paths.
- test_books_match_oc_fundregime: rebuilt d2 books equal oc_fundregime math
  on a sampled block (same files, same formula).

## Deliverables

research/tournament/oc_qbasis/: PLAN.md (this file),
analyze_qbasis.py, results.json, REPORT.md (tables + one-line verdict).
tests/test_oc_qbasis.py. No tuning on results; any post-hoc change logged
in REPORT.md. No commits. One process; 4h + basis + fills only (RAM << 1 GB).
