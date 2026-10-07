# oc_premfill PLAN (pre-registered BEFORE any outcome is inspected)

Question: does perp-vs-spot dislocation AT THE FILL separate good from bad
dip-rung fills? Liquidation proxy: forced selling pushes the perp below the
spot index, so a deeply negative premium index at the fill minute should go
with (worse — or better, sign read from the data, consistency is what
matters) dip-fill outcomes. Fill-time context only (bot_only label).

## Hypothesis (fixed here)

The premium index level, its 30-minute change, and its 7-day z-score measured
at the fill minute predict dip-fill outcome y1.0. A feature is PROMISING only
if its relationship with y1.0 is sign-consistent across anchor years (rule
below). Expected direction under the liquidation story: more negative premium
(deeper dislocation) -> worse fills (adverse selection / momentum), i.e.
positive IC. The data decides the sign; consistency decides the verdict.

## Data (fixed here)

- Fills: `research/tournament/ext/fills_U_ext.parquet`. Universe MAIN = majors
  {BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT} x R2 depths x1 in
  {2.5, 3.0, 3.5, 4.0, 5.0}. T = t_fill - f minutes (all T on 4h boundaries).
  Outcomes: y1.0 primary; margin m = y1.5 - y1.0 secondary (descriptive only).
- Premium: `data/raw/binance_premium_20260928/<SYM>_premium_1m.parquet`
  (columns open_time, open/high/low/close; open_time = minute bar START (UTC),
  bar END = open_time + 1m; close = premium index in decimal, e.g. -0.0005 =
  perp 5 bps below spot). Per-coin spans (manifest): BTC/ETH from 2020-01-01,
  XRP from 2020-01-06, BNB from 2020-02-10, SOL from 2020-09-14; all through
  2026-09-26 23:59. Bars starting at/after 2026-09-24 00:00 UTC are dropped
  (assignment cutoff); no data beyond the cutoff is read.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides the
  old RULES.md hidden-year cut; findings still need prospective validation).
- LIGHT job: one process, RAM < 1 GB, premium loaded one coin at a time,
  fills joined by searchsorted; no other 1m data is loaded.

## Features (exact, causal — value for a fill uses ONLY premium bars with bar END <= t_fill)

t_fill is minute-exact (all seconds == 0); the fill occurs during minute
[t_fill, t_fill + 1m). Usable premium bars at t_fill are those with
open_time <= t_fill - 1m (bar END <= t_fill). i = index of the bar with
open_time == t_fill - 1m (exact match required via searchsorted check).
Per-coin series (own symbol only; no cross-coin proxy):

1. `prem` — premium close at f-1: c[i]. Unit: decimal premium (1e-4 = 1 bp).
2. `prem_chg30` — 30-minute change: c[i] - c[i-30]. Both bars must exist with
   exact 1m spacing (open_time[i] - open_time[i-30] == 30m) else NaN. Unit:
   decimal premium points.
3. `prem_z7d` — 7-day z-score: (c[i] - mean(W)) / std(W, ddof=1), W = up to
   10080 closes c[i-10079..i] (bars with open_time in [t_fill-7d, t_fill-1m],
   exact 1m spacing verified: open_time[i] - open_time[i-k] == k minutes for
   the window actually used); require >= 7200 non-NaN values in W else NaN;
   std == 0 or non-finite -> NaN. Unit: standard deviations.

Missing-bar policy: any gap (missing minute) touching a required bar makes
that feature NaN for that fill (no imputation, no fill-forward). Coverage is
reported per year; NaN rows are dropped pairwise.

Label: fill-time features (minute f-1 knowledge) -> variant/feature set is
`bot_only` per RULES.md (not available at the bar open T).

## Evaluation (fixed here)

- Anchor years (5): Y_k = [A_k, A_k + 365d) by T,
  A in {2021-09-24 .. 2025-09-24} (UTC). Expected n ~ 990/1045/1330/989/1144.
- Per anchor year, per feature (3 features): Spearman rho(feature, y1.0) AND
  Spearman rho(feature, m = y1.5 - y1.0) over year rows (pairwise-complete;
  NaN if < 30 valid pairs — counts as a FAIL for the sign count, never
  imputed). Report n, n_valid and coverage (fraction of year rows with
  non-NaN feature). The margin IC is DESCRIPTIVE ONLY (helps read whether any
  effect is about TP choice); it is not part of the decision rule.
- Tercile means per year: mean y1.0 (+ n) per Lo/Mid/Hi; cut-offs q33/q67 =
  percentiles of the feature over the TRAINING pool = rows with T < A_k AND
  feature non-NaN (strictly previous data only; no warm-up exclusion needed —
  premium starts 2020). Require >= 100 training rows else the year's terciles
  are NaN (FAIL). Assignment: Lo: v <= q33, Hi: v > q67, Mid: else; NaN
  feature -> unassigned.
- LOYO spread: for held-out year h, training = rows of the other 4 anchor
  years (feature non-NaN); cut-offs from training; spread_h = mean(y1.0 | Hi)
  - mean(y1.0 | Lo) in the held-out year; require >= 30 rows in EACH of Hi/Lo
  else NaN (FAIL).
- DECISION RULE (assignment default, per feature, on y1.0): PROMISING iff
  (a) sign(rho(feature, y1.0)) is identical in >= 4 of 5 anchor years
  (NaN = fail), AND (b) sign(spread_h) is identical in >= 4 of 5 held-out
  years (NaN = fail). Also reported descriptively: whether the spread sign
  matches the IC sign, and per-coin IC splits (NOT part of the rule).
- Cost context: y1.0 reported in bps (1 bps = 1e-4); round-trip cost ~4-8 bps.

## Causality / alignment tests (tests/test_oc_premfill.py)

- test_fill_bar_strictly_before_fill: sampled fills; the f-1 bar has
  open_time == t_fill - 1m and END <= t_fill; the 30m/7d windows use only
  bars with END <= t_fill; shifting all premium data at/after t_fill leaves
  features unchanged (truncate-and-recompute on sampled fills).
- test_training_cutoffs_causal: year-k cut-offs use no row with T >= A_k;
  LOYO cut-offs for held-out h use no row of year h; no premium bar starting
  at/after 2026-09-24 00:00 UTC is used.
- test_universe_counts: majors-R2 join yields 6876 rows with T in
  2020-08-25 .. 2026-09-23 and 990/1045/1330/989/1144 rows per anchor year.

## Deliverables

research/tournament/oc_premfill/: PLAN.md (this file), analyze_premfill.py,
features_premfill.parquet, results.json, REPORT.md (tables + one-line
verdict). No tuning on results; any post-hoc change logged in REPORT.md.
No commits. Test: tests/test_oc_premfill.py.
