# oc_bookmodel blind re-audit (pre-Kaggle, after fixes)

Scope: `research/tournament/oc_bookmodel_impl/` (common_impl.py,
c1_pooled_tvflow.py, c2_rank_calibrated.py, kpack_C1/, kpack_C2/, REPORT.md)
against `docs/opencode/BOOKMODEL_PLAN_20261006.md` §(c) + §(e) under the
AGENTS.md ZERO DATA LEAKAGE rule. No commits, no Kaggle, audited code untouched.
Method: full line-by-line re-read of the impl + the reused upstream paths it calls
(v92 features/labels/embargo, v103 kline-flow, v94 weights_ls, v142 add_xs,
v231 TV(17), v236 flow formulas on the v240 order-level archive), plus executed
checks: feature_list probe, allowlist-vs-builder-outputs, kpack filecmp diff,
credential grep (nil), alt-universe count (72, majors excluded),
quarter-start/cutoff asserts, TV + order-flow truncation on 3 anchors
(2021/2022/2023-09-24, max_abs_diff 0.0), synthetic label-mask asserts,
split_fit_cal time-order + determinism probe, source scan for sampling and
FINAL_ANCHOR training loops. Regression tests:
`tests/test_oc_bookmodel_reaudit.py` (10 tests, green).
Previous audit: `research/tournament/oc_bookmodel_audit/COMPARISON.md` FAIL on F1.

## Re-check of previous findings (REPORT.md 'Fixes after audit')

- F1 [FIXED, verified] C2 label-as-feature gone. `common_impl.py:279-281`
  explicit `FEATURE_ALLOWLIST` (83 cols from builder outputs only) replaces the
  old y\*-prefix filter; `common_impl.py:284-295` explicit denylist
  (`LABEL_DENY_EXACT` + `LABEL_DENY_PREFIXES`) + module-load assert `:288-290`;
  `feature_list` (`common_impl.py:298-314`) selects by allowlist membership
  (`:307`) and asserts no denied column (`:310-311`) plus an explicit
  rank42/pred assert (`:312-313`). Probe: panel carrying
  y/y3/y18/y42/rank42/pred returns none of them; ranker fit
  (`c2_rank_calibrated.py:166-167`) and calibrator fit (`:168-169`) train on
  allowlist feats only. Kpacks re-synced byte-identical
  (`kpack_C1/common_impl.py:279-313`, `kpack_C2/common_impl.py:279-313`,
  `kpack_C2/c2_rank_calibrated.py:103-176`). Old pin
  `tests/test_oc_bookmodel_audit.py:164-176` (`rank42 in feats`) now fails by
  design, as REPORT.md predicts.
- W1 [FIXED, verified] calibration split is time-last 20%. New
  `split_fit_cal` (`c2_rank_calibrated.py:103-115`, sorts by `t`, `k=max(100,
  0.8n)`, asserts `fit.t.max() <= cal.t.min()`); `fit_anchor`
  (`c2_rank_calibrated.py:160-165`) sorts by `t`, caps with deterministic
  time-last `iloc[-max_rows:]` (`:162`, comment `:158-161`), no `.sample()` in
  code (`:158` is a comment only; code grep nil). Still strictly pre-cutoff.
- W2 [FIXED, verified] explicit denylist (`common_impl.py:284-295`) + per-call
  asserts (`:310-313`); allowlist-vs-builder-outputs probe passes
  (v103.FLOW + v231.TV + v236.FL in allowlist; every v142 BASE/FLOWX xs_/xr_
  in allowlist; y/y42/rank42/pred not members).
- N1 [FIXED, verified] dead `for ... + [FINAL_ANCHOR]: pass` loop deleted;
  C1 full writer loops `C.DEV_ANCHORS` only (`c1_pooled_tvflow.py:147`);
  `FINAL_ANCHOR` count is 0 in both candidate scripts (docstring mentions of
  2025-09-24 scored-once only).

## Check (1) — features at row t use only data <= t close — PASS

- TV(17) `v231/tv_indicators.py:27-170`: rolling/ewm/shift/pivot logic on bars
  0..i only; market-structure pivots confirmed after 3 right bars (`:75-87`);
  Ichimoku cloud `.shift(26)` (`:156-157`); VWAP per-period cumsum (`:90-96`);
  POC trailing-180 (`:99-110`). Wiring `common_impl.py:157-161` aligns TV to
  (t,sym) by position. Truncation on real BTC 4h at 3 anchors = bit-identical
  head (0.0), re-run here.
- Order whale flow: `common_impl.py:42-43` binds a separate module instance to
  `data/raw/aggflow_20260928_orders` (v240 order-level pattern); formulas are the
  same six v236 ratios/rolls (`flow_features.py:27-51`, per-bar aggregates +
  rolling <= t, `reindex(bar_open)` `:51` gives NaN outside archive, no ffill).
  Truncation on 3 anchors = 0.0, re-run here. C1 random `tr.sample`
  (`c1_pooled_tvflow.py:101`, only when `--max-rows` is passed, i.e. smoke) draws
  from pre-cutoff rows only: no leakage (full run passes max_rows=None).
- Kline flow `v103:49-65`, v92 base `v92:53-84` (merge_asof backward on
  close_time for daily ribbon `:71` and funding `:75`), xs `v142:33-39`
  (per-bar groupby(t) mean/rank only, same-bar cross-section = known at close).
  Alt bars `common_impl.py:67-95` aggregate 1m inside each 4h bar (n_min>=200
  completeness is intra-bar, causal); alt funding uses the same backward
  merge_asof via v92.features. Grid note: alt 4h grid is `floor("4h")` UTC
  (`common_impl.py:79`) while majors come from perp/spot parquets; every alt
  feature still uses only minutes <= the bar close — parity note, not leakage.

## Check (2) — training rows realised before anchor - 7d (h = 3/18/42) — PASS

- `add_targets_multi:98-119` y_h uses opens t+1..t+1+h over causal vol42(t);
  `train_mask:122-129` requires `t < cutoff` AND `t+(h+1)*4h < cutoff` for every
  h AND label notna. `cutoff_for:47-48` = anchor - 7d >= 7d max horizon + 1-bar
  margin (for h=42 the realised bound is t+43 bars < cutoff, stricter than 7d).
  C1 `fit_anchor` (`c1_pooled_tvflow.py:92-94`) uses exactly this mask.
- C2 (`c2_rank_calibrated.py:150-151`): `t < cutoff` & y42+rank42 notna &
  `t+43*4h < cutoff`; `rank_target:67-81` is per-bar cross-sectional (needs all
  5 y42, else NaN excluded). Mask logic re-asserted synthetically; F1
  contamination is gone (see above).

## Check (3) — normalisation / calibration on training rows only — PASS

- C1: no fitted scaler/normaliser; HGB takes raw features (NaN-native).
- C2: `fit_calibrator:84-92` (Platt with isotonic fallback) fits on `tr_cal`
  (`c2:168-169`), which `split_fit_cal` guarantees is the time-last 20% of the
  pre-cutoff train frame. No test-year data in either fold.

## Check (4) — quarterly members respect the same cutoffs — PASS

- `fit_anchor` quarterly branch (`c1:85-87`, `c2:141-143`) sets
  `cutoff = q0 - 7d` per quarter (`quarter_starts:51-53`,
  `quarter_end:56-57`) and reuses the same mask. Training for Q2+ sees earlier
  quarters of the test year but strictly before q0 - 7d, causal per the v202
  plan. Re-asserted for all DEV anchors.

## Check (5) — alt universe fixed Dec-2020 — PASS

- `alt_universe:60-64` reads `data/raw/um_universe_20260930/volume_2020_12.csv`,
  filters `days >= 28`, excludes the 5 majors -> 72 symbols (re-counted here;
  head LTC/LINK/BCH). `add_alt_rows:181-222` appends rows only where the coin
  was listed (1m archive presence + `len(b) >= 600`), `asset = 5`. The
  `alts_intraday_20260926` glob fallback (`common_impl.py:71-72`) is a read path
  only and still filtered through the same Dec-2020 list. No survivorship
  pick-up. Train mask excludes any alt row with t >= cutoff.

## Check (6) — kpacks carry nothing beyond the scripts, no credentials — PASS

- `kpack_C1`/`kpack_C2` contain only the candidate script + `common_impl.py`
  copies (byte-identical to sources, filecmp True both), `kernel_run.py`,
  metadata template (private, no GPU, no internet), `INPUTS.json`,
  `MANIFEST.txt`. No parquet/csv/pkl/npz. Credential grep over both bundles
  (api_key/API_KEY/secret/SECRET/BEGIN PRIVATE/kaggle.json) = nil. INPUTS are
  minimal and correct: C1 lists xs_universe + spot_majors + alts2020 +
  um_universe + aggflow_orders + the two D member caches; C2 lists the
  majors-only subset (no alts) + the same D caches. D caches are the deployed
  byte-identical leg per the plan, not post-cutoff training data.

## Check (7) — 2025-09-24 not used by any training/selection code path — PASS

- `DEV_ANCHORS` = 2021-2024, `FINAL_ANCHOR` = 2025-09-24
  (`common_impl.py:18-19`). C1 full writes dev anchors only (`c1:147-153`); C2
  full loops dev only (`c2:211-217`). Smokes use `DEV_ANCHORS[0]` (`c1:120`,
  `c2:184`). `FINAL_ANCHOR` appears 0 times in either candidate script code.
  Selection lives leader-side post-run per the docstrings; no threshold or
  statistic from 2025+ feeds any choice in this code.
