# v143 blind audit — COMPARISON.md

Scope: `artifacts/kaggle/v143/kernel/train_v143.py`, `research/.../v143/v143_export.py`,
`research/.../v143/v143_evaluate.py`, `research/.../v143/v143_result.json`,
`artifacts/kaggle/v143/dataset/*`, `artifacts/kaggle/v143/local_out/*`.
All writes under `research/parallel/rounds/parallel-20260906-r2/v143_audit/`
(`leakage_check.py`, `export_check.py`, `retrain_20250924_cpu.py`,
`recompute_evaluate.py`, `leakage_report.json`, `export_report.json`,
`pred_2025-09-24_cpu.parquet`, `log_2025-09-24_cpu.json`, `repro_report.json`,
`eval_report.json`, this file) + `tests/test_v143_audit.py`. No leader files edited.

## 1. Leakage review (`leakage_report.json`) — PASS, no leakage found

- Per-target cutoffs as specified: `cut = anchor - e*4h`, `EMB=(78,78,102)` for
  `(y6,y18,y42)`; label mask `times + (h+1)*4h >= cu -> NaN` (`train_v143.py:64-68`).
  Dynamic check on the exported panel: 35/95/335 raw pre-cutoff rows per anchor have
  label ends on/after their cutoff and are masked by construction (y6/y18/y).
- Split as specified: `train_t = times < cut[0]`; validation = last 365d (2190 steps)
  before the y6 cutoff; training steps end 102 bars before validation
  (`tr_idx < val_start - 102*4h`; measured gap 103 bars on the discrete grid, >= 102).
  Split counts match `local_out/summary.json` for all 5 anchors
  (6608/8798/10988/13184/15374 train, 2190 val, 2190 test).
- Normalisation (`mu`/`sd`) from training steps only (`X[tr_idx][pres[tr_idx]]`,
  `:76-79`); max train/val time < anchor <= min test time for every anchor, so no
  test-period data in normalisation. Test window `[anchor, anchor+365d)` exact.
- Per-step asset set is contemporaneous only: presence flag `X[:,:,F]>0`, batch rows
  filtered by `pres.any(1)`, loss masked by `Mt & Pt` (no future rows, no cross-asset
  future; attention padding mask is same-step presence).
- `leaks_found: []`.

## 2. Export check (`export_report.json`) — PASS

- `v143_export.py` only calls `v103.build()`, selects `t/sym + 36 non-y feats +
  y6/y18/y`, casts `t` to int64; no feature math in the exporter.
- `feature_list.json`: sha256 matches panel bytes, 88818 rows, 36 features, 5 syms,
  targets `y6/y18/y` present.
- Independent raw-data replication of the v103 panel (same formulas as audited
  `v103_v105_audit/replicate_v103_v105.py`, no leader import) on 40 sampled times:
  176/176 matched rows (24 early slots absent for late-listed assets on both sides),
  max abs diff 0.0 over all 36 feats + 3 targets — bit-exact.

## 3. Reproducibility (`repro_report.json`) — PASS (within GPU non-determinism)

- Retrained anchor 2025-09-24 on CPU, seeds 0-4, 40 epochs max
  (`pred_2025-09-24_cpu.parquet`, 73.8 s): train/val/test steps 15374/2190/2190 match;
  epochs [4,5,4,5,5] vs leader CUDA [4,4,4,5,5] (same early-stopping regime).
- IC(mean(p6,p18) vs y6): CPU 0.0715 vs saved CUDA 0.0608, diff +0.0107 (< 0.02
  threshold, no explanation required). Saved-IC recomputation (0.0608) equals the
  leader `v143_result.json` 2025 `nn_y6`, confirming the IC definition.
- Expected: NN training is not bit-reproducible across GPU/CPU; the observed jitter
  is normal sampling/optimiser noise, not a code defect.

## 4. Evaluation (`eval_report.json`) — PASS, bit-exact on every number

Independent recompute from saved NN predictions (no leader v143 import; HGB/vol legs
retrained deterministically from raw with audit-helper methods, tranched v133 books,
v110 sequential engine with carry):

- ICs: all 20 values (HGB/NN vs y6/y18 x 5 anchors) exact, incl. negative early NN
  ICs (-0.032/-0.0262 in 2021, -0.019/-0.005 in 2022) turning positive from 2023.
- Causal scale ratios exact: 1.0 / 1.8281579288602596 / 2.2864770055275274 /
  1.176665757296836 / 1.2703450630419584 (prev-year std(HGB)/std(NN), 1 first year).
- Portfolios exact (diff 0.0 everywhere): primary_blend monthly
  2.358/2.15/1.891, fullDD 14.61/16.12/18.07; secondary_nn_only monthly
  2.263/2.048/1.781, fullDD 17.41/17.78/18.24; all 30 yearly nets, all DDs, all
  fills (1994-2190/yr) match `v143_result.json` and `run.log` (sha `a3dfb926...`).
- HGB train rows reproduce the audited v103 counts (33388/33328 ... 77218/77158).

## Verdict

- No look-ahead in training cutoffs/masks/splits/normalisation/asset set; export is
  the audited v103 panel bit-exact; CPU retrain reproduces within expected
  GPU-noise (+0.0107 IC); evaluation numbers recompute bit-exact from saved
  predictions through the causal scale + v133 pipeline.
- Note (not leakage): steps with `t` in `[cut42, cut0)` train y6/y18 while y42 is
  masked — intended per-target-embargo design, loss is masked-MSE over available pairs.
- Result stands as reported: primary_blend 2.358/2.15/1.891 monthly (below v133
  reference 2.44/2.222/1.95); manifest `rejected`, `live_approved:false`,
  audit flags pending leader update. Audit complete; leader files untouched.
