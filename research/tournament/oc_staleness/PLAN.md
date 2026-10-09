# oc_staleness — PLAN (pre-registered BEFORE any outcome is computed)

## Question
How fast does the book's skill decay with model age? (Decides the live retraining schedule.)

## Fixed method (from OPENCODE_W_oc_staleness.md, no variants beyond the named cuts/families)
- Member families (training code = the code behind `research_books_d2`):
  - **A (whale-flow A)**: panel = `v92.build()` base merged with TV(17) (`v231/tv_indicators.py`)
    + order-level flow(6) (`v236/flow_features.py` on `data/raw/aggflow_20260928_orders`,
    via `v240_order_level_flow.feature_frame(keep_fills=False)`). Label = v92 7d vol-norm
    `y = clip(fwd42/(vol42*sqrt(42)), +-4)` (`H=42`). Model = ONE pooled HGB
    (`max_depth=4, lr=0.03, max_iter=400, min_samples_leaf=300, l2=1.0, rs=0`, = v92).
  - **D (Coinbase-premium D)**: panel = `v103.build()` (v92 base + kline FLOW(10)) merged with
    CB(5) via `v111.add_cb` (Coinbase 1h vs Binance spot, known at bar close). Labels = short-horizon
    `y6 (H=6)`, `y18 (H=18)` (same formulas as `v103.build`). Model = TWO pooled HGBs (same
    hyperparams), `pred = mean(pred6, pred18)` (= `v103.train_predict`).
- Training cuts (stale): `C in {2021-09-17, 2022-09-17, 2023-09-17}`. Training rows: `t < cutoff`
  AND label notna AND label realised before cutoff (`t+(H+1)*4h < cutoff`), cutoff = native rule
  (`C - 4*EMBARGO_BARS h`: v92 102 bars ~17d for A; v103 78 bars ~13d for D). This is a SUBSET of
  "data before C-7d", so compliant. Feats = all panel cols except `y,t,open,sym,bar,y*`.
- Predict every 4h bar `t in [C, 2025-09-23]` (features are causal at `t` close; predictions use the
  model frozen at C, no retraining).
- Age bins per C: bin k=0..7 = bars with `C + k*Q <= t < C + (k+1)*Q`, `Q = 91.3125 d` (3 months),
  intersected with `[C, 2025-09-24)`. Up to 24 months.
- Metric per bin (pooled over the 5 majors, rows with realised label ending `< 2025-09-24` only):
  - A: Spearman IC `corr(pred, y42)`; D: Spearman IC `corr(pred, y18)` (primary) + `corr(pred, y6)`
    (secondary). Report `n` per bin.
  - Vectorised DIAGNOSTIC book P&L (labelled, NOT gate, no costs): `w = clip(pred/0.5, -1, 1)`
    per (t,sym); `r = open[t+1]/open[t]-1`; `pnl[t] = sum_s w*r` (gross, no fees/funding/vol-target).
    Per bin: sum + mean/bar + n. Uses only `open[t+1]` (>= t+1 fill).
- Fresh reference: same feature/label/model/cutoff code, trained at yearly anchors
  `A in {2021-09-24, 2022-09-24, 2023-09-24, 2024-09-24}` (cutoff = `A - native embargo`), each model
  predicts its own year `[A, A+365d)`. For a stale bin, `IC_fresh` = pooled IC of the fresh preds on
  THE SAME bars (same label availability). Difference = `IC_fresh - IC_stale` per bin.
- Halving age per (family, C): `IC0` = stale bin0 IC. If `IC0 <= 0`: "no positive skill at age 0".
  Else first bin k>=1 with `IC_k <= 0.5*IC0` (bin start age reported); else "no halving within 24m".
- Data rule: nothing with timestamp `>= 2025-09-24` is read for features/fits; labels only where
  realised `< 2025-09-24` (tail bars dropped). Opens beyond the cutoff are never used.

## Outputs (all inside `research/tournament/oc_staleness/`)
- `results.json` (per family x cut x bin: stale IC + n, fresh IC + n, diff, diagnostic pnl sum/mean/n).
- `staleness_ic.png` (IC vs model age: stale solid + fresh dashed, one panel per family, cuts as series).
- `staleness.csv` (same table as results.json, flat).
- `REPORT.md` (tables + halving ages + fresh-vs-stale + descriptive recommendation
  monthly/quarterly/yearly + 3-line Vietnamese verdict + leakage checklist).
- Test file `tests/test_oc_staleness.py` (>=1 causality/truncation test + >=1 hand-checked synthetic case).

## Leakage checklist (to confirm in REPORT)
1. Feature timing: TV/flow/CB rows at t use inputs <= t close only (audited builders reused unchanged).
2. Label windows: 7d/3d/1d forwards realised before cutoff (`t+(H+1) < cutoff`) and before 2025-09-24.
3. Fit windows: all fits end before anchor-embargo (native embargo >= 13d >= 7d horizon max for D,
   17d >= 7d for A); stale C models use only data before C-7d.
4. No feedback: no statistic from any test quarter enters features/labels/fits; fresh models for year Y
   train only before Y-embargo.
5. Fill timing: diagnostic uses open[t+1] (>= t+1); no limit-fill claim; labelled non-executable diagnostic.

## Costs
Diagnostic P&L is gross (no maker/taker/funding); gate costs N/A here. This study measures SKILL decay
(IC + gross diagnostic), not net gate pass.

## Compute
Single process, HGB on CPU (no GPU), 4h panels only (no 1m). 6 stale + 8 fresh HGB fits (~10-60 s each).
Heavy steps via `scripts/heavy_slot.py run --tag oc_staleness --min-free-gb 2.0 -- ...`. Progress printed
at least every 10 minutes.
