# oc_bookmodel blind pre-run audit (before any Kaggle upload of C1/C2)

Scope: `research/tournament/oc_bookmodel_impl/` (common_impl.py, c1_pooled_tvflow.py,
c2_rank_calibrated.py, kpack_C1/, kpack_C2/, REPORT.md) against
`docs/opencode/BOOKMODEL_PLAN_20261006.md` §(c) common rules + §(e) leakage checklist,
under the AGENTS.md ZERO DATA LEAKAGE rule. No commits, no Kaggle, audited code untouched.
Method: full line-by-line read of the impl + the reused upstream paths it calls
(v92 features/labels/embargo, v103 kline-flow, v94 weights_ls, v142 add_xs, v231 TV(17),
v236 flow formulas on the v240 order-level archive), plus executed checks:
feature_list probe, kpack diff, credential grep (nil), alt-universe count (72, majors
excluded), quarter-start/cutoff asserts, TV + order-flow truncation on 3 anchors
(2021/2022/2023-09-24, max_abs_diff 0.0), synthetic label-mask asserts.
Targeted regression tests: `tests/test_oc_bookmodel_audit.py` (9 tests).

## Check (1) — features at row t use only data ≤ t close
- PASS: TV(17) `v231/tv_indicators.py:27-170` — all rolling/ewm/shift/pivot logic uses
  bars 0..i only; market-structure pivots confirmed after 3 right bars (`:75-87`);
  Ichimoku cloud `.shift(26)` (`:156-157`); VWAP per-period cumsum (`:90-96`); POC
  trailing-180 (`:99-110`). Wiring `common_impl.py:157-161` aligns TV to (t,sym) by
  position; truncation test on real BTC 4h at 3 anchors = bit-identical head (0.0).
- PASS: order whale flow — `common_impl.py:42-43` binds a separate module instance to
  `data/raw/aggflow_20260928_orders` (v240 pattern `v240_order_level_flow.py:42-44`);
  formulas are the same six v236 ratios/rolls (`flow_features.py:27-51`, per-bar
  aggregates + rolling ≤ t, `reindex(bar_open)` `:51` gives NaN outside archive, no
  ffill). Truncation on 3 anchors = 0.0.
- PASS: kline flow `v103:49-65`, v92 base `v92:53-84` (merge_asof backward on
  close_time for daily ribbon `:71` and funding `:75`), xs `v142:33-39` (per-bar
  groupby(t) mean/rank only). Alt bars `common_impl.py:67-95` aggregate 1m inside
  each 4h bar (n_min>=200 completeness is intra-bar, causal); alt funding uses the
  same backward merge_asof via v92.features.
- Note: alt 4h grid is `floor("4h")` UTC (`common_impl.py:79`) while majors come from
  the perp/spot parquets; even under a grid offset every alt feature still uses only
  minutes ≤ the bar close — parity note, not leakage.

## Check (2) — training rows have labels realised before anchor − 7d (h = 3/18/42)
- PASS (C1): `add_targets_multi:98-119` y_h uses opens t+1..t+1+h over causal vol42(t);
  `train_mask:122-129` requires `t < cutoff` AND `t+(h+1)*4h < cutoff` for every h AND
  label notna. `cutoff_for:47-48` = anchor − 7d ≥ 7d max horizon + 1-bar margin.
- PASS-as-mask (C2): `c2_rank_calibrated.py:135-136` requires y42+rank42 notna and
  `t+43*4h < cutoff`; rank itself (`:67-81`) is per-bar cross-sectional (needs all 5
  y42, else NaN → excluded). Mask logic correct — BUT nullified by F1 below.
- PASS (quarterly): `fit_anchor` quarterly branch (`c1:85-87`, `c2:126-131`) sets
  `cutoff = q0 − 7d` per quarter and reuses the same mask. Training for Q2+ sees
  earlier quarters of the test year, but strictly before q0 − 7d, so causal and per
  the v202 plan. Noted explicitly.

## Check (3) — normalisation / calibration fitted on training rows only
- PASS (C1): no fitted scaler/normaliser; HGB takes raw features (NaN-native).
- PASS-in-window / FAIL-by-contamination (C2): `fit_calibrator:84-92` (Platt with
  isotonic fallback) fits on `tr_cal` (`c2:146-151`), which is pre-cutoff — window
  correct. But WARN W1: `tr.sample()` (`c2:143`) shuffles before the `iloc[:k]/[k:]`
  split, so the "last 20% by time" claim is actually a random split (still
  pre-cutoff: no leakage, doc false). And the calibrator is contaminated by F1
  (ranker trained with its own target as a feature).

## Check (4) — quarterly members respect the same cutoffs — PASS (see check 2).

## Check (5) — alt universe fixed Dec-2020 — PASS
- `alt_universe:60-64` reads `data/raw/um_universe_20260930/volume_2020_12.csv`
  (80 rows), filters `days >= 28`, excludes the 5 majors → 72 symbols
  (LTC/LINK/BCH/… head verified); `add_alt_rows:181-222` appends rows only where the
  coin was listed (1m archive presence + `len(b) >= 600`), `asset = 5`. The
  `alts_intraday_20260926` glob fallback (`common_impl.py:71-72`) is a read path only
  and still filtered through the same Dec-2020 list. No survivorship pick-up.

## Check (6) — kpack bundles carry nothing beyond the scripts, no credentials — PASS
- `kpack_C1`/`kpack_C2` contain only the candidate script + `common_impl.py` copies
  (byte-identical to sources, diff exit 0), `kernel_run.py`, metadata template
  (private, no GPU, no internet), `INPUTS.json`, `MANIFEST.txt`. No
  parquet/csv/pkl/npz. Credential grep over the bundle (api_key/secret/BEGIN
  PRIVATE/kaggle.json) = nil. INPUTS are minimal and correct: C1 lists
  xs_universe + spot_majors + alts2020 + um_universe + aggflow_orders + the two D
  member caches; C2 lists the majors-only subset (no alts) + the same D caches.

## Check (7) — 2025-09-24 not used by any selection code path — PASS
- `DEV_ANCHORS` = 2021–2024, `FINAL_ANCHOR` = 2025-09-24 (`common_impl.py:18-19`).
  C1 full writes dev anchors only (`c1:149-156`); the `list(DEV)+[FINAL]` loop
  (`c1:147-148`) is a dead `pass`. C2 full loops dev only (`c2:193-200`). Smokes use
  `DEV_ANCHORS[0]` (`c1:120`, `c2:166`). Selection lives leader-side post-run per the
  docstrings; no threshold/statistic from 2025+ feeds any choice in this code.

## Findings (blocking first)
- F1 [FAIL, pre-Kaggle blocker] C2 label-as-feature: `common_impl.py:251-256`
  `feature_list` excludes only `("y","t","open","sym","bar")` + `y*` prefix, so the C2
  label `rank42` (created `c2_rank_calibrated.py:79`) is returned as a training
  feature; `run()` (`c2:167-168,188-189`) → `fit_anchor` (`c2:149,152-154`) trains the
  HGB ranker (and calibrator) on its own target. In-sample memorisation; OOS rows
  would also carry the label at predict time in this code path. Fix: exclude
  `rank42` (and defensively `pred`) from `feature_list` (or drop label cols before
  the call), then re-run this audit. Kpack copies inherit the bug
  (`kpack_C2/common_impl.py:251`, `kpack_C2/c2_rank_calibrated.py:149`).
- W1 [WARN] calibration split is random, not time-ordered: `c2:141-147` sorts by t,
  then `.sample()` shuffles, then `iloc[:k]/[k:]` splits shuffled order. Pre-cutoff
  (no leakage) but contradicts the "last 20% by time" docstring (`c2:18,144`).
  Fix: split by time before subsampling (or re-sort after sampling).
- W2 [WARN] `feature_list` allowlist is fragile (`common_impl.py:251-256`): any
  non-`y*` label (rank42) or a future `pred` column passes through (probe:
  `['rank42','ret42',...,'pred']`). Recommend an explicit denylist.
- N1 [NOTE] C1 dead loop `c1:147-148` (`for ... + [FINAL_ANCHOR]: pass`) is harmless
  (verified no fit inside) but confusing next to the 2025 rule; consider deleting.
