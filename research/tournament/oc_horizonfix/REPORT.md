# oc_horizonfix REPORT — contemporaneous-return leak check in two IC yardsticks

Assignment `docs/opencode/OPENCODE_W_oc_horizonfix.md` (+ common header).
Method pre-registered in PLAN.md BEFORE any outcome (one clarification
logged at the bottom; definitions unchanged).

## 1. Timing audit (Task 1, code-cited; `audit_timing.py` reproduces it)

- (a) `preds_*.csv` rows: `open_time` T = bar OPEN ts (standard
  00/04/08/12/16/20 UTC grid; `presamplebook.py:65-85` builds bars keyed by
  floored open). Features at row T use bars `0..T` INCLUDING `close[T]`:
  `tv_indicators.py:1-5` docstring ("known at the close of bar i"),
  `flow_features.py:1-5` ("row of bar t is known at its close"),
  `v111_coinbase_premium.py:3` ("known at the bar close T+4h").
  The members' own labels prove the executable base is the NEXT bar open:
  `fwd=log(o[T+1+H]/o[T+1])` (`presamplebook.py:96-108`,
  `presampleflow.py:96-108`, `v103:74-80`) and
  `r_next=o[T+2]/o[T+1]-1` (`presamplebook.py:121-130`,
  `presampleflow.py:131-135`, `v144_deploy_v3.py:82` engine earns
  `books.shift(2)*(o/o.shift(1)-1)`). => prediction at T is available at
  T+4h (close of bar T).
- (b) Book caches: `v103.build` sets `x["t"]=b["open_time"]` with features
  "from bars closed at t" (`v103:6-12`); `research_books_d2`
  (`forward_v205.py:82-90`) only reindexes/fillna-blends (no time shift);
  `compute_bookichorizon.py:65-82` scored `open[T+h]/open[T]` from base
  `open[T]`. => book row at T is the decision available at T's close.
- VERDICT: old yardstick `y_old[T,h]=(open[T+h]/open[T]-1)/sigma[T]`
  includes bar T's own move `open[T]->open[T+1]` (1 full bar), which is
  already known to the features via `close[T]` (~= `open[T+1]`):
  contemporaneous leak in the YARDSTICK (strategies/engine fills
  unaffected — they trade from `o[T+1]`). Corrected
  `y_corr[T,h]=(open[T+4h+h]/open[T+4h]-1)/sigma[T+4h]`
  (`t_trade`=first bar open at/after availability). Leak weight ~1/h, so
  h=1 is worst, h=42 negligible.

## 2. Old vs corrected IC tables (Task 2, `recompute.py` -> `results.json`)

Old yardstick reproduced EXACTLY (max |published-old| pooled diff 0.0000
both studies). Histories, test sets, sigma, horizons {1,2,6,18,42}, metrics
identical; point ICs only (no bootstrap; old CIs from published results).

### 2a. Presample TV (rebuilt TV-only): the h=1 "skill" was 100% leak

Pooled IC old -> corrected:

| h | 2019-03 | 2019-09 | 2020-03* | 2021 | 2022 | 2023 | 2024 |
|---|---|---|---|---|---|---|---|
| 1 | +0.133->-0.011 | +0.151->-0.003 | +0.137->-0.027 | +0.142->-0.006 | +0.138->+0.002 | +0.129->+0.001 | +0.175->+0.008 |
| 2 | +0.110->+0.013 | +0.124->+0.013 | +0.088->-0.021 | +0.107->+0.005 | +0.106->+0.007 | +0.092->-0.001 | +0.132->+0.006 |
| 6 | +0.084->+0.015 | +0.102->+0.031 | +0.053->-0.012 | +0.074->+0.011 | +0.076->+0.016 | +0.059->-0.001 | +0.102->+0.026 |
| 18 | +0.034->-0.007 | +0.080->+0.035 | +0.035->-0.007 | +0.065->+0.028 | +0.093->+0.053 | +0.028->-0.013 | +0.105->+0.056 |
| 42 | +0.021->-0.000 | +0.070->+0.045 | +0.033->+0.008 | +0.042->+0.012 | +0.050->+0.024 | +0.000->-0.025 | +0.016->-0.020 |

TS mean collapses identically (h=1: +0.13..+0.17 -> -0.03..+0.01, all 7 y);
XS h=1 (+0.05..+0.10, positive all 7 y) -> ~0 (-0.014..+0.012). At h=42
old~=new everywhere (leak is 1/42 of the window) — the presamplebook "~0
at 7d" finding is unaffected.

### 2b. Presample FLOW / PREMIUM / BLEND: ~0 before, ~0 after (survives)

FLOW pooled h=1: +0.018/-0.006/+0.015/+0.042/+0.009/+0.030/+0.036 ->
+0.004/-0.014/-0.001/+0.003/-0.016/-0.017/-0.004. Its weak reference-year
h=1 trace (2021/2023/2024 CIs excluded 0) VANISHES corrected — it was
leak-adjacent, not forward skill. PREMIUM/BLEND deltas are all <= 0.03
(PREMIUM h=42: -0.168->-0.168 etc.). XS stays ~0 / structurally void.
Verdict "NO stable short-horizon skill" for these three families STANDS,
now stronger (the only nominally-positive cells are gone too).

### 2c. Deployed book (oc_bookichorizon): essentially unchanged (survives)

FINAL pooled h=1: +0.018/+0.018/+0.023/+0.024/(recent +0.036) ->
+0.017/+0.018/+0.018/+0.017/(+0.033); h=2/6/18 deltas <= 0.005;
h=42: +0.144/-0.036/+0.042/+0.085/(+0.107) ->
+0.143/-0.041/+0.037/+0.085/(+0.104) (2022 still flips).
All 10 series dev4 h=1 means shift by only -0.001..-0.004, still 4/4 dev
years positive for every member; TS≈pooled shape and XS ~2-3x smaller
unchanged. The deployed book's predictions correlate ~0 with the
contemporaneous bar (blended/sized decisions), so the leak never inflated
them: "skill lives at h=1..18 in TS, not at h=42" STANDS as genuine
forward skill (tiny, CI-covering-0 magnitudes unchanged).

## 3. Synthetic proof (Task 3, `tests/test_oc_horizonfix.py`, 4 tests pass)

3000 iid 4h opens (seed 0); feature = current bar's own move
`close[T]/open[T]-1` (known at close[T]; `close[T]==open[T+1]` exact
sampling): old h=1 IC = +0.9998 (>0.5), corrected IC = -0.002 (|.|<0.1).
Genuinely predictive feature (next bar's move): corrected IC = +0.9998
(>0.5 — not a null machine). Plus a hand-checked 6-open case and a
truncation/causality test (tail NaN edges shift by exactly 1 bar;
far-future perturbation leaves row T bit-identical; sigma warm-up NaN).

## Leakage / execution statement

Fits frozen before anchors (inputs read-only); sigma causal trailing-360
(min120); targets are scoring labels only; no test-year or most-recent-year
statistic entered any choice (no refits, no thresholds, no CIs recomputed).
No fills claimed (IC diagnostic). `pytest tests/test_oc_horizonfix.py`: 4 passed.

## Post-hoc clarification (definition unchanged, index made explicit)

PLAN's synthetic line said `f[T]=r1[T]`; strictly, an OPEN-to-open feature
`open[T]/open[T-1]-1` would NOT inflate (it is last bar's move). The leak
mechanism is via CLOSE: `close[T]`~= `open[T+1]`, so the inflating feature
is the bar's own move `close[T]/open[T]-1 == y_old[T,1]` numerator. The test
uses the close-based form (matches real TV features that ingest close[T]).

## Verdict (tiếng Việt, kết luận chính)

- Kết luận "chỉ họ TV có skill ngắn hạn (+0.13..+0.18 ở h=1)" của oc_presampleshort KHÔNG còn: hiệu chỉnh còn ~0 cả 7 năm (TS và XS cùng về 0) — toàn bộ là leak đồng thời qua close[T]; FLOW/PREMIUM/BLEND vẫn ~0 nên kết luận NO của chúng càng chắc, kể cả trace h=1 yếu ở 2021/2023/2024 cũng biến mất.
- Kết luận của oc_bookichorizon NGUYÊN VẸN: book G2 dịch ≤0.008 mọi ô, skill TS ngắn hạn +0.02..+0.04 dương 4/4 năm dev và h=42 vẫn đảo 2022 — là forward skill thật (dù nhỏ), không phải leak; không đổi deployment, và không mở hướng TV-horizon-ngắn nào từ presample nữa.
