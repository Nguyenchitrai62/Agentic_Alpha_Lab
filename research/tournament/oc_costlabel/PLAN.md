# oc_costlabel PLAN (pre-registered BEFORE any outcome is computed, 2026-10-08)

## Assignment

docs/opencode/OPENCODE_W_oc_costlabel.md + docs/opencode/OPENCODE_W_COMMON_20261007.md
+ AGENTS.md + docs/opencode/OPENCODE_VF_COMMON.md. Implements IDEAS8_20261008.md
idea #2 EXACTLY (Cost-aware label: P(net-of-cost up move), rank 2), with the two
pre-registered variants and frozen constants below. Read IDEAS8 §2 and its cited
CLOSED rows first (oc_shortmember rejected; oc_bookichorizon diagnostic that found
h=1..18 TS skill; oc_horizonfix corrected yardstick o[T+1]-based forwards).

## Question (fixed)

Raw-return labels spend capacity on dust moves below the 4-8 bps round-trip;
book episode win ~51% says the margin is the cost line. Does retraining the
whale-flow book member (A/Aq) on a COST-THRESHOLDED binary label at the frozen
short horizon h=6 sharpen the G2 engine outcome via fewer dust trades?

## Rows (pre-registered; ONLY these three are eligible)

- REF (G2): deployed reference. Books = `forward_v205.research_books_d2` from the
  deployed caches (A/Aq = `member_A_O1_orders` / `member_Aq_O1_orders`,
  B/Bq = `member_B_tv` / `member_Bq_tv`, D = `members_v154[D]` /
  `members_quarterly_D`), v421 x0.5 bear filter, G2 engine
  (RUNS rule `inv`, k 1.0, kd 1.7, bear True, G 2.0).
- CV1 (V1): same as REF except A and Aq are replaced by members retrained with
  the binary cost label at threshold 8 bps (0.0008, frozen round number).
  All other members, blend weights, bear filter and engine settings identical.
- CV2 (V2): same as REF except A and Aq are replaced by members retrained with
  the binary cost label at threshold 5 bps (0.0005, frozen round number).

No other eligible variant exists. Controls (reported, NOT eligible for selection):
exposure-matched constant controls CC1/CC2 (book target x the variant's realised
mean absolute-exposure scale per anchor year, computed on the standard grid before
the bear filter; one scalar per year per variant). If a variant's yearly mean |exposure|
is within 5% of REF in all dev years, its control is still reported but noted as
near-identity (IDEAS8: "same exposure by construction; control optional").
If the builder check below fails, there are no CV rows: stop and report.
If anything is changed after seeing an outcome, the original row stays and the
change is added as a disclosed extra row.

## Deployed-A builder (exact; builder check first; cites)

`v240_order_level_flow.build_member(quarterly, keep_fills=False)` logic
(cites: RD/v240/v240_order_level_flow.py, RD/v144/v144_deploy_v3.py::books_v142,
RD/v202/v202_quarterly_retrain.py::quarterly, RD/v92/v92_pooled_hgb_vt.py,
RD/v94/v94_long_short_ensemble.py, RD/v103/v103_flow_short_horizon.py),
re-implemented with fresh module instances per tag (no shared state):
fresh `v144_deploy_v3` instance (+ `v202_quarterly_retrain.quarterly` wrapper
iff quarterly); `ext.cb_bars = cb_bars_ext`;
`ext.v92.load_asset = ext.load_asset_ext`; `base92 = ext.v92.build()`;
`xf = v240.feature_frame(ext.v92.load_asset, False)`
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

## Label change (fixed; closest-CLOSED + precedents cited)

Closest CLOSED oc_shortmember (rejected 2026-10-07): kept regression form, changed
horizon to h=6/18 vol-normalised. THIS keeps horizon h=6, changes the label to a
COST-THRESHOLDED BINARY (different axis, never tested). Precedents for mechanics:
v112_sign_classifier.py (HGB Classifier P(y_h>0), same hyperparams, same
panel/embargo/filters, pred = 2*mean(P)-1); oc_horizonfix (executable forwards are
o[T+1]-based: fwd from o[T+1], horizonfix rule); oc_shortmember (EVERY return target
replaced, filters/embargoes unchanged, per-anchor walk-forward).

Replace EVERY return target inside the builder above (v92 `y` H=42,
v94 `y18/y42/y84`, v103 `y6/y18`) by the SINGLE binary cost label (same label in
all three sub-models; horizons/weights otherwise frozen):

  y_cost[t,s] = 1{ log(open[t+1+6] / open[t+1]) > thr },

computed per symbol on time-sorted panel rows from the panel's own `open`
(raw log return, NOT vol-normalised; h=6 4h bars = 1 day; base o[T+1] per the
horizonfix rule, i.e. the executable forward). thr = 0.0008 (CV1) or 0.0005 (CV2)
(frozen round numbers ~ the 4-8 bps round-trip bound; no tuning).
Rows whose forward is not realised (t+1+6 beyond panel end) get NaN (same tail
rule as v92/v94/v103). The quarterly refit (Aq) uses the same thr.
Horizons, anchors, embargo cutoffs and the training filters
(`t+(h_orig+1)*4h < cutoff` per sub-model, cutoffs at anchor-EMBARGO_BARS:
v92 102, v94 144, v103 78 bars) are UNCHANGED (conservative: each kept subset
implies t+7*4h < cutoff, i.e. a subset of "before anchor - 7d", leakage-free).
Features (TV + order-level flow + BTC cross, incl. vol42 kept as a FEATURE),
HGB hyperparams
(max_depth=4, lr=0.03, max_iter=400, min_samples_leaf=300, l2=1.0, rs=0),
xs features, vol models, blend weights and downstream are unchanged, except the
estimators become Classifiers (see next).

## Classifier + weight-scale mapping (fixed, frozen; pre-anchor only)

- Estimator: `HistGradientBoostingClassifier` with the IDENTICAL hyperparams above
  (v112 precedent), one classifier per sub-model per anchor (v92-sub: 1, v94-sub: 1
  replacing the 3-model mean, v103-sub: 1 replacing the 2-model mean), trained on
  `y_cost` (rows with non-NaN label passing the UNCHANGED per-sub-model filter).
  Single-label prediction per sub-model: p = predict_proba(te)[:,1].
  No Platt scaling (raw HGB proba; isotonic below is the calibrator).
- Mapping to the existing weight scale (IDEAS8: "Platt or HGB-proba mapped to
  existing weight scale by pre-anchor isotonic fit"), per anchor and per sub-model,
  fitted on TRAINING rows only (all ends before anchor-embargo):
  X = in-sample p on tr (classifier predict_proba on its own training rows),
  y = in-sample deployed-regressor pred on the SAME tr rows
  (the builder-check repro regressor's predict on tr, same features/filters).
  Fit `sklearn.isotonic.IsotonicRegression(out_of_bounds="clip")` (y_X monotonic).
  Test-time mapped score = iso(p_test). This mapped score replaces the regressor
  `pred` and flows through the UNCHANGED downstream (`v125.raw_lo/raw_ls`,
  `v125.phased`, `vol_target_scale`, books_v142 blend 0.25/0.25/0.5).
  Rationale: downstream clipping (pred/0.5) and vol targeting see the same marginal
  scale as deployed by construction; direction comes from the cost-aware proba.
  In-sample pairing is disclosed (both sides pre-anchor; no test-year statistic).
  Isotonic fit diagnostics (train Spearman iso-input vs output, monotone check) are
  logged, never selected on.

## Blend, bear filter, engine (fixed; G2 must reproduce first)

- Blend = `research_books_d2` exactly: o1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2
  (CV rows: A/Aq = retrained cost-aware, B/Bq/D/Dq = deployed caches);
  D2 = 0.8*o1 + 0.2*(D+Dq)/2; union-index reindex, fillna 0.
- Bear (v421): btc opens < trailing-1200 mean (min 600); halve rows with w>0.
- Engine = v421 `R2B1D17BFG2` replica exactly as
  `oc_shortmember/run_engine.py::cmd_shift` (pipe_setup "v321", corr_size
  rule inv kd 1.7, risk_mult k 1.0, sleeve budget 0.26*1.0*1.7, gross cap
  G 2.0, bear books, win_start 5, agents ON v376 tables, shifts 0..3,
  DEV0 2021-09-24 .. Y1 2026-09-23).
- Gate costs: maker 0.0002, taker 0.00055 (stops/market exits taker), longs
  pay 0.0001 per 8h settlement, shorts zero; no fill in minutes 0-4 after a
  4h close; stop-first in the same 1m bar.
- Metrics: `reset_metric.year_reset` per anchor year (R %/month geometric,
  DD) + 5y/dev4 geometric means + worst year + losing count + full-path DD
  via `v388.mix` (max of close/marked, v421 convention). Book-episode win rate
  via the shortmember/memberdrop book_fill/add/reduce/stop/tp/close walk;
  fee split (maker vs taker notional) from captured events.
- Reproduction gate: the REF row must equal `v421_result.json[R2B1D17BFG2]` to
  the digit (per-year R/DD lists, R5 5.41, max-yearly DD 16.91, full-path DD
  16.82). Else stop and report.
- Exposure control rows CC1/CC2 (not eligible): per anchor year,
  scale_y = mean|CV_book| / mean|REF_book| on the standard grid (pre-bear);
  CC book = REF_book * scale_y (that year's scalar). Same bear/engine.

## Selection and most-recent-year rule (fixed)

Compare and choose ONLY on dev4 (anchors 2021..2024-09-24). Robust criterion:
DD <= 20 and no losing dev year; prefer dev4 mean >= 5 %/month; among those
the highest dev4 WORST-year monthly return; ties -> higher mean. Eligible set:
{REF, CV1, CV2} (controls CC1/CC2 reported, not eligible).
The most recent year 2025-09-24..2026-09-23 is scored ONCE, only for the chosen
row (CV1 or CV2 per criterion, or REF if neither passes the DD/no-losing filter)
and for REF, and is labelled. Non-chosen CV rows keep dev4 columns only
(last-year fields redacted, v287/shortmember convention).

## Leakage statement (how checked; fixed)

Feature timing: audited builders reused unchanged (TV/flow merge on (t,sym),
each row from bars <= t close; order-flow frame from aggflow orders <= t).
Label windows: y_cost realised at t+1+6, trained only where realised
before the native cutoff (filters kept, each implying t+7*4h < cutoff;
cutoffs 102/144/78 bars = 17d/24d/13d >= 7d embargo). Fit windows: all fits
(classifiers + isotonic + vol models) end before anchor-embargo; fresh models
for year Y train only before Y-embargo; quarterly Aq same per quarter.
No feedback: no statistic from any test year (or the most recent year) enters
features/labels/fits/choices (thresholds are frozen round numbers 5/8 bps).
Fill timing: engine minute-5+ trade-through, SL market/TP limit, stop-first
(inherited from the replica). Tests: causality/truncation + hand-checked
synthetic (binary label formula, threshold edge, truncation invariance,
filter-requires-realised, bear, isotonic monotonicity).

## Costs / compute

Gate costs above for engine rows. CPU HGB-classifier training + isotonic + 4-phase
engine, all HEAVY steps via
`scripts/heavy_slot.py run --tag oc_costlabel --min-free-gb 2.0 -- ...`
(one job at a time; CPU only, no GPU, no Kaggle). Long engine shifts via
nohup + log under `research/tournament/oc_costlabel/tmp/`.
Progress printed at least every 10 minutes. Scratch only under
`research/tournament/oc_costlabel/tmp/`.

## Deliverables (fixed)

`research/tournament/oc_costlabel/`: PLAN.md (this file, frozen),
`build_costlabel.py` (builder check + CV1/CV2 training + isotonic mapping),
`run_engine.py` (books + bear + 4 shifts + scoring incl. CC controls),
`results.json`, `REPORT.md` (per-year tables incl. book win + fee split,
exposure table, what failed, 3-line Vietnamese verdict, leakage checklist).
Test `tests/test_oc_costlabel.py` (>= 1 causality/truncation test + >= 1
hand-checked synthetic case), run with
`.venv/Scripts/python.exe -m pytest tests/test_oc_costlabel.py -q`.
Write ONLY that folder + that test file. No commits.

## Post-hoc log

- 2026-10-08 (before any engine outcome; training only): quarterly cost members
  first trained WITHOUT the v202 `[anchor, next_anchor)` cut (the cost path calls
  its predictors directly, bypassing the `v202.quarterly` wrapper that applies
  `_cut` in the deployed builder) -> 20 overlapping year-long predictions and a
  duplicate-index failure in `run_engine --build-books`. Fixed by applying
  `v202._cut` per anchor in `build_member_cost` (same cut as deployed); the two
  bad quarterly files were deleted and retrained. Annual files unaffected
  (disjoint `[A, A+365d)` predictions). No scored outcome had been computed.
