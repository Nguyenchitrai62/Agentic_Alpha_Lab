# oc_dvolbook PLAN (pre-registered BEFORE any outcome is computed)

Question: does Deribit implied volatility (DVOL) observed at a 4h bar help the
deployed BOT **book** — either as a return forecaster (IC with forward
returns) or as a context splitter (high-DVOL bars earn/lose differently)?

## Hypothesis (fixed here)

Elevated / rising implied vol and a wide DVOL-minus-realised premium at the bar
open go with different forward returns and different book P&L. The sign is read
from the data; **consistency** across anchor years is what matters. A book rule
keyed to a feature/leg is PROMISING only under the decision rule below.

## Inputs (read-only, never edited)

- DVOL: `research/tournament/oc_dvol/dvol_hourly.parquet` (BTCDVOL/ETHDVOL
  hourly closes; `t` = hour START (UTC), bar END = `t` + 1h). No refetch.
- Realised vol: `research/tournament/ext/hourly_ext.parquet` hourly closes
  (BTCUSDT/ETHUSDT; `t` = bar start UTC).
- Book: `forward_v205.research_books_d2` rebuilt EXACTLY as
  `research/tournament/oc_bookic/compute_bookic.py::research_books_d2`
  (0.8 x O1 + 0.2 x D-members/2 from `artifacts/research/engine_real/`).
- Opens: `artifacts/research/engine_real/opens_v154.parquet` (4h opens, the
  `eu.er.v154_books()` grid).
- Symbols: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides the
  old tournament-harness hidden-year cut; all five years are research data,
  findings still need prospective validation).

## Exact definitions (fixed before seeing numbers)

- Grid: inner join of the book index with the opens index (dropna), sorted 4h
  grid. `T` = bar `open_time`; weight `w[T,s]` is known at the close of bar T.
  DVOL features are additionally computed on the pre-anchor 4h grid
  [FEAT_START, A_0) (feature cut-off pool only; no weights/P&L there).
- As-of rule: a DVOL hourly bar (start `t_h`, end `t_h+1h`) is usable at T iff
  its end is **at or before** T (`t_h+1h <= T`). `asof(T)` = close of the last
  usable hourly bar. For 4h-aligned T this is the bar `[T-1h, T]` (fresh at the
  open; still strictly causal — no information after T is used).
- Coin mapping (no Deribit DVOL for alts; same as oc_dvol): BTC -> BTC DVOL +
  BTC realised; ETH -> ETH DVOL + ETH realised; SOL/BNB/XRP -> BTC DVOL + BTC
  realised (market-fear proxy).
- Features per (T, mapped coin):
  1. `dvol_z90` = (`v0` - mean(W)) / std(W, ddof=1); `v0` = asof(T);
     W = {asof(T - k*1h) : k = 1..2160} (trailing 90d of hourly as-of samples,
     current value excluded); require >= 1728 non-NaN else NaN; std == 0 -> NaN.
  2. `dvol_chg24` = asof(T) - asof(T-24h). Unit: DVOL vol points.
  3. `vrp` = asof(T) - rv30(T); rv30(T) = 100 * std(30 daily log returns,
     ddof=1) * sqrt(365) (365-day annualisation for crypto, vol points). Daily
     close C(D) of the mapped coin = close of the hourly bar starting D-1
     23:00 UTC (end = D 00:00); usable iff its end <= T; take the last 31
     usable closes -> 30 log returns; fewer than 31 -> NaN.
- FEAT_START = 2021-06-30 (DVOL starts 2021-04-01; ~90d warm-up). Earlier rows
  are NaN and dropped pairwise; coverage reported.
- Forward returns per coin: `R6[T,s]` = open[T+6]/open[T]-1 (1 day),
  `R42[T,s]` = open[T+42]/open[T]-1 (7 days), simple returns. Last 6/42 bars of
  the grid have no forward return and are dropped pairwise for that horizon.
- Book P&L (vectorised gross, NO costs, before vol target/governor/sleeve):
  `pnl[T,s]` = `w[T,s]` * (`open[T+1]/open[T]` - 1). The last grid bar (no
  forward open) is dropped.
- Anchor years (partition, no orphan bars): Y_k = [A_k, A_{k+1}) for k = 0..3,
  Y_4 = [A_4, A_4 + 365d), A = {2021-09-24, ..., 2025-09-24} (UTC) on `T`.

## Evaluation (fixed here)

- (Q1) IC: per anchor year, per feature, per horizon (6, 42): Spearman
  rho(feature, R) over (T, coin) pairs in the year with both non-NaN —
  (a) pooled (all 5 coins, mapped features), (b) BTC-only (BTCDVOL features vs
  BTC returns), (c) ETH-only (ETHDVOL features vs ETH returns). Require >= 30
  valid pairs else NaN (counts as FAIL for the sign count, never imputed).
  Report rho, n, p (nominal), coverage.
- (Q2) Tercile split of book P&L by `dvol_z90` (mapped per coin): cut-offs
  q33/q67 = percentiles of mapped z90 over the TRAINING pool = (T, coin) rows
  with T on the 4h grid, T in [FEAT_START, A_k), feature non-NaN (strictly
  previous data only; cut-offs use the feature alone, so no book weights are
  needed — this keeps year 1 (book grid starts exactly at A_0 = 2021-09-24)
  causal: its pool is the pre-anchor 4h grid 2021-06-30..2021-09-24, ~2.5k
  values). Require >= 100 training values else the year's terciles are NaN
  (FAIL). Assignment: Lo: v <= q33, Hi: v > q67, Mid: else; NaN -> unassigned.
  The same all-row cut-offs are used for the leg splits. Report mean pnl in
  bps (x1e4 per unit weight) + n per tercile, for (a) all rows, (b) long leg
  (w > 0) only, (c) short leg (w < 0) only. P&L/IC statistics always use
  book-grid rows only (T >= 2021-09-24 with a weight).
- (Q2 spreads) Per year and leg: spread = mean(pnl|Hi) - mean(pnl|Lo) in bps;
  require >= 30 rows in EACH of Hi/Lo else NaN (FAIL).
- (Q2 LOYO) For held-out year h: training = rows of the other 4 anchor years;
  cut-offs from training; spread_h in the held-out year (same >= 30 rule).
  Done for total / long / short legs.
- (Q3) Crash-risk descriptives per year x z90-tercile: mean pnl (bps), stdev
  (bps), P(pnl < 0), mean of negative pnl (avg loss size, bps), n. Read whether
  Hi predicts larger losses or better returns; no extra test.
- DECISION RULE (from the assignment, applied per leg-series total/long/short
  of the z90 tercile spread; Q1 ICs are descriptive context, NOT part of the
  rule): a book rule keyed to that leg is PROMISING iff (a) sign(spread) is
  identical in >= 4 of 5 anchor years (NaN = fail), AND (b) sign(spread_h) is
  identical in >= 4 of 5 LOYO held-out years (NaN = fail).
- Cost context: pnl in bps per unit weight per (bar, coin); round-trip cost
  ~4-8 bps. Book weights average << 1, so per-unit bps overstates portfolio
  impact; portfolio-scale translation is the leader's job.

## Causality / alignment tests (tests/test_oc_dvolbook.py)

- test_asof_usable_at_or_before_T: sampled (T, coin) features recomputed from
  panels truncated to bars with end <= T are unchanged; every retained bar
  satisfies end <= T; shifting any bar after T leaves features unchanged.
- test_cutoffs_causal: year-k cut-offs use no row with T >= A_k; LOYO cut-offs
  for held-out h use no row of year h (recomputed from the saved panel).
- test_books_match_oc_bookic: rebuilt books equal oc_bookic's formula cell by
  cell on the common index (same files, same math).
- test_grid_bounds: no T at/after 2026-09-24 00:00 UTC; anchors partition the
  grid without gaps/overlaps.

## Deliverables

research/tournament/oc_dvolbook/: PLAN.md (this file), compute_dvolbook.py,
panel.parquet (per (T, sym) features + weights + forwards, small), results.json,
REPORT.md (tables + one-line verdict + at most ONE proposed rule with an
economic reason). No tuning on results; any post-hoc change logged in REPORT.md.
No commits.
