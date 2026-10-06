# oc_bookmodel_impl — C1/C2 book-model candidates (implementation only, no selection)

Design: `docs/opencode/BOOKMODEL_PLAN_20261006.md` (followed exactly). Pre-registrations are the
module docstrings of `c1_pooled_tvflow.py` (C1) and `c2_rank_calibrated.py` (C2).
Selection happens ONLY on anchors 2021-2024 after the pre-registered Kaggle runs; `2025-09-24`
is scored once for the frozen finalist. Nothing here was fitted or scored beyond the smokes below.

## Files (only these were written)

- `research/tournament/oc_bookmodel_impl/__init__.py`, `common_impl.py` (shared embargo/panel/
  targets/weights/kpack helpers; reuses audited `v92/v94/v103/v142/v231/v236` code paths, no new formulas)
- `research/tournament/oc_bookmodel_impl/c1_pooled_tvflow.py` (C1: pooled 77-coin, TV+order-flow,
  H=(3,18,42) multi-horizon, HGB depth-4 unchanged, annual A/B + quarterly Aq/Bq, books = 0.8×pooled-O1+0.2×D)
- `research/tournament/oc_bookmodel_impl/c2_rank_calibrated.py` (C2: same features/windows/embargo as C1,
  majors only; listwise rank of 5 majors' y42 in [-1,1] + Platt/isotonic calibration on train folds only
  → `v94.weights_ls`; vol_target_scale unchanged)
- `research/tournament/oc_bookmodel_impl/kpack_C1/`, `kpack_C2/` (Kaggle bundle templates, private)
- `tests/test_oc_bookmodel_impl.py` (8 tests)

## How to run

```bat
.venv/Scripts/python.exe -m pytest tests/test_oc_bookmodel_impl.py -q
.venv/Scripts/python.exe research/tournament/oc_bookmodel_impl/c1_pooled_tvflow.py --smoke
.venv/Scripts/python.exe research/tournament/oc_bookmodel_impl/c2_rank_calibrated.py --smoke
.venv/Scripts/python.exe research/tournament/oc_bookmodel_impl/c1_pooled_tvflow.py --build-kpack <dir>
.venv/Scripts/python.exe research/tournament/oc_bookmodel_impl/c2_rank_calibrated.py --build-kpack <dir>
```

Full (Kaggle CPU; leader uploads, do NOT push; needs the INPUTS.json datasets attached):
`--full --out <dir>` trains per-anchor annual + quarterly members and writes
`member_C*_A(_q)_YYYY.parquet` in deployed format (index `t` tz-aware 4h, columns
`BNBUSDT,BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT`). D leg stays byte-identical deployed.
Evaluation = 4-phase reset-metric harness with the R2B1D17BF sleeve fixed (leader side).

## Smoke results (local, ONE anchor 2021-09-24, 3000-row subsample, <10 min)

- C1 smoke: panel (117942, 91) with 2 alts, 83 feats, A_oos=10950 B_oos=10950 rows, **25.1 s**
- C2 smoke: panel (88818, 90) majors-only, 84 feats, rank coverage 0.995, A_oos=10950 B_oos=10950, **18.7 s**
- Causality: truncation test on real BTC 4h TV features, drop last 3 bars → head rows bit-identical
  (`max_abs_diff == 0.0`, PASS); rank-target truncation test PASS; embargo/mask/format tests PASS
- `pytest tests/test_oc_bookmodel_impl.py`: **8 passed** (incl. both smoke CLIs)

## Expected Kaggle runtime (measured samples, no full training)

- HGB depth-4 reference: 20k rows × 26 feats = 0.7 s; majors panel build = 0.8 s; alt 4h cache load = 0.1 s/coin.
- C1 full (~1M pooled rows; 4 dev anchors × 6 fits + 16 quarterly × 6 fits ≈ 120 HGB fits + panel build
  over 72 alts): **~3-6 h on Kaggle CPU** (±2×); GPU NOT needed (HGB CPU-bound; the 5-6 GPU/DL attempts failed).
- C2 full (majors ~90k rows; ~40 HGB fits + Platt/isotonic calibrations): **~0.5-1 h on Kaggle CPU**.
- Evaluation ≈ folds(4) × phases(4) × sim(~4 s) ≈ 1-2 min locally, ~2-4 min on Kaggle CPU.

## Leakage checklist (implementation; blind audit re-checks)

1. Features at t use bars ≤ t close only (audited TV/flow/xs paths; truncation test PASS).
2. Labels realised before cutoff (`t+(h+1)*4h < cutoff` for every h; C2 ranks only where all 5 y42 realised).
3. All fits (HGB, calibration, quarterly) end before anchor/quarter-start − 7 d; alts only where listed before
   the bar; universe fixed Dec-2020.
4. No 2025-09-24+ statistic feeds any choice (smokes use 2021-09-24 only; full writes dev anchors; final scored once).
5. Fill timing unchanged (engine_user minute-5+ trade-through, SL market/TP limit, stop-first).
6. Embargo 7 d ≥ 7 d max horizon (+1-bar margin).
