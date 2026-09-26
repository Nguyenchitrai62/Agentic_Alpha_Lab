# v89 blind audit — COMPARISON.md (Part B)

Blind replication was saved BEFORE opening `v89/` (see `replication.json`).
Audit scope: `v89/v89_pooled_hgb.py`, `v89/v89_result.json`, `v89/result_manifest.json`.
No leader files were edited.

## A. Number comparison (anchor 2025-09-24)

| metric | blind audit | leader v89 | diff |
|---|---|---|---|
| train rows | 60930 | 60930 | 0 (match) |
| Spearman pred vs y (pred rows, drop NaN y) | 0.1602 | 0.1682 | 0.0080 (< 0.01 threshold) |
| pred rows / with y | 10950 / 10750 | — / — | window [2025-09-24, 2026-09-24) |

Threshold from spec (IC diff > 0.01 or train-row mismatch = explain root cause):
train rows match exactly; IC diff 0.008 passes the threshold, but a root cause
was still isolated (below). Model params identical
(HGB max_depth=4, lr=0.03, max_iter=400, min_samples_leaf=300, l2=1.0, rs=0).

## B. Root cause of the 0.008 IC gap (spec ambiguities)

Feature-by-feature max-abs diff on BTC (lengths equal, y identical, NaN counts equal):
ret/snr/vol/EMA/daily means exact (0.0); funding means differ ~1e-13 (pandas
rolling vs cumsum rounding — binning-irrelevant).
The material divergences are NaN-vs-value conventions for EARLY rows only
(2025 train/predict rows themselves are equal):

1. `ribbon` when SMA50/200 unavailable: leader `np.where(...)` yields 0.0
   (1 NaN total); audit used NaN (1195 NaNs = first ~200 daily bars).
2. funding means: leader `rolling(21, min_periods=3)` / `rolling(90, min_periods=9)`;
   audit required full 21/90 prints (NaN counts 14 vs 50, 26 vs 188).
   For all 2025 rows both have full windows and values agree.

HGB is NaN-native, so 0-vs-NaN / value-vs-NaN on early training rows changes
splits and shifts every prediction (pred Spearman audit-vs-leader 0.95,
max |Δpred| ~0.50), giving IC 0.160 vs 0.168. Train-row count is unaffected
because the filter is on `y` only. With the leader's lenient conventions the
leader IC 0.1682 reproduces exactly in this environment.

## C. Look-ahead audit of `v89_pooled_hgb.py`

- Features: ret/snr/vol (past closes), EMA (past, adjust=False), daily
  SMA/ribbon via `merge_asof(backward)` on close_time (last CLOSED daily bar;
  coincident 23:59:59.999 inclusion is the closed bar — OK), funding via
  `merge_asof(backward)` on fundingTime (only prints ≤ bar close — OK),
  volume z (past 180 incl. current closed bar — OK). No future inputs.
- Label/embargo: y=log(open[t+43]/open[t+1])/(std42·√42), clip ±4 — matches spec.
  cutoff=A−4h·(42+60); train requires t<cutoff AND t+43 bars<cutoff AND y not NaN.
  Label realized before cutoff plus 60-bar embargo. Predict [A,A+365d). Pass.
- Portfolio K rule: K for year i from PRIOR out-of-sample years only
  (K=1 first year; later K=floor(min(2, 0.20/maxDD)·20)/20, cap 2x). No forward use. Pass.
- Execution timing: W[t] (from close-t prediction, daily-rebalanced/ffilled)
  earns r[t]=open[t+2]/open[t+1]−1 — one-bar delay, fills at open[t+1]. No intrabar
  fill at signal close. Turnover/fees/funding per scenario. Pass.
- Baseline TSMOM uses the same past-only ret42/ret180/ribbon. Pass.

No look-ahead found. Minor non-leakage notes: funding min_periods 3/9 and
ribbon-0-when-NaN are stability/definition choices, not leakage; `quote_volume.clip(lower=1)`
is a no-op here (min > 90k).

## D. Manifest / acceptance note

`result_manifest.json`: v89/track A, status `rejected`, `live_approved:false`,
`audit.passed:false, replay_complete:false` ("awaiting independent blind reproduction").
Hidden-year (2025) model_normal net +10.69%, monthly-geometric +0.85%, DD 5.37%,
fills 224; 5y worst-year DD 51.56% (model_normal). Fails the leader acceptance gate
(monthly ≥5% all scenarios, DD ≤20%) — `rejected` is consistent.

## E. Verdict

Numbers reproduced within tolerance (rows exact, IC Δ=0.008 < 0.01); residual gap
explained by documented NaN-vs-0 funding/ribbon conventions. No look-ahead in
features, labels/embargo, K rule, or execution timing. Audit complete; leader
files untouched.
