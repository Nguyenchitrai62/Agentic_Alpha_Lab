# oc_fundregime PLAN (pre-registered BEFORE any outcome is computed)

Question: does Binance settled funding — a crowding proxy (high positive
funding = crowded longs paying) — observed strictly before T separate good
from bad outcomes for (a) the BOT book legs and (b) dip-rung fills?

## Hypothesis (fixed here)

Crowded longs (HIGH cross-major 7-day funding at T) make book LONGS and dip
fills worse. Expected sign is NEGATIVE for both primary spreads:
Hi-tercile mean minus Lo-tercile mean < 0. The short leg is reported
descriptively only (no signed expectation, not part of the rule).

## Data (fixed here, read-only)

- Funding: `data/raw/binance_premium_20260928/{BTC,ETH,SOL,BNB,XRP}USDT_funding.parquet`
  (columns calc_time, funding_interval_hours, last_funding_rate; settlements at
  00/08/16 UTC; spans 2020-01..2026-08-31 16:00 UTC; manifest + sha256 in that
  folder). No 1m/premium files are loaded.
- Books: `forward_v205.research_books_d2` rebuilt EXACTLY as
  `scripts/forward_v205.py` (same files/math as `oc_bookic/compute_bookic.py`):
  o1 from member_A/Aq_O1_orders + member_B/Bq_tv, d2 = 0.8*o1 + 0.2*(D+Dq)/2,
  union index, missing -> 0.0; all from `artifacts/research/engine_real/`.
  Opens: `artifacts/research/engine_real/opens_v154.parquet`.
- Dips: `research/tournament/ext/fills_U_ext.parquet`; T = t_fill - f minutes
  (verified 4h-aligned, minute 0); universe majors-R2 = sym in
  {BTC,ETH,SOL,BNB,XRP}USDT and x1 in {2.5,3.0,3.5,4.0,5.0} (6876 rows;
  per anchor year 990/1045/1330/989/1144); outcome y1.0 only (exact net return,
  unit rung size).
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides the
  old RULES.md hidden-year cut; all five years are research data, findings
  still need prospective validation).

## Regime feature F(T) (exact, causal)

F(T) = cross-major average 7-day funding at T, using ONLY settlements
strictly before T:
- Per coin c: settlements with calc_time (UTC) in [T - 7d, T). Expected count
  is 21 (3/day x 7d). m_c(T) = mean(last_funding_rate) iff exactly 21
  settlements present, else NaN for that coin.
- F(T) = mean_c m_c(T) over the 5 majors iff all 5 are non-NaN, else NaN.
- Units: rate per 8h settlement (reported x1e4 = bps).
- Valid span: ~2020-09-21 (SOL funding starts 2020-09-13) through T < 2026-09-01
  04:00 UTC (funding files end 2026-08-31 16:00; later T has <21 settlements
  -> NaN, pairwise-dropped, coverage reported). No imputation, no fill-forward.

## Part (a) — book legs by funding tercile (exact)

- Grid: inner join of books index with opens index, sorted 4h (10950 bars,
  2021-09-24 00:00 .. 2026-09-23 20:00 UTC; 2190 bars per literal anchor year,
  see below). w[t] known at the close of bar t.
- Next-bar gross P&L (no costs): pnl[t,s] = w[t,s] * (open[t+1,s]/open[t,s]-1).
  Last grid bar dropped (no forward return). Legs: long w>0, short w<0.
- Funding at bar t: F(t), t = bar open_time (settlements strictly before the
  open; weight known at the prior close -> causal).
- Anchor years: Y_k = [A_k, A_k + 365d) on bar open_time,
  A in {2021-09-24 .. 2025-09-24} (literal +365d per assignment; the 6 bars of
  2024-09-23 fall in no year; 5y totals still include every grid bar).
- Cut-offs q33/q67 = percentiles of F over ALL 4h clock times
  (00/04/08/12/16/20 UTC) t < A_k with F valid, back to 2020-09-21 00:00 UTC
  (strictly previous data only; uniform rule for all k; every book bar time is
  one such clock time). Require >= 100 training times else the year is NaN
  (FAIL).
  Assign Lo: F <= q33, Hi: F > q67, Mid: else; NaN F -> unassigned.
- Per year, per tercile, per leg: sum pnl (gross weight x return), n rows,
  per-row mean (bps = mean x 1e4).
- PRIMARY book effect E_book = mean_long(Hi) - mean_long(Lo) (bps). Expect < 0.
  A year counts as FAIL (breaks the sign count) if < 30 long-leg rows in
  either Hi or Lo. Short leg: same table, descriptive only.

## Part (b) — dip y1.0 by funding tercile (exact)

- Same F(T); T = t_fill - f minutes per row.
- Per year: cut-offs q33/q67 = percentiles of F over DIP ROWS with T < A_k and
  F non-NaN (row-weighted; strictly previous data). Require >= 100 training
  rows else NaN (FAIL). Same Lo/Mid/Hi assignment; NaN F -> unassigned.
- Per year, per tercile: mean y1.0 (bps) + n.
- PRIMARY dip effect E_dip = mean(Hi) - mean(Lo) (bps). Expect < 0. FAIL if
  < 30 rows in either Hi or Lo.

## LOYO + decision rule (fixed here)

- LOYO: for held-out year h, training = rows of the OTHER 4 anchor years
  (book: (t,sym) rows; dips: fill rows); cut-offs from training; spread_h =
  Hi mean - Lo mean in the held-out year (long-leg rows for books, y1.0 for
  dips). Require >= 30 rows per side else NaN (FAIL).
- DECISION (assignment rule, per primary effect): PASS iff (a) spread_year has
  the expected (negative) sign in >= 4 of 5 anchor years (NaN = fail), AND
  (b) spread_h is negative in >= 4 of 5 LOYO folds (NaN = fail).
- OVERALL verdict: PROMISING only if BOTH primaries (E_book and E_dip) PASS;
  exactly one passing = PARTIAL (not promising); none = NOT PROMISING.
- Cost context: dip y1.0 is net; book pnl is gross weight x return (before vol
  target, governor, fees, funding); round-trip cost ~4-8 bps as reference.

## Causality / alignment tests (tests/test_oc_fundregime.py)

- test_funding_strictly_before_T: 200 sampled T (bars + rungs); no settlement
  used has calc_time >= T; truncate-all-funding-at-T leaves F unchanged
  (recompute on 5 sampled T).
- test_cutoffs_causal: year-k cut-offs use no time >= A_k; LOYO cut-offs for
  held-out h use no row of year h.
- test_counts: majors-R2 = 6876 rows, per-year 990/1045/1330/989/1144; book
  grid = 10950 bars (2190 per literal year); funding files span 2020-01 ..
  2026-08-31 with 3 settlements/day/coin.
- test_no_1m: analysis script never references premium_1m / intraday 1m paths.
- test_books_match_oc_bookic: rebuilt d2 books equal oc_bookic math on a
  sampled block (same files, same formula).

## Deliverables

research/tournament/oc_fundregime/: PLAN.md (this file),
analyze_fundregime.py, results.json, REPORT.md (tables + one-line verdict).
tests/test_oc_fundregime.py. No tuning on results; any post-hoc change logged
in REPORT.md. No commits. One process; 4h + funding + fills only (RAM << 1 GB).
