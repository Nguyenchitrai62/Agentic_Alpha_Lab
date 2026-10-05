# oc_dvol PLAN (pre-registered BEFORE any outcome is inspected)

Question: does Deribit implied volatility (DVOL) observed before a dip-rung
bar open separate good from bad dip fills? DVOL = Deribit 30-day implied-vol
index (their VIX analogue), public history for BTC and ETH only.

## Hypothesis (fixed here)

High / rising implied vol and a wide variance risk premium at the bar open
predict worse (or better — sign to be read from the data, consistency is what
matters) dip-fill outcomes y1.0. A feature is PROMISING only if its
relationship with y1.0 is sign-consistent across anchor years (rule below).

## Data (fixed here)

- Source: Deribit public `get_volatility_index_data`, currencies BTC + ETH,
  resolution `3600` (1h; probed 2026-10-05: 1h IS available for the whole
  span, so no 1D fallback needed). Span 2021-04-01 .. 2026-09-24 00:00 UTC.
- Fetch: month-by-month chunks per currency (66 months x 2 = 132 requests),
  single process, sequential, 0.2 s sleep; follow `continuation` paging
  (use as next `end_timestamp`) if ever non-null. Raw JSON responses saved to
  `data/raw/deribit_dvol_20261005/<CUR>_YYYY-MM.json` + `manifest.json`
  (request URL + sha256 per file). Parsed panel:
  `research/tournament/oc_dvol/dvol_hourly.parquet` (t = bar START (UTC),
  bar END = t + 1h, o/h/l/c = DVOL vol points, sym = BTCDVOL/ETHDVOL).
- Fills: `research/tournament/ext/fills_U_ext.parquet`. Universe MAIN = majors
  {BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT} x R2 depths x1 in
  {2.5, 3.0, 3.5, 4.0, 5.0}. T = t_fill - f minutes (all T on 4h boundaries).
  Outcome = y1.0 only (net return at TP 1.0 sigma, unit rung size).
- Realized vol: `research/tournament/ext/hourly_ext.parquet` hourly closes
  (t = bar start UTC; covers 2020-08-01 .. 2026-09-23 23:00 UTC). No 1m data
  is loaded (hourly is sufficient; RAM stays far below the limit).
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides the
  old RULES.md hidden-year cut; findings still need prospective validation).

## Features (exact, causal — value at T uses ONLY data strictly before T)

As-of rule: a DVOL hourly bar (or daily close) is usable at T iff its bar END
is strictly before T (`end < T`). `asof(T)` = close of the last usable hourly
bar (for 4h-aligned T this is the bar [T-2h, T-1h]; 1h staleness, immaterial
for these slow features, required for strict compliance).

Coin mapping (no Deribit DVOL exists for alts): BTC rungs -> BTC DVOL + BTC
realized; ETH rungs -> ETH DVOL + ETH realized; SOL/BNB/XRP rungs -> BTC DVOL
+ BTC realized as the market-fear proxy. One feature set per row:

1. `dvol_z90` — DVOL level z-score vs trailing 90 days: (v - mean(W)) / std(W),
   W = up to 2160 hourly `asof` samples `asof(T-k*1h)`, k = 1..2160 (all with
   end < T by construction); require >= 1728 non-NaN else NaN; ddof=1;
   std == 0 -> NaN. Unit: standard deviations.
2. `dvol_chg24` — DVOL 24h change: `asof(T) - asof(T-24h)` (same as-of rule
   at the lagged time). Unit: DVOL vol points.
3. `vrp` — variance risk premium: `asof(T) - rv30(T)`,
   rv30(T) = 100 * std(30 daily log returns; ddof=1) * sqrt(365) (vol points,
   365-day annualisation for crypto). Daily close C_c(D) of coin c = close of
   the hourly bar starting D-1 23:00 UTC (last bar with start < D 00:00);
   usable iff C's bar end (= D 00:00) is strictly before T; take the last 31
   usable closes -> 30 log returns; fewer than 31 -> NaN.

DVOL history starts 2021-04-01, so `dvol_z90` is valid from ~2021-06-30;
earlier rows are NaN and dropped pairwise (coverage reported).

## Evaluation (fixed here)

- Anchor years (5): Y_k = [A_k, A_k + 365d) by T,
  A in {2021-09-24 .. 2025-09-24} (UTC).
- Per anchor year, per feature: Spearman rho(feature, y1.0) over year rows
  (pairwise-complete; NaN if < 30 valid pairs — counts as a FAIL for the
  sign count, never imputed). Report n and coverage (fraction of year rows
  with non-NaN feature).
- Tercile means per year: cut-offs q33/q67 = percentiles of the feature over
  the TRAINING pool = rows with T < A_k AND T >= 2021-06-30 (feature-valid
  start) AND feature non-NaN (i.e. strictly previous data only; for year 1
  this is 2021-06-30 .. 2021-09-24). Require >= 100 training rows else the
  year's terciles are NaN (FAIL). Assignment: Lo: v <= q33, Hi: v > q67,
  Mid: else; NaN feature -> unassigned. Report mean y1.0 + n per tercile.
- LOYO spread: for held-out year h, training = rows of the other 4 anchor
  years; cut-offs from training; spread_h = mean(y1.0 | Hi) - mean(y1.0 | Lo)
  in the held-out year; require >= 30 rows in EACH of Hi/Lo else NaN (FAIL).
- DECISION RULE (from the assignment, per feature): PROMISING iff
  (a) sign(rho) is identical in >= 4 of 5 anchor years (NaN = fail), AND
  (b) sign(spread_h) is identical in >= 4 of 5 held-out years (NaN = fail).
  Also reported descriptively: whether the spread sign matches the IC sign,
  and BTC-only / ETH-only / proxy-coin (SOL+BNB+XRP) IC splits (NOT part of
  the rule).
- Cost context: y1.0 reported in bps (1 bps = 1e-4); round-trip cost ~4-8 bps.

## Causality / alignment tests (tests/test_oc_dvol.py)

- test_asof_strictly_before_T: 200 sampled rungs; no DVOL bar / daily close
  used by any feature has end >= T; shifting all DVOL data after T leaves
  features unchanged (truncate-and-recompute on 5 sampled T).
- test_training_cutoffs_causal: year-1 cut-offs use no row with T >= A_1;
  LOYO cut-offs for held-out h use no row of year h.
- test_manifest_covers_span: raw files + manifest present; parsed panel spans
  2021-04 .. 2026-09-23 for both coins (gaps logged, not filled).
- test_universe_counts: majors-R2 join yields the expected ~6876 rows with
  T in 2020-08-25 .. 2026-09-23 and ~990/1045/1330/989/1144 rows per year.

## Deliverables

research/tournament/oc_dvol/: PLAN.md (this file), fetch_dvol.py,
analyze_dvol.py, dvol_hourly.parquet, results.json, REPORT.md (tables +
one-line verdict). No tuning on results; any post-hoc change logged in
REPORT.md. No commits.
