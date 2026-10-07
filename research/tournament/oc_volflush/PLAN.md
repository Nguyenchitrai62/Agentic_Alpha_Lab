# oc_volflush PLAN (pre-registered BEFORE any outcome is inspected)

Question: does capitulation volume AT THE FILL separate good from bad
dip-rung fills? A rung that fills into an abnormal volume spike with heavy
taker selling is the footprint of capitulation; the bounce afterwards should
be larger (exhaustion — or smaller under momentum/adverse selection; sign is
read from the data, consistency is what matters). Fill-time context only
(bot_only label).

## Hypothesis (fixed here)

Relative 15-minute volume and the 15-minute taker-sell share measured at the
fill minute predict dip-fill outcome y1.0. A feature is PROMISING only if its
relationship with y1.0 is sign-consistent across anchor years (rule below).

## Data (fixed here)

- Fills: `research/tournament/ext/fills_U_ext.parquet`. Universe MAIN = majors
  {BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT} x R2 depths x1 in
  {2.5, 3.0, 3.5, 4.0, 5.0}. T = t_fill - f minutes (verified: all T on 4h
  boundaries, all t_fill minute-exact). Outcomes: y1.0 primary (net return at
  TP 1.0 sigma, fees/funding included). Expected 6876 rows,
  ~990/1045/1330/989/1144 per anchor year.
- 1m klines (verified to carry `volume` + `taker_buy_volume`):
  `data/raw/btc_intraday_20260924/klines_1m_YYYY.parquet` (BTC),
  `data/raw/majors_intraday_20260924/<SYM>_1m_YYYY.parquet` (others).
  Columns: open_time (= bar START, UTC), open/high/low/close, volume,
  taker_buy_volume. Bars with open_time >= 2026-09-24 00:00 UTC are dropped
  (assignment cutoff); no data beyond the cutoff is read.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides the
  old RULES.md hidden-year cut; all five years are research data, findings
  still need prospective validation).
- LIGHT job: one process, RAM < 2 GB for the 1m pass (one coin in memory at a
  time, float32; yearly files concatenated per coin then freed), RAM < 1 GB
  afterwards. No GPU.

## Features (exact, causal — a fill uses ONLY 1m bars with bar END <= t_fill)

t_fill is minute-exact. The fill occurs during minute [t_fill, t_fill + 1m).
Usable bars for a fill are those with open_time <= t_fill - 1m (bar END <=
t_fill). i = position of the bar with open_time == t_fill - 1m (exact match
required via searchsorted; no match -> both features NaN). Per-coin series
(own symbol only; no cross-coin proxy):

1. `vol_ratio` — capitulation intensity: (V15 / 15) / MU24, where
   V15 = sum(volume[i-14..i]) (15 closed minutes ending at f-1) and
   MU24 = mean(volume[j] for bars j with open_time in [t_fill - 24h,
   t_fill - 1m]) (up to 1440 bars). Require: all 15 V15 bars present with
   exact 1m spacing (open_time[i] - open_time[i-14] == 14 min) and non-NaN;
   >= 1200 non-NaN bars in the 24h window; MU24 > 0 and finite, V15 finite.
   Else NaN. Unit: multiple of the trailing per-minute mean (1.0 = normal).
2. `sell_share` — taker-sell share over the same 15 minutes:
   1 - sum(taker_buy_volume[i-14..i]) / V15. Require: same 15-bar presence
   rule as V15 plus all 15 taker_buy_volume values non-NaN; V15 > 0.
   Else NaN. Unit: fraction in [0, 1] (values outside logged, not clipped).

No imputation, no fill-forward. Coverage reported per year; NaN rows are
dropped pairwise.

Label: fill-time features (minute f-1 knowledge) -> variant/feature set is
`bot_only` per RULES.md (not available at the bar open T).

## Evaluation (fixed here)

- Anchor years (5): Y_k = [A_k, A_k + 365d) by T,
  A in {2021-09-24 .. 2025-09-24} (UTC).
- Per anchor year, per feature (2 features): Spearman rho(feature, y1.0) over
  year rows (pairwise-complete; NaN if < 30 valid pairs — counts as a FAIL
  for the sign count, never imputed). Report n, n_valid and coverage. Pearson
  r reported as a secondary descriptive column (not part of the rule).
- Tercile means per year: mean y1.0 (+ n) per Lo/Mid/Hi; cut-offs q33/q67 =
  percentiles of the feature over the TRAINING pool = rows with T < A_k AND
  feature non-NaN (strictly previous data only; 1m history starts 2019/2020 so
  no warm-up exclusion is needed). Require >= 100 training rows else the
  year's terciles are NaN (FAIL). Assignment: Lo: v <= q33, Hi: v > q67,
  Mid: else; NaN feature -> unassigned.
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

## Causality / alignment tests (tests/test_oc_volflush.py)

- test_windows_strictly_before_fill: on synthetic 1m frames the f-1 bar has
  open_time == t_fill - 1m and END <= t_fill; V15/MU24/sell windows use only
  bars with END <= t_fill; shifting all 1m data at/after t_fill leaves
  features unchanged (truncate-and-recompute on sampled fills).
- test_missing_bar_policy: a gap inside the 15m window -> both NaN; < 1200
  bars in 24h -> vol_ratio NaN; V15 <= 0 -> sell_share NaN.
- test_training_cutoffs_causal: year-k cut-offs use no row with T >= A_k;
  LOYO cut-offs for held-out h use no row of year h; no 1m bar starting
  at/after 2026-09-24 00:00 UTC is used.
- test_universe_counts: majors-R2 join yields 6876 rows with T in
  2020-08-25 .. 2026-09-23 and 990/1045/1330/989/1144 rows per anchor year.

## Deliverables

research/tournament/oc_volflush/: PLAN.md (this file),
compute_volflush.py, analyze_volflush.py, features_volflush.parquet,
results.json, REPORT.md (tables + one-line verdict). No tuning on results;
any post-hoc change logged in REPORT.md. No commits. Test:
tests/test_oc_volflush.py.

Note on docs/opencode/OPENCODE_VF_COMMON.md: its compute()/events() contract
targets BTC-bar pattern features; this assignment is a tournament fills study
with its own fixed deliverables (PLAN/scripts/results.json/REPORT), so the
common-pattern contract does not apply here; the shared rules honoured are
causality (value at fill uses only bars ending <= t_fill), no peeking at
outcomes before freezing definitions, and the default 4/5 + LOYO 4/5 rule.
