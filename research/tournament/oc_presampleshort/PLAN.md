# oc_presampleshort PLAN (pre-registered BEFORE any outcome is computed, 2026-10-07)

## Status

DESCRIPTIVE ONLY. No variant selection, no deployment change, no tuning.
Re-scores STORED predictions at short horizons with the identical yardstick
to oc_bookichorizon. All seven stored anchors are scored descriptively
(pre-sample 2019-03-01, 2019-09-24, 2020-03-01 + reference 2021-09-24 ..
2024-09-24). There is no 2025/most-recent year here (no stored preds);
the deployed book's 2021-2025 numbers from oc_bookichorizon are shown only
as context. The robust selection criterion (AGENTS.md) is NOT applied.

## Puzzle (fixed here)

oc_bookichorizon: the DEPLOYED book's skill lives at short horizons
h = 1, 2, 6, 18 four-hour bars in the TIME-SERIES dimension (pooled IC
+0.02..+0.04, 4/4 dev years for all six members, also positive in the most
recent year), not at the 7-day label (h = 42, 2022 flips). The pre-sample
generality tests (oc_presamplebook: TV-only member; oc_presampleflow: FLOW,
PREMIUM, BLEND) scored only the 7-day label and found ~0 -- possibly the
wrong horizon. Their per-bar predictions are stored: preds_<anchor>.csv in
both folders. This study re-scores those SAME stored predictions at
h in {1, 2, 6, 18, 42} with the identical target/metric machinery.

## Inputs (read-only, never edited)

- oc_presamplebook preds_<anchor>.csv (7 anchors): columns open_time, sym,
  open, pred, label, src, r_next. Series TV = pred. Pre-sample anchors
  (2019-03-01, 2019-09-24, 2020-03-01) are spot-built; reference anchors
  (2021-09-24 .. 2024-09-24) are perp (src column; PLAN/code of that worker).
- oc_presampleflow preds_<anchor>.csv (7 anchors): columns open_time, sym,
  open, pred_flow, pred_prem, pred_blend, label, r_next. Series FLOW =
  pred_flow, PREMIUM = pred_prem, BLEND = pred_blend. All anchors are the
  single stitched SPOT series (presample 1m-built for t < 2020-10-01 +
  spot_majors_20260925 SPOT 4h after; PLAN/code of that worker).
- Deployed-book context: research/tournament/oc_bookichorizon/results.json
  (FINAL pooled/TS/XS), read-only, for sign/size comparison only.

## Fixed series (ONLY these four; fixed here)

TV (rebuilt TV-only member, spot-or-perp per above -- NOT the deployed B/Bq),
FLOW (rebuilt spot-order-flow family -- NOT the deployed perp-flow A/Aq),
PREMIUM (rebuilt Coinbase-premium family, same construction as deployed D/Dq
features but refit through the 7d proxy), BLEND = 0.8*FLOW + 0.2*PREMIUM as
stored (mirrors deployed d2 = 0.8*o1 + 0.2*D at prediction level; the stored
column is used verbatim, never recomputed). Predictions are used RAW.

## Fixed price histories and targets (fixed here; identical to oc_bookichorizon)

- Rebuild per-coin full opens history with the WORKER'S OWN construction:
  (a) spot 1m-built: data/raw/spot_1m_presample_20261007 <SYM>.parquet on the
  standard 00/04/08/12/16/20 UTC grid (open = first finite 1m open, high =
  max finite high, low = min finite low, close = last finite close, volume =
  sum finite; windows with zero finite minutes are NaN bars; gaps stay NaN;
  same as presamplebook.py build_spot_4h / presampleflow.py build_spot_4h);
  (b) perp: BTC data/raw/ma_ribbon_20260924/klines_4h.parquet, others
  data/raw/xs_universe_20260924/<SYM>_4h.parquet (same as load_perp_4h);
  (c) flow stitched spot: (a) for t < 2020-10-01 + <SYM>_spot_4h.parquet from
  data/raw/spot_majors_20260925 for t >= 2020-10-01 (same STITCH_CUT rule).
- Which history per scored row (fixed): TV pre-sample anchors -> (a) spot;
  TV reference anchors -> (b) perp (test bars are perp rows; sigma warms up
  from perp history only, which has ~2y before 2021-09-24); FLOW/PREMIUM/BLEND
  all anchors -> (c) stitched spot. Verify: rebuilt test-bar opens match the
  preds csv open column (report max abs rel diff; tolerance 1e-6 else stop).
- 1-bar open-to-open simple return on the FULL per-study history (sorted):
  r1[k,s] = open[k,s]/open[k-1,s] - 1.
- Trailing sigma (causal, known at bar close t): sigma[t,s] = std(r1[k,s] for
  k in (t-359 .. t)), pandas std ddof=1, min_periods=120, else NaN. Uses only
  opens with timestamp <= t. Same as oc_bookichorizon.
- Forward return by TIMESTAMP (same as oc_bookichorizon): fwd_h[t,s] =
  open[t+h*4h,s]/open[t,s] - 1, where t+h*4h must exist in the full history
  index; tail/missing bars are dropped for that h. h in {1,2,6,18,42} 4h bars
  (= 4h, 8h, 1d, 3d, 7d).
- Vol-normalised target: y_h[t,s] = fwd_h[t,s] / sigma[t,s]. Rows with sigma
  NaN / sigma <= 0 / fwd NaN are dropped for that h.
- Test set (fixed): ONLY stored rows (A <= t < A+365d with realised 7d label,
  i.e. exactly the rows in each preds file). Short horizons could realisably
  extend further into the tail, but no stored pred exists there, so the test
  set is identical across h (disclosed). No filling.
- Prediction at bar t is the stored value at t (known at t's close).

## Fixed metrics per (series, year, h) (fixed here; identical to oc_bookichorizon)

- Pooled Spearman IC: stack all valid (t,s) rows of the year,
  spearman(pred, y_h). Report IC + n_rows + 95% block bootstrap CI.
- Per-coin / time-series (TS) IC: per coin s, spearman over valid bars t of
  the year. Report IC + n per coin. TS summary = arithmetic mean of the 4
  per-coin ICs (NaNs propagate: if any coin NaN, the mean is NaN -- same rule
  as oc_bookichorizon, adjusted from 5 to 4 coins) + count of positive coins.
- Cross-sectional (XS) IC: per bar t with >= 3 valid coins and non-constant
  pred and target across the coins, spearman across the coins (rank the preds
  vs the targets). XS mean = mean over valid bars t in the year. Report mean
  + std + fraction positive + n_bars + 95% bar-bootstrap CI of the mean.
- Spearman = Pearson correlation of mid-ranks (scipy rankdata; same semantics
  as pandas Series.corr(method="spearman")). Constant side or n < 3 -> NaN.
- Block bootstrap 95% CIs (fixed, same as oc_bookichorizon): block length
  L = max(h, 6) bars; B = 500 resamples; seed = 7 (numpy Generator,
  independent per-(year,h) streams default_rng((7, yi, h)), yi = anchor index
  0..6; the four series consume the stream sequentially in fixed order
  TV, FLOW, PREMIUM, BLEND -- same distribution as oc_bookichorizon).
  Resampling unit = bar: draw ceil(n_bars/L) blocks with replacement from the
  year's valid bar list (chronological bar order), concatenate, truncate to
  n_bars, gather ALL valid coin rows of the sampled bars (pooled/per-coin are
  recomputed on resampled rows with fresh ranks; XS mean is the mean of the
  precomputed per-bar XS values at the sampled bars). CI = [2.5, 97.5]
  percentiles. Point NaN -> CI null.

## Verdict rule (fixed now)

Pre-sample short-horizon skill = the (series, h in 1..18) cells where pooled
IC (corroborated by TS mean) is positive in the pre-sample years 2019-2020
with a similar sign and rough size to the deployed book's 2021-2025 ICs at
the same h (pooled ~ +0.02..+0.04 TS-driven, XS ~2-3x smaller), reported per
family (TV / FLOW / PREMIUM / BLEND). h = 42 is the reference control (the
horizon the presample studies originally scored). No threshold, weight, or
choice is changed here. State plainly that these are REBUILT members (spot
flow, TV-only), not the deployed perp-flow blend.

## Leakage statement (how checked; fixed)

Stored parquets/csvs are frozen fits (training rows obey label end <
anchor - 7d per worker PLANs; read-only here). No test-year or most-recent
statistic enters any weight, threshold, or choice (blend 0.8/0.2 is the
stored column; horizons/B/L/seed fixed above). Feature timing: stored pred
at bar t is known at t's close; sigma[t] uses only opens <= t; forward
returns are scoring labels only, never features. Fill timing: N/A (IC
diagnostic, no fills claimed). Fit windows: none in this study (preds
read-only). Tests cover target causality/truncation + hand-checked synthetic
IC/XS cases.

## Costs / execution

IC diagnostic only (no PnL, no fees/funding/vol-target/governor/sleeve).
Gate costs N/A here. This study measures whether the rebuilt members carry
short-horizon rank skill like the deployed book, not net gate pass.

## Compute

Single process, 4h data only (spot 1m -> 4h aggregation one coin at a time,
float; HGBR fits are NOT rerun; RAM << 0.4 GB, no 1m positions held, no GPU):
LIGHT, direct python (no heavy_slot). Progress printed per anchor
(>= every 10 min). Seeds fixed above.

## Deliverables (fixed)

research/tournament/oc_presampleshort/: PLAN.md (this file),
compute_presampleshort.py (rebuilds histories + targets + all metrics),
results.json (per series x year x h: pooled IC + CI + n, per-coin IC + n,
TS mean, XS mean + CI + n; plus meta/definitions), REPORT.md (per-year
tables, bold key question, 3-line Vietnamese verdict, leakage statement),
tmp/ (scratch only). Test tests/test_oc_presampleshort.py (>= 1
causality/truncation test + >= 1 hand-checked synthetic case), run with
.venv/Scripts/python.exe -m pytest tests/test_oc_presampleshort.py -q.
Write ONLY research/tournament/oc_presampleshort/ + that test file.
No commits. No selection, no deployment change.

## Post-hoc log

- 2026-10-07, before REPORT.md was written (outcomes seen in stdout only):
  first compute run pivoted the flow family onto the book file's bar list,
  truncating flow 2020-03-01 to the book's 1241 bars against this PLAN's
  "exactly the stored rows of each preds file". Implementation fix only,
  definitions unchanged: per-series bar sets (TIMES[sname] from each file's
  own open_time), cached parts deleted, run repeated. Reported rows are the
  corrected run only.
