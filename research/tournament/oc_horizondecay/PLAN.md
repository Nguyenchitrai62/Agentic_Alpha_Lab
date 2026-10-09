# oc_horizondecay PLAN (pre-registered BEFORE any outcome is computed, 2026-10-08 — FROZEN)

## Assignment

docs/opencode/OPENCODE_W_oc_horizondecay.md + docs/opencode/OPENCODE_W_COMMON_20261007.md
+ AGENTS.md + docs/opencode/OPENCODE_VF_COMMON.md. Implements IDEAS8_20261008.md
idea #4 EXACTLY (Slow-horizon decay ensemble, rank 4), with the two pre-registered
variants and frozen constants below. Read IDEAS8 §4 and its cited CLOSED row first
(oc_bookichorizon diagnostic that FOUND h=1..18 TS skill; oc_horizonfix corrected
yardstick o[T+1]-based forwards; oc_shortmember rejected short-horizon retrain).
Write ONLY `research/tournament/oc_horizondecay/` + `tests/test_oc_horizondecay.py`.

## Question (fixed)

Skill lives at h=1..18 4h bars (oc_bookichorizon, horizonfix-corrected) but short-h
bars are noisiest; equal horizon weighting overpays h=1 noise (BTC lit 2026: slow
beats fast). Does blending member horizon outputs with a frozen slow-decay sharpen
the G2 engine outcome?

## Rows (pre-registered; ONLY these three are eligible)

- REF (G2): deployed reference. Books = `forward_v205.research_books_d2` from the
  deployed caches (A/Aq = `member_A_O1_orders` / `member_Aq_O1_orders`,
  B/Bq = `member_B_tv` / `member_Bq_tv`, D = `members_v154[D]` /
  `members_quarterly_D`), v421 x0.5 bear filter, G2 engine
  (RUNS rule `inv`, k 1.0, kd 1.7, bear True, G 2.0).
- HD1 (V1): same as REF except A and Aq are replaced by decay-blended members
  with frozen weights w_h = (1/h) / sum_{h'}(1/h') over H (see below).
  All other members, blend weights, bear filter and engine settings identical.
- HD2 (V2): same except w_h = (1/sqrt(h)) / sum_{h'}(1/sqrt(h')) over H.

No other eligible variant exists. Controls (reported, NOT eligible for selection):
exposure-matched constant controls CC1/CC2 (book target x the variant's realised
mean absolute-exposure scale per anchor year, computed on the standard grid before
the bear filter; one scalar per year per variant). If the builder check below fails,
there are no HD rows: stop and report. If anything is changed after seeing an
outcome, the original row stays and the change is added as a disclosed extra row.

## Horizon set H (fixed; exact reading of "beyond 18 excluded")

oc_bookichorizon (the cited CLOSED diagnostic) scored EXACTLY h in {1,2,6,18,42}
4h bars (=4h,8h,1d,3d,7d). IDEAS8 §4 says "horizons beyond 18 excluded".
Therefore H = {1,2,6,18} (the diagnostic set truncated at 18; h=42 excluded).
No other horizon is trained or blended. This is the full slow-horizon set the
diagnostic found skill at (4/4 dev years positive pooled+TS at h=1,2,6,18).

## Frozen decay weights (fixed; renormalised; no fit)

- HD1 (1/h): raw 1, 1/2, 1/6, 1/18; sum = 31/18. Renormalised:
  w1 = 18/31 = 0.580645, w2 = 9/31 = 0.290323, w6 = 3/31 = 0.096774,
  w18 = 1/31 = 0.032258 (sum 1.0).
- HD2 (1/sqrt(h)): raw 1.0, 0.70710678, 0.40824829, 0.23570226;
  sum = 2.35105733. Renormalised:
  w1 = 0.425336, w2 = 0.300706, w6 = 0.173643, w18 = 0.100315 (sum 1.0).
Weights are frozen analytic constants (no fit, no test-year statistic).
Blending is at member level (see below); renormalisation is exact in code
(weights divided by their sum, asserted to sum to 1.0 within 1e-12).

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

## Horizon-label replacement (fixed; horizonfix rule; shortmember precedent)

For each h in H={1,2,6,18}, train one full A-member (and one Aq-member) with
EVERY return target inside the builder replaced by the single horizon-h label
(same label in all three sub-models; horizons/weights otherwise frozen):

  y_h[t,s] = clip( log(open[t+1+h] / open[t+1]) / (vol42[t,s]*sqrt(h)), -4, +4 ),

computed per symbol on time-sorted panel rows from the panel's own `open`
and `vol42` (the same vol42 unit as y42; log-form and +-4 clip identical to
v92/v94/v103; executable o[T+1]-based forward per the oc_horizonfix rule,
i.e. the forward tradeable from the decision close).
Rows whose forward is not realised (t+1+h beyond panel end) get NaN (same tail
rule as v92/v94/v103). The quarterly refit (Aq) uses the same h.
Horizons, anchors, embargo cutoffs and the training filters
(`t+(h_orig+1)*4h < cutoff` per sub-model, cutoffs at anchor-EMBARGO_BARS:
v92 102, v94 144, v103 78 bars) are UNCHANGED (conservative: each kept subset
implies t+19*4h < cutoff at worst, i.e. a subset of "before anchor - 7d",
leakage-free; shortmember v287 precedent).
Features (TV + order-level flow + BTC cross, incl. vol42 kept as a FEATURE),
HGB hyperparams
(max_depth=4, lr=0.03, max_iter=400, min_samples_leaf=300, l2=1.0, rs=0),
xs features, vol models, blend weights and downstream are unchanged.
Per anchor, this yields 4 horizon-specific full members A_1,A_2,A_6,A_18
(and Aq_1,Aq_2,Aq_6,Aq_18); the decay-blended member is:

  A_HD1 = w1*A_1 + w2*A_2 + w6*A_6 + w18*A_18 (HD1 weights above),
  A_HD2 = same with HD2 weights (and likewise for Aq).

Blending is on the final member parquet values (post-vol-target,
post-books_v142), reindexed to the union index, fillna 0. No test-year
statistic enters any weight (weights frozen above).

## Blend, bear filter, engine (fixed; G2 must reproduce first)

- Blend = `research_books_d2` exactly: o1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2
  (HD rows: A/Aq = decay-blended, B/Bq/D/Dq = deployed caches);
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
  fee split (maker vs taker notional) from captured events; realised mean
  gross scale per variant-year for the controls.
- Reproduction gate: the REF row must equal `v421_result.json[R2B1D17BFG2]` to
  the digit (per-year R/DD lists, R5 5.41, max-yearly DD 16.91, full-path DD
  16.82). Else stop and report.
- Exposure control rows CC1/CC2 (not eligible): per anchor year,
  scale_y = mean|HD_book| / mean|REF_book| on the standard grid (pre-bear);
  CC book = REF_book * scale_y (that year's scalar). Same bear/engine.

## Selection and most-recent-year rule (fixed)

Compare and choose ONLY on dev4 (anchors 2021..2024-09-24). Robust criterion:
DD <= 20 and no losing dev year; prefer dev4 mean >= 5 %/month; among those
the highest dev4 WORST-year monthly return; ties -> higher mean. Eligible set:
{REF, HD1, HD2} (controls CC1/CC2 reported, not eligible).
The most recent year 2025-09-24..2026-09-23 is scored ONCE, only for the chosen
row (HD1 or HD2 per criterion, or REF if neither passes the DD/no-losing filter)
and for REF, and is labelled. Non-chosen HD rows keep dev4 columns only
(last-year fields redacted, v287/shortmember convention).

## Leakage statement (how checked; fixed)

Feature timing: audited builders reused unchanged (TV/flow merge on (t,sym),
each row from bars <= t close; order-flow frame from aggflow orders <= t).
Label windows: y_h realised at t+1+h, trained only where realised
before the native cutoff (filters kept, each implying t+19*4h < cutoff at
worst; cutoffs 102/144/78 bars = 17d/24d/13d >= 7d embargo; horizonfix
o[T+1] base). Fit windows: all fits (HGB + vol models) end before
anchor-embargo; fresh models for year Y train only before Y-embargo;
quarterly Aq same per quarter. Weights frozen analytic (1/h, 1/sqrt(h),
renormalised; no fit, no test-year reweight). No feedback: no statistic from
any test year (or the most recent year) enters features/labels/fits/choices.
Fill timing: engine minute-5+ trade-through, SL market/TP limit, stop-first
(inherited from the replica). Tests: causality/truncation + hand-checked
synthetic (decay-weight renormalisation, label formula, truncation invariance,
filter-requires-realised, bear, exposure-scale).

## Costs / compute

Gate costs above for engine rows. CPU HGB training (4 horizons x 25 anchors x
3 sub-models = 300 fits) + 4-phase engine, all HEAVY steps via
`scripts/heavy_slot.py run --tag oc_horizondecay --min-free-gb 2.0 -- ...`
(one job at a time; CPU only, no GPU, no Kaggle). Long engine shifts via
nohup + log under `research/tournament/oc_horizondecay/tmp/`.
Progress printed at least every 10 minutes. Scratch only under
`research/tournament/oc_horizondecay/tmp/`.

## Deliverables (fixed)

`research/tournament/oc_horizondecay/`: PLAN.md (this file, frozen),
`decay_rule.py` (pure weights/blend helpers, no data),
`build_horizondecay.py` (builder check + 4-horizon training + decay blend),
`run_engine.py` (books + bear + 4 shifts + scoring incl. CC controls),
`results.json`, `REPORT.md` (per-year tables incl. book win + fee split,
exposure table, what failed, 3-line Vietnamese verdict, leakage checklist).
Test `tests/test_oc_horizondecay.py` (>= 1 causality/truncation test + >= 1
hand-checked synthetic case), run with
`.venv/Scripts/python.exe -m pytest tests/test_oc_horizondecay.py -q`.
Write ONLY that folder + that test file. No commits.

## Post-hoc log

(none; filled only if definitions change after an outcome is seen)
