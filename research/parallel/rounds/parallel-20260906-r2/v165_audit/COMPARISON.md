# v165 blind audit — COMPARISON (Part B)

Part A was saved before opening `research/.../v165/` (see `replication.json`,
`replicate_v165.py`). This file is Part B.

## Replication vs `v165/v165_result.json`

All diffs are zero (thresholds: IC > 0.01, return > 1pp, DD > 0.5pp):

- IC per anchor (mlp_plr/ft p6 vs y6, p42 vs y): diff 0.0000 on all 5 anchors.
- Primary `(A+B+D+E)/4`: monthly 2.575 / 3.109 / 3.409, full-path DD
  14.92 / 17.68 / 19.22 — diff 0. Yearly net/DD identical.
- Secondary E alone: monthly 2.075 / 2.349 / 2.525, full-path DD
  15.84 / 19.66 / 22.95 — diff 0. Yearly identical.
- Nothing exceeds any threshold, so no difference needs explaining.

Reference: leader `reference_v154.t25 = (3.515, 19.15)` is a label only,
not part of the comparison gate.

## Code audit (look-ahead)

- `v165/v165_evaluate.py`: matches the assignment exactly — `p_k` = mean of
  the two architectures; inner-merge on `(t, sym)` with `p103` from
  `books_v142`; `v129.vol_predict(p103, f103, ANCHORS, EMBARGO_BARS)` with
  `f103` = non-`y*` columns; `vol42 = pvol` where available; `LO = phased(
  raw_lo(p42))`, `LS94 = phased(raw_ls(mean(p18,p42,p84)))`, `LS103 = phased(
  raw_ls(mean(p6,p18)))`; scales `ext.v92` (LO) / `ext.v94` (LS) on the
  `p103` panel with NaN→1; primary `(A+B+D+E)/4` on the union index
  (missing→0), secondary E; `v144.simulate` rows 0.15 / 0.20 / 0.25.
  No forward returns are touched outside the inner-merged OOS test years.
- `v165/v165_export.py`: exports the audited `v103` panel + `v150`
  options features + `v111` Coinbase features joined on `t` + `v142`
  cross-sectional features (all previously audited as causal, known at bar
  close), plus labels `y6/y18/y(=y42)/y84/fv` defined from future opens
  (labels, embargo-governed). Numbers only, no credentials.
- `v165/kaggle/train_v165.py`: per-target cutoffs `anchor − EMB·4h`
  (78/78/102/144/102) with label-realized guard `t+(h+1)·4h < cutoff`
  (matches v103/v92/v94 embargoes); validation = last 365d of training
  time ending at the cutoff with train ending 102 bars earlier
  (inside training, no test leakage); early stopping on masked
  return-target MSE (fv excluded, weight 0.5 in training loss only);
  robust median/IQR scaling + missing indicators fit on train rows only.
  No feature recomputation in-kernel, so no new timing risk.

## Verdict

PASS — independent replication reproduces the leader IC table and both
blocks (monthly, yearly, full-path DD) exactly. No look-ahead found in
`v165_evaluate.py`, `v165_export.py`, or `train_v165.py` under the
checked rules (feature timing, target cutoffs vs anchor-minus-embargo,
early-stopping year inside training, train-only normalisation).
Do not edit leader files.
