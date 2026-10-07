# oc_idea9 PLAN (pre-registered BEFORE any outcome is computed)

Idea #9 of `research/tournament/oc_ideas/IDEAS.md`: US-equity overnight-gap
book tilt (single risk-appetite dial). This file freezes the hypothesis,
data, exact causal definitions, and decision rule before any outcome
statistic is computed. No tuning on results; any post-hoc change is logged
in REPORT.md.

## Hypothesis (fixed here)

Crypto book drawdowns cluster in global risk-off windows. A single causal
SPX prior-session return (known before each 4h bar) used as a
downside-only exposure dial — scale the book target to 0.75 after a weak
equity session, 1.0 otherwise — trims drawdown and worst days at the cost
of a small return give-up. It is a risk dial, not an ensemble member, not a
blackout: no scaling up, no skipped bars.

## Inputs (read-only, never edited)

- Books: rebuilt EXACTLY as `scripts/forward_v205.py::research_books_d2`
  (same files, same math as `oc_bookvol/compute_bookvol.py`: O1 = half
  (A+B)/2 + half (Aq+Bq)/2 on the union index missing -> 0.0, then
  D2 = 0.8*O1 + 0.2*(D+Dq)/2) from `artifacts/research/engine_real/`.
- Opens: `artifacts/research/engine_real/opens_v154.parquet` (4h opens).
- Symbols: BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT.
- SPX: free Yahoo `^GSPC` daily (chart API v8, no key), fetched by
  `fetch_spx.py` into `data/raw/newinfo_idea9/spx_daily.json` + CSV with
  `manifest.json` (URLs + sha256), range 2016-01-01..2026-09-23 (>= 10y, so
  >= 4y of history stands before the 2021-09-24 anchor).
- Market data up to 2026-09-24 00:00 UTC may be read (assignment; all five
  years are research data, any finding still needs prospective validation).
- No 1m data, one process, RAM < 1 GB (one 4h grid + one daily series).

## Exact causal definitions (fixed now)

- Grid: inner join of books index with opens index (dropna all), sorted 4h
  grid. Weight `w_c[t]` is known at the close of bar `t`.
- Next-bar simple return: `r_c[t] = open_c[t+1]/open_c[t] - 1`. The last
  grid bar has no forward return and is dropped. Same timing as oc_bookvol.
- SPX close time: each `^GSPC` daily bar for calendar date d closes at
  16:00 US Eastern = 20:00 UTC in daylight saving (second Sunday of March
  02:00 local to first Sunday of November 02:00 local), else 21:00 UTC.
  `close_utc(d)` is that instant (e.g. 2022-01-26 -> 21:00 UTC EST,
  2022-06-15 -> 20:00 UTC EDT).
- Prior session at T: `D(T) = max{d : close_utc(d) < T}` (strictly before
  the 4h bar close T, so known at T; for `^GSPC` adjclose == close, the
  `close` field is used). Gap: `gap(T) = ln(C(D(T)) / C(prev(D(T))))`
  where `prev` is the previous trading day in the file. Every input close
  used for `gap(T)` has `close_utc < T`.
- Threshold (single pre-registered rule, no fitting on outcomes):
  per anchor year `A_k`, `q25(A_k)` = 25th percentile (linear
  interpolation) of `gap` over trading days with date in
  `[2016-01-01, A_k - 7 days]` (expanding history, 7-day embargo, strictly
  pre-anchor; year 1 window holds ~5.6y / ~1400 sessions).
- Dial at T: `dial(T) = 0.75 if gap(T) < q25(A(T)) else 1.0`, where `A(T)`
  is the anchor year T falls in (`[A_k, A_k+365d)` partition as in
  oc_bookvol). Downside-only; never above 1.0.
- BASE (deployed, identical to oc_bookvol V0): `u[t] = sum_c w_c[t]*r_c[t]`;
  `sig0[t] = std(u[t-360..t-1], ddof=1)*sqrt(2190)`, min_periods 120;
  `s0[t] = min(2, 0.25/sig0[t])`, NaN or sig <= 0 -> 1.0;
  `ws_base_c[t] = w_c[t]*s0[t]`. Windows end at t-1 (strictly before t).
- TILT (the single scored variant): `ws_tilt_c[t] = ws_base_c[t]*dial(T)`.
- Net P&L per bar per variant (oc_bookvol harness):
  `TO[t] = sum_c |ws_c[t]-ws_c[t-1]|` (first grid bar vs flat 0, each
  variant's own turnover, so dial steps pay turnover);
  `pn[t] = sum_c ws_c[t]*r_c[t] - 0.0005*TO[t]`; equity compounded from
  1.0. ANN = sqrt(6*365) = sqrt(2190).
- Anchor years `A_k = 2021-09-24 .. 2025-09-24` (UTC), partition
  `[A_k, A_{k+1})` k=0..3 plus `[A_4, A_4+365d)`.
- Per (variant, year): return `= prod(1+pn)-1`; max DD on the year-rebased
  equity; Sharpe `= mean(pn)/std(pn,ddof=1)*ANN` (NaN if < 30 bars);
  daily sums grouped by UTC date of T; `worst_day` = min daily sum;
  `fire_rate` = share of year bars with dial 0.75.

## Decision rule (assignment default + sizing/filter extra, fixed here)

Primary effect = drawdown reduction: `dDD_y = DD_BASE,y - DD_TILT,y`
(positive = tilt draws down less). LOYO stability (thresholds are
pre-anchor per year, so LOYO is a stability check as in oc_bookvol):
`LOYO_h` passes iff `sign(dDD_h) == sign(mean_{k!=h} dDD_k)` with that
training mean `> 0` (NaN -> fail). Worst-day guard:
`tail_ok_y = (worst_day_TILT,y >= worst_day_BASE,y)` (not worse).
Return/Sharpe/turnover are descriptive only (the dial is expected to buy
DD with return, per IDEAS.md: return -0.2..0.0 pp/mo).

TILT is PROMISING iff ALL THREE hold: dDD > 0 in >= 4/5 years AND
LOYO-DD passes in >= 4/5 held-out years AND tail_ok in >= 4/5 years.
NaN counts as FAIL. Anything else (including a return gain without the
DD/tail bar) is NOT PROMISING. One variant only; no scaling up, no
re-tuning of 0.75 / 25th pct on outcomes.

## Causality / correctness tests (tests/test_oc_idea9.py)

- test_gap_causal: gap(T) unchanged when SPX rows with date >= T-date are
  removed/perturbed; hand-check D(T)/gap on 2-3 bars incl. an EST/EDT pair.
- test_threshold_prefit: q25(A_k) identical recomputed from SPX rows with
  date < A_k - 7d only; year-1 window starts 2016-01-01.
- test_scales_causal: truncating books+opens at a cut leaves BASE/TILT at
  rows <= cut identical; dial column depends only on T + SPX file.
- test_year_partition: 5 year masks disjoint, cover every scored bar once;
  per-year bar counts match oc_bookvol (2190/2190/2196/2190/2189).
- test_decision_matches_counts: verdict recomputed from results.json
  counters; turnover/cost nonnegativity.

## Deliverables

`research/tournament/oc_idea9/`: PLAN.md (this file), `fetch_spx.py`,
`compute_idea9.py`, `results.json`, REPORT.md (tables + one-line verdict).
`tests/test_oc_idea9.py`. `data/raw/newinfo_idea9/`: SPX daily file(s) +
`manifest.json` (URLs + sha256). No commits, no edits outside these paths.
