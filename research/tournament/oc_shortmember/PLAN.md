# oc_shortmember PLAN (pre-registered BEFORE any outcome is computed, 2026-10-07)

## Question (fixed)

The deployed book's IC is stable and positive at h = 1..18 four-hour bars but
unstable at the 7-day label h = 42 that the A / Aq (whale-flow) members are
TRAINED on. Does retraining the whale-flow member A directly on a
SHORT-horizon label sharpen the signal at the G2 engine level?

## Rows (pre-registered; ONLY these three)

- G2: deployed reference. Books = `forward_v205.research_books_d2` from the
  deployed caches (A/Aq = `member_A_O1_orders` / `member_Aq_O1_orders`,
  B/Bq = `member_B_tv` / `member_Bq_tv`, D = `members_v154[D]` /
  `members_quarterly_D`), v421 x0.5 bear filter, G2 engine
  (RUNS rule `inv`, k 1.0, kd 1.7, bear True, G 2.0).
- AS6: same as G2 except A and Aq are replaced by members retrained with the
  label horizon changed to h = 6 bars (1 day). All other members, blend
  weights, bear filter and engine settings identical.
- AS18: same as G2 except A and Aq are replaced by members retrained with the
  label horizon changed to h = 18 bars (3 days).

No other variant exists. If the builder check (below) fails, there are no
AS rows: stop and report. If anything is changed after seeing an outcome,
the original row stays and the change is added as a disclosed extra row.

## Deployed-A builder (exact; builder check first)

`v240_order_level_flow.build_member(quarterly, keep_fills=False)` logic,
re-implemented with fresh module instances per tag (no shared state):
fresh `v144_deploy_v3` instance (+ `v202_quarterly_retrain.quarterly` wrapper
iff quarterly); `ext.cb_bars = cb_bars_ext`;
`ext.v92.load_asset = ext.load_asset_ext`; `base92 = ext.v92.build()`;
`xf = v240.feature_frame(ext.v92.load_asset, keep_fills=False)`
(TV(17) + order-level flow(6) on `data/raw/aggflow_20260928_orders`);
`vol_predict` excludes xf columns; `ext.v92.build = merge(base92, xf)`;
`v103.build = merge(b103(), xf)`; return `v144.books_v142()[1]`
(0.25 LO + 0.25 LS + 0.5 flow, v125 phased/raw + vol_target_scale).
Annual A uses the 5 annual anchors 2021..2025-09-24 (predicts own
[A, A+365d)); quarterly Aq uses the 20 v202 quarterly anchors
2021-09-24 + 3k months through 2026-06-24 (predicts own quarter).
Builder check: reindex repro and cache to the `books_v154` grid, fillna 0,
per anchor year stack all (bar, coin) predictions and require
Spearman(repro, cache) >= 0.999 for A in EACH of the 5 years AND for Aq in
EACH of the 5 years. Else stop and report (no training, no engine).

## Label change (fixed; v287 precedent)

Replace EVERY return target inside the builder above (v92 `y` H=42,
v94 `y18/y42/y84`, v103 `y6/y18`) by the short-horizon vol-normalised label

  y_hnew[t,s] = clip( log(open[t+1+hnew]/open[t+1]) / (vol42[t,s]*sqrt(hnew)), -4, +4 ),

hnew = 6 (AS6) or 18 (AS18), computed per symbol on time-sorted panel rows
from the panel's own `open` and `vol42` (the same vol42 unit as y42;
log-form and +-4 clip identical to v92/v94/v103). The quarterly refit (Aq)
uses the same hnew. Horizons, anchors, embargo cutoffs and the training
filters (`t+(h_orig+1)*4h < cutoff` per sub-model, cutoffs at
anchor-EMBARGO_BARS: v92 102, v94 144, v103 78 bars) are UNCHANGED
(conservative: a subset of "before anchor - 7d", leakage-free).
Features, HGB hyperparams
(max_depth=4, lr=0.03, max_iter=400, min_samples_leaf=300, l2=1.0, rs=0),
xs features, vol models, weights and blend are unchanged.

## Blend, bear filter, engine (fixed; G2 must reproduce first)

- Blend = `research_books_d2` exactly: o1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2
  (AS rows: A/Aq = retrained, B/Bq/D/Dq = deployed caches);
  D2 = 0.8*o1 + 0.2*(D+Dq)/2; union-index reindex, fillna 0.
- Bear (v421): btc opens < trailing-1200 mean (min 600); halve rows with w>0.
- Engine = v421 `R2B1D17BFG2` replica exactly as
  `oc_memberdrop/run_memberdrop.py::cmd_shift` (pipe_setup "v321", corr_size
  rule inv kd 1.7, risk_mult k 1.0, sleeve budget 0.26*1.0*1.7, gross cap
  G 2.0, bear books, win_start 5, agents ON v376 tables, shifts 0..3,
  DEV0 2021-09-24 .. Y1 2026-09-23).
- Gate costs: maker 0.0002, taker 0.00055 (stops/market exits taker), longs
  pay 0.0001 per 8h settlement, shorts zero; no fill in minutes 0-4 after a
  4h close; stop-first in the same 1m bar.
- Metrics: `reset_metric.year_reset` per anchor year (R %/month geometric,
  DD) + 5y/dev4 geometric means + worst year + losing count + full-path DD
  via `v388.mix` (max of close/marked, v421 convention).
- Reproduction gate: the G2 row must equal `v421_result.json[R2B1D17BFG2]` to
  the digit (per-year R/DD lists, R5 5.41, max-yearly DD 16.91, full-path DD
  16.82). Else stop and report.

## Selection and most-recent-year rule (fixed)

Compare and choose ONLY on dev4 (anchors 2021..2024-09-24). Robust criterion:
DD <= 20 and no losing dev year; prefer dev4 mean >= 5 %/month; among those
the highest dev4 WORST-year monthly return; ties -> higher mean. The most
recent year 2025-09-24..2026-09-23 is scored ONCE, only for the chosen row
(AS6 or AS18 per criterion, or G2 if neither passes the DD/no-losing filter)
and for G2, and is labelled. Non-chosen rows keep dev4 columns only
(last-year fields removed, v287 convention).

## Member IC diagnostic (fixed, descriptive)

Pooled Spearman per anchor year (dev Y0..Y3 + recent Y4 labelled) of the
ANNUAL member predictions (deployed A vs retrained AS6 vs retrained AS18) at
h in {1, 6, 18, 42} vs bookichorizon-style targets
(fwd_h = open[t+h]/open[t]-1 on full opens history, sigma = trailing-360-bar
std of 1-bar open returns min120 causal, y = fwd/sigma; stacked (bar,coin)
Spearman, predictions raw). No bootstrap, no selection on IC.

## Leakage statement (how checked; fixed)

Feature timing: audited builders reused unchanged (TV/flow merge on (t,sym),
each row from bars <= t close). Label windows: y_hnew realised at
t+1+hnew, trained only where realised before the native cutoff
(filter kept). Fit windows: all fits end before anchor-embargo (17d/24d/13d
>= 7d horizon max); fresh models for year Y train only before Y-embargo;
quarterly Aq same per quarter. No feedback: no statistic from any test year
(or the most recent year) enters features/labels/fits/choices. Fill timing:
engine minute-5+ trade-through, SL market/TP limit, stop-first (inherited
from the replica). Tests: causality/truncation + hand-checked synthetic.

## Costs / compute

Gate costs above for engine rows; IC diagnostic has no P&L. CPU HGB
training + 4-phase engine, all HEAVY steps via
`scripts/heavy_slot.py run --tag oc_shortmember --min-free-gb 2.0 -- ...`.
Progress printed at least every 10 minutes. No GPU. No Kaggle uploads.
Scratch only under `research/tournament/oc_shortmember/tmp/`.

## Deliverables (fixed)

`research/tournament/oc_shortmember/`: PLAN.md (this file),
`build_shortmember.py` (builder check + AS6/AS18 training),
`run_engine.py` (books + 4 shifts + scoring), `results.json`, `REPORT.md`
(per-year tables, member-IC table, what failed, 3-line Vietnamese verdict,
leakage checklist). Test `tests/test_oc_shortmember.py` (>= 1
causality/truncation test + >= 1 hand-checked synthetic case),
run with `.venv/Scripts/python.exe -m pytest tests/test_oc_shortmember.py -q`.
Write ONLY that folder + that test file. No commits.

## Post-hoc log

(none; filled only if definitions change after an outcome is seen)
