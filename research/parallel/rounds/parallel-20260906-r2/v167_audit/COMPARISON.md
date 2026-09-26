# v167 blind audit — COMPARISON (Part B)

Part A was saved before opening `research/.../v167/` (see `replication.json`,
`replicate_v167.py`, `tests/test_v167_audit.py` passing 3/3). This file is Part B.
Write scope: `research/parallel/rounds/parallel-20260906-r2/v167_audit/` +
`tests/test_v167_audit.py` only. No leader files edited.

## Replication vs `v167/v167_result.json`

All diffs are zero (thresholds: IC > 0.01, return > 1pp, DD > 0.5pp):

- IC per anchor (gru p6 vs y6, p42 vs y): diff 0.0000 on all 5 anchors.
  Leader: 2021 (-0.0135, -0.0144), 2022 (-0.0294, -0.0992),
  2023 (0.0343, 0.0049), 2024 (-0.0067, -0.0066), 2025 (0.0913, 0.2635).
  Blind matches exactly.
- Primary `(A+B+D+E)/4`: monthly 2.355 / 2.851 / 3.149, full-path DD
  19.24 / 19.22 / 20.52 — diff 0. Yearly net/DD identical.
- Secondary E alone: monthly 1.228 / 1.363 / 1.499, full-path DD
  23.01 / 23.55 / 25.37 — diff 0. Yearly identical.
- Nothing exceeds any threshold, so no difference needs explaining.

Reference: leader `reference_v154.t25 = (3.515, 19.15)` is a label only,
not part of the comparison gate. Blind primary t25 3.149 sits below v154;
secondary E alone is weak (t25 1.499, DD 25.37).

## Code audit (look-ahead)

- `v167/v167_evaluate.py`: matches the assignment exactly — `p_k = gru_p_k`
  single architecture; inner-merge on `(t, sym)` with `p103` from
  `books_v142`; `v129.vol_predict(p103, f103, ANCHORS, EMBARGO_BARS)` with
  `f103` = non-`y*` columns; `vol42 = pvol` where available;
  `LO = phased(raw_lo(p42))`, `LS94 = phased(raw_ls(mean(p18,p42,p84)))`,
  `LS103 = phased(raw_ls(mean(p6,p18)))`; scales `ext.v92` (LO) / `ext.v94`
  (LS) on the `p103` panel with NaN→1; primary `(A+B+D+E)/4` on the union
  index (missing→0), secondary E; `v144.simulate` rows 0.15 / 0.20 / 0.25.
  No forward returns are touched outside the inner-merged OOS test years.
- `v165/v165_export.py` (shared dataset `nguynchtrai/v165-majors-full-panel`,
  reused by v167 per kernel metadata): exports the audited `v103` panel +
  `v150` options features + `v111` Coinbase features joined on `t` + `v142`
  cross-sectional features (all previously audited as causal, known at bar
  close), plus labels `y6/y18/y(=y42)/y84/fv` defined from future opens
  (labels, embargo-governed). Numbers only, no credentials. Dataset
  `meta.json` (70 features, targets y6/y18/y/y84/fv, 88818 rows) matches the
  kernel `summary.json` (features 70, seq_len 42, 6 seeds).
- `artifacts/kaggle/v167/kernel/train_v167.py` (identical sha256 to
  `v167/kaggle/train_v167.py`): GRU over the last 42 bars —
  `seq_index` builds per-asset windows `t-41..t` (missing start rows →
  zero-pad + mask channel), `gather` clamps padding to zero; window uses
  only bars `<= t`, current bar inclusive, no future bar. Per-target cutoffs
  `anchor − EMB·4h` (78/78/102/144/102 for y6/y18/y/y84/fv) with
  label-realized guard `t+(h+1)·4h < cutoff` (fv 43+1=44, matches v129);
  matches v103/v92/v94 embargoes. Validation = last 365d ending at
  `cut[y6]` with train ending 102 bars earlier (inside training, no test
  leakage); test = `[anchor, anchor+365d)`. Early stopping on masked
  return-target MSE (first 4 heads, fv excluded, weight 0.5 in training loss
  only), patience 5 / max 40 epochs. Robust median/IQR scaling + missing
  indicators fit on train rows only (`prep(X, tr)`). No feature
  recomputation in-kernel, so no new timing risk.

## Verdict

PASS — independent replication reproduces the leader IC table and both
blocks (monthly, yearly, full-path DD) exactly. No look-ahead found in
`v167_evaluate.py`, `v165_export.py` (shared dataset), or `train_v167.py`
under the checked rules (sequence window uses only bars <= t, feature
timing, target cutoffs vs anchor-minus-embargo, early-stopping year inside
training, train-only normalisation). Do not edit leader files.

## Files

- `replication.json` (Part A, blind, frozen), `replicate_v167.py`,
  `tests/test_v167_audit.py` pass 3/3.
