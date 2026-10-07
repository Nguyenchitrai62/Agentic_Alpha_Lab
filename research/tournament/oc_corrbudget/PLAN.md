# oc_corrbudget PLAN (pre-registered BEFORE any outcome is inspected)

Question: does a slow cross-coin correlation regime known before each day let
the BOT dip sleeve spend less on crash days without giving up the yearly edge?
Context = rolling 30-day average pairwise correlation of the majors hourly
returns, used as a DIP BUDGET scaler w(D) = 1 / (1 + c(D)).

## Hypothesis (fixed here)

High-correlation regimes coincide with worse dip-sleeve crash days. That is,
within each anchor year, the worst daily dip sum among high-correlation days
is more negative than the worst daily dip sum among low-correlation days
(worst_Hi < worst_Lo, terciles cut on strictly previous data). If so, scaling
each day's dip exposure by 1/(1+c) should shrink the worst day while keeping
>= 90% of the yearly sum. PROMISING only under the decision rule below.

## Data (fixed here)

- Fills: `research/tournament/ext/fills_U_ext.parquet` (35 coins,
  2020-08..2026-09-23). Universe MAIN = majors
  {BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT} x R2 depths x1 in
  {2.5, 3.0, 3.5, 4.0, 5.0}. T = t_fill - f minutes (all T on 4h boundaries).
  Outcome = y1.0 only (exact net return at TP 1.0 sigma, unit rung size,
  fees + adverse funding already inside). No other outcome is used.
- Correlation input: `research/tournament/ext/hourly_ext.parquet` ONLY
  (columns t, open, high, low, close, sym; t = bar START UTC, bar END = t+1h;
  majors gap-free except SOL starting 2020-09-14 07:00 UTC). No 1m data, no
  options/premium/DVOL, no bar_open_ext. One process, RAM < 1 GB.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides the
  old RULES.md hidden-year cut; all five years are research data; any finding
  still needs prospective validation).

## Exact causal definitions (frozen)

Hourly log return per major: r(sym, t) = log(close(t) / close(prev bar of the
same sym ordered by t)). A return labelled by bar start t is usable at time U
iff its bar END (t + 1h) is strictly before U.

Daily correlation c(D) for calendar day D (UTC midnight): take all hourly
returns of the 5 majors with bar END in [D - 30d, D 00:00) (ends strictly
before D 00:00; up to 720 returns per coin). For each of the 10 coin pairs,
Pearson correlation over pairwise-complete overlapping returns; a pair is NaN
if < 600 overlapping points. c(D) = mean of the non-NaN pairs; NaN if fewer
than 8 of 10 pairs are valid. c(D) uses ONLY data strictly before D 00:00.
Warm-up: c valid from ~2020-10-15 (SOL history + 720h window); earlier days
are NaN and dropped. Guard (never expected to trigger, c ~ 0.2..0.8):
c <= -0.9 or NaN -> weight w = 1.

Daily dip sum s(D) = sum of y1.0 over MAIN-R2 fills with floor(T to calendar
day UTC) == D (equal notional = 1 per rung). Days with zero fills have no row
and never count as worst days. Yearly sum S(Y) = sum of s(D) over fill-days D
in the anchor year Y = [A, A + 365d), A in {2021-09-24 .. 2025-09-24} (UTC).
Worst day W(Y) = min s(D) over fill-days in Y (date reported).

Terciles per year (sequential, causal): training pool = fill-days D' with
D' < A_k, c(D') non-NaN (all history since warm-up, strictly previous data
only). Require >= 100 training days else the year's terciles are NaN (FAIL).
Cut-offs q33/q67 = 33rd/67th percentiles of training c. Assignment: Lo:
c <= q33, Hi: c > q67, Mid: else. Per year report per bucket: n_days,
mean daily sum, worst daily sum. Effect E1(Y): worst_Hi < worst_Lo
(strictly more negative); requires >= 10 days in EACH of Lo/Hi else FAIL.

LOYO terciles: for held-out year h, training = fill-days of the other 4
anchor years with valid c (>= 100 required); cut-offs from that training;
same assignment and E1(h) comparison in the held-out year.

Budget scaler (uses raw c, no cut-offs, no fitting): w(D) = 1 / (1 + c(D))
(c NaN or <= -0.9 -> w = 1). s_scaled(D) = s(D) * w(D). Per year:
S_base, S_scaled, retention = S_scaled / S_base, W_base = min s(D),
W_scaled = min s_scaled(D). Scaler PASS(Y): W_scaled > W_base (strictly less
negative) AND S_base > 0 AND retention >= 0.90. (If S_base <= 0 the retention
ratio is meaningless -> FAIL. Worst-day ties with no fills scaled are
impossible since w < 1 whenever c > 0.)

Descriptive only (NOT part of the rule): per-year Spearman rho(c(D), s(D))
over fill-days; mean daily sum per tercile; distribution of c and w.

Cost context: y1.0 and daily sums reported in bps (1 bps = 1e-4 per unit
rung notional); round-trip cost ~4-8 bps per fill is inside y1.0.

## Decision rule (from the assignment)

- (a) E1 sequential: worst_Hi < worst_Lo in >= 4 of 5 anchor years.
- (b) E1 LOYO: worst_Hi < worst_Lo in >= 4 of 5 held-out years.
- (c) Scaler utility: PASS in >= 4 of 5 anchor years.
- PROMISING iff (a) AND (b) AND (c) all hold. Otherwise NOT PROMISING.
  NaN/FAIL counts as a miss, never imputed. One variant only (30d as
  assigned); no tuning on results; any post-hoc change logged in REPORT.md.

## Causality / alignment tests (tests/test_oc_corrbudget.py)

- test_corr_causal_truncate: 20 sampled days; c(D) recomputed from hourly
  truncated to bar END < D 00:00 equals the full-panel row.
- test_no_future_hour: no c(D) uses any hourly bar with END >= D 00:00.
- test_cutoffs_causal: sequential cut-offs for year k use no fill-day >= A_k;
  LOYO cut-offs for held-out h use no day of year h.
- test_T_and_bounds: T = t_fill - f minutes; no fill with T >= 2026-09-24;
  no hourly bar starting at/after 2026-09-24 00:00 UTC is used.
- Pure helpers (bucket assignment, scaler pass logic) unit-tested on
  synthetic frames.

## Deliverables

research/tournament/oc_corrbudget/: PLAN.md (this file), analyze_corrbudget.py,
results.json, REPORT.md (tables + one-line verdict). tests/test_oc_corrbudget.py.
No commits, no edits outside these two paths.
