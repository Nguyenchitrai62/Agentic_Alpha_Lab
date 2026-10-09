# oc_bookichorizon PLAN (pre-registered BEFORE any outcome is computed, 2026-10-07)

## Status

DESCRIPTIVE ONLY. No variant selection, no deployment change, no tuning.
All five anchor years are scored descriptively (dev Y0..Y3 = 2021..2024-09-24
plus the most-recent year Y4 = 2025-09-24..2026-09-23, always labelled).
The robust selection criterion (AGENTS.md) is NOT applied.

## Puzzle (fixed here)

oc_bookattrib: the deployed G2 book's realised weights earn by TIMING
(block-shuffle placebo pct 96.8-100 every year 2021-2025).
oc_presamplebook / oc_presampleflow: TV-only, SPOT-flow and premium member
rebuilds have ~0 OOS IC vs the 7-day label in every year, INCLUDING 2021-2024.
oc_staleness (perp members, native labels) found quarter-to-quarter IC sign flips.
Where is the skill? This study asks: at which forward horizon(s) h and in
which dimension (cross-sectional across the 5 coins vs time-series per coin)
do the CACHED deployed member predictions and the final blended book weights
carry positive, stable IC?

## Inputs (read-only, never edited)

- Members (caches `research_books_d2` reads, `artifacts/research/engine_real/`):
  A = `member_A_O1_orders.parquet`, Aq = `member_Aq_O1_orders.parquet`,
  B = `member_B_tv.parquet`, Bq = `member_Bq_tv.parquet`,
  D = `members_v154.parquet` xs `D`, Dq = `members_quarterly_D.parquet`.
- Opens: `artifacts/research/engine_real/opens_v154.parquet`
  (the `eu.er.v154_books()` 4h opens, full history from 2017 for the sigma).
- Standard grid: `books_v154.parquet` index
  (`eu.er.v154_books()[0].index`, 4h, 2021-09-24 .. 2026-09-23).
- Symbols: BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT (engine order).
- Code mirror: `scripts/forward_v205.py::research_books_d2` and
  `research/tournament/oc_memberdrop/run_memberdrop.py::build_standard_books`
  (blend math + v421 bear filter).

## Fixed series (ONLY these ten; fixed here)

On the standard grid `std` (books_v154 index), reindex each member and
fillna 0.0 (same as research_books_d2 / memberdrop):
`o1 = (A+Aq+B+Bq)/4`, `cb = (D+Dq)/2`, `FULL = 0.8*o1 + 0.2*cb`.
Bear mask (v421 lines, same as memberdrop/bookattrib, from opens only):
`btc = opens_std["BTCUSDT"]`,
`bear = (btc < btc.rolling(1200, min_periods=600).mean()).fillna(False)`,
`FINAL[T,s] = 0.5*FULL[T,s]` iff `bear[T] and FULL[T,s] > 0`, else `FULL[T,s]`.
Series scored: A, Aq, B, Bq, D, Dq (six members) + O1, CB (aggregates,
pre-registered helpers) + FULL (pre-bear) + FINAL (post-bear = the deployed
book whose timing P&L is explained). The verdict is stated on FINAL; the
other nine locate the source.

## Fixed horizons and targets (fixed here)

- Horizons: h in {1, 2, 6, 18, 42} 4h bars (= 4h, 8h, 1d, 3d, 7d).
- 1-bar open-to-open simple return on the FULL opens history (2017..):
  `r1[k,s] = open[k,s]/open[k-1,s] - 1`.
- Trailing sigma (causal, known at bar close t):
  `sigma[t,s] = std(r1[k,s] for k in (t-359 .. t))`, pandas std ddof=1,
  min_periods=120, else NaN. Uses only opens with timestamp <= t.
- Forward return: `fwd_h[t,s] = open[t+h,s]/open[t,s] - 1` on the standard
  grid (t+h must exist in the full opens history; tail bars without it
  are dropped for that h).
- Vol-normalised target: `y_h[t,s] = fwd_h[t,s] / sigma[t,s]`.
  Rows with sigma NaN / sigma <= 0 / fwd NaN are dropped for that h.
  Predictions are used RAW (no vol scaling); Spearman is rank-based so the
  normalisation matters only through the target's cross-time/coin ranks.
- Prediction at bar t is the member/book value at t (known at t's close).

## Fixed metrics per (series, year, h) (fixed here)

Years: anchors A_k = 2021..2025-09-24 00:00 UTC, year k = [A_k, A_k+365d)
on the grid timestamp. Y0..Y3 = dev, Y4 = most-recent (labelled everywhere).
A grid bar belongs to exactly one year (no overlap, no gap inside the grid).

- Pooled Spearman IC: stack all valid (t,s) rows of the year,
  `spearman(pred, y_h)`. Report IC + n_rows.
- Per-coin / time-series (TS) IC: per coin s, `spearman(pred[:,s], y_h[:,s])`
  over valid bars t of the year. Report IC + n per coin. TS summary =
  arithmetic mean of the 5 per-coin ICs (NaNs propagate: if any coin NaN,
  the mean is NaN) + count of positive coins.
- Cross-sectional (XS) IC: per bar t with >= 3 valid coins and non-constant
  pred and target across the 5 coins, `spearman` across the 5 coins
  (rank the 5 preds vs the 5 targets). XS mean = mean over valid bars t
  in the year. Report mean + std + fraction positive + n_bars (+ n_skipped).
- Hit rate (sign only), same three cuts: a row/bar-coin scores iff
  pred != 0 and target != 0 and both valid. Pooled hit =
  mean(sign(pred)==sign(target)) + n. Per-coin hit + n per coin.
  XS hit: per bar t, fraction of scored coins correct (bars with 0 scored
  coins skipped); XS-hit mean = mean over valid bars + n_bars.
- Spearman definition: Pearson correlation of mid-ranks (pandas
  `Series.corr(method="spearman")` semantics; ties get average ranks).
  If either side is constant (std 0) or n < 3, the IC is NaN (and its CI null).
  If no scored rows, hit is NaN.
- Block bootstrap 95% CIs (fixed): block length L = max(h, 6) bars;
  B = 500 resamples; seed = 7 (numpy Generator). Resampling unit = bar:
  draw ceil(n_bars/L) blocks with replacement from the year's valid bar
  list (chronological bar order), concatenate, truncate to n_bars, gather
  ALL valid coin rows of the sampled bars (pooled/TS/hit are recomputed on
  the resampled rows with fresh ranks; XS mean is the mean of the
  precomputed per-bar XS values at the sampled bars, which is exact because
  within-bar ranks do not change under bar resampling). CI = [2.5, 97.5]
  percentiles of the B resampled stats. If the point stat is NaN, CI = null.
  (B = 500 keeps the 10 series x 5 h x 5 y x ~8 stats run in minutes on CPU.)

## Verdict rule (fixed now)

The horizon(s) and dimension holding the skill = the (h, dimension) where
FINAL (post-bear) shows IC > 0 in ALL FOUR dev years (stable) or 3/4
(marginal), with bootstrap CIs mostly excluding 0, corroborated by which
members/aggregates (O1 vs CB; A/Aq vs B/Bq vs D/Dq) are positive on the same
(h, dimension). Pooled answers "does the signal rank all bets jointly",
XS-vs-TS answers "is it coin selection at each bar or timing each coin".
The most-recent year is reported alongside but NEVER promotes/demotes a
horizon (descriptive). No threshold, weight, or choice is changed here.

## Leakage statement (how checked; fixed)

Member parquets are research fits frozen before each anchor year (same
provenance as the deployed book; read-only here). No test-year or
most-recent-year statistic enters any weight, threshold, or choice (blend
weights and bear rule fixed above; bootstrap seed fixed). Feature timing:
series value at bar t is the cached member value at t (known at t's close);
sigma[t] uses only opens <= t (full 2017.. history, never future);
forward returns are scoring labels only, never features. Fill timing: N/A
(IC diagnostic, no fills claimed). Fit windows: none in this study
(series read-only). Tests cover causality/truncation + hand-checked
synthetic IC/XS/hit/bootstrap cases.

## Costs / execution

IC/hit diagnostic only (no P&L, no fees/funding/vol-target/governor/sleeve).
Gate costs N/A here. This study measures WHERE the predictive skill lives,
not net gate pass.

## Compute

Single process, 4h parquets only (standard grid + members + opens, tens of
MB, RAM << 0.4 GB, no 1m, no GPU): LIGHT, direct python (no heavy_slot).
Progress printed per (year, h) (>= every 10 min). Seed 7 fixed.

## Deliverables (fixed)

`research/tournament/oc_bookichorizon/`: PLAN.md (this file),
`compute_bookichorizon.py` (builds series + targets + all metrics),
`results.json` (per series x year x h: pooled/per-coin/TS/XS IC + hit +
CIs + n; plus meta/definitions), `REPORT.md` (per-year tables, bold key
question, 3-line Vietnamese verdict, leakage statement), `tmp/` (scratch
only). Test `tests/test_oc_bookichorizon.py` (>= 1 causality/truncation
test + >= 1 hand-checked synthetic case), run with
`.venv/Scripts/python.exe -m pytest tests/test_oc_bookichorizon.py -q`.
Write ONLY `research/tournament/oc_bookichorizon/` + that test file.
No commits. No selection, no deployment change.

## Post-hoc log

- 2026-10-07, before any result was produced: the first compute run timed out
  after 30 min (no results.json or part file was written, no outcome seen).
  Implementation changes only, definitions unchanged: (a) vectorised the
  per-bar XS point computation (rankdata axis=1; identical mid-rank Spearman),
  (b) checkpoint per (year, h) in tmp/parts/ so a timeout resumes instead of
  restarting, (c) bootstrap RNG uses independent per-(year,h) streams
  `default_rng((7, yi, h))` instead of one global `default_rng(7)` sequence
  (same seed family, same B/L/percentiles; required so resumed parts stay
  reproducible without replaying skipped draws). No IC/hit/CIs were inspected
  before this change.
