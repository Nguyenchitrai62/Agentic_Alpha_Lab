# Kaggle prep 2026-10-06 — bookmodel C1/C2 (staging only, leader uploads)

Staged, never pushed. No `kaggle` CLI create/push call was made, no credentials
touched, `.env` never read or copied. Fixes from REPORT.md (F1 allowlist,
W1 time-last split, W2 denylist, N1 dead-loop removal) verified present in the
freshly built kpacks below.

## 1. Kpacks (`--build-kpack` output, byte-identical to fixed source)

- `artifacts/kaggle_stage/C1/` (27,761 B): c1_pooled_tvflow.py (10,642),
  common_impl.py (16,032), kernel_run.py (116), kernel-metadata.json.template
  (310), INPUTS.json (562), MANIFEST.txt (99). Kernel `oc-c1-pooled-tvflow`.
- `artifacts/kaggle_stage/C2/` (30,591 B): c2_rank_calibrated.py (13,534),
  common_impl.py (16,032), kernel_run.py (118), kernel-metadata.json.template
  (314), INPUTS.json (490), MANIFEST.txt (103). Kernel `oc-c2-rank-calibrated`.

## 2. Datasets needed (from each INPUTS.json; local source path | type | files | bytes)

C1 (C1-pooled-tvflow), total ~9,557,440,065 B (~9.56 GB), 1,068 files:
- `data/raw/xs_universe_20260924` | dir | 572 | 120,503,093
- `data/raw/spot_majors_20260925` | dir | 22 | 18,233,570
- `data/raw/alts2020_intraday_20260930` | dir | 445 | 9,412,042,547
- `data/raw/um_universe_20260930` | dir | 1 | 2,448
- `data/raw/aggflow_20260928_orders` | dir | 25 | 6,571,814
- `artifacts/research/engine_real/members_v154.parquet` | file | 1 | 1,510,253
- `artifacts/research/engine_real/members_quarterly_D.parquet` | file | 1 | 581,341

C2 (C2-rank-calibrated), total ~147,399,581 B (~0.147 GB), 621 files:
- `data/raw/xs_universe_20260924` | dir | 572 | 120,503,093
- `data/raw/spot_majors_20260925` | dir | 22 | 18,233,570
- `data/raw/aggflow_20260928_orders` | dir | 25 | 6,571,814
- `artifacts/research/engine_real/members_v154.parquet` | file | 1 | 1,510,253
- `artifacts/research/engine_real/members_quarterly_D.parquet` | file | 1 | 581,341

Note: C1's 9.4 GB alts intraday dir dominates; leader may need a sharded upload.

## 3. Dataset folders (metadata templates, `<owner>` placeholder kept)

- `artifacts/kaggle_stage/C1_data/dataset-metadata.json`: title
  `oc-c1-pooled-tvflow-data`, id `<owner>/oc-c1-pooled-tvflow-data`, private
  (no `--public` on create).
- `artifacts/kaggle_stage/C2_data/dataset-metadata.json`: title
  `oc-c2-rank-calibrated-data`, id `<owner>/oc-c2-rank-calibrated-data`, private.
- Populate each folder with the §2 paths (mirrored repo-relative layout
  recommended) before `datasets create`.

## 4. Kernel folders (private CPU, no GPU, no internet)

- `artifacts/kaggle_stage/C1_kernel/`: kernel-metadata.json (id
  `<owner>/oc-c1-pooled-tvflow`, is_private true, enable_gpu false,
  enable_internet false, dataset_sources `<owner>/oc-c1-pooled-tvflow-data`),
  kernel_run.py with `_kaggle_default_argv()` (finds dataset under
  `/kaggle/input` by sentinel search, symlinks §2 paths, runs
  `c1_pooled_tvflow.py --full --out /kaggle/working/out_C1`),
  plus byte-identical c1_pooled_tvflow.py + common_impl.py.
- `artifacts/kaggle_stage/C2_kernel/`: same shape for
  `<owner>/oc-c2-rank-calibrated` + dataset `<owner>/oc-c2-rank-calibrated-data`,
  runs `c2_rank_calibrated.py --full --out /kaggle/working/out_C2`.
- Open item for leader: kpack code needs `research/parallel/rounds/
  parallel-20260906-r2` (v92/v94/v103/v142/v231/v236/v144) at runtime; not in
  the kpack. Attach as code or extend the kernel bundle before push.

## 5. Secret scan

22 staged files scanned for `KAGGLE|API_KEY|SECRET|TOKEN|password` values and
`.env` content: no secret values found. Only benign hits: the word "kaggle" in
docstrings/comments and `/kaggle/input|working` paths (0 `key= value` hits).

## 6. Leader upload sequence (exact; NOT executed here)

Replace `<owner>` with the private account in all four metadata files first.

```
kaggle datasets create -p artifacts/kaggle_stage/C1_data
kaggle datasets status <owner>/oc-c1-pooled-tvflow-data
kaggle datasets create -p artifacts/kaggle_stage/C2_data
kaggle datasets status <owner>/oc-c2-rank-calibrated-data
kaggle kernels push -p artifacts/kaggle_stage/C1_kernel
kaggle kernels push -p artifacts/kaggle_stage/C2_kernel
```

Poll each `datasets status` until ready before the matching `kernels push`.

## 7. Expected runtime (REPORT.md, Kaggle CPU; GPU not needed, HGB CPU-bound)

- C1 full (~1M pooled rows, ~120 depth-4 HGB fits + panel build): ~3-6 h (±2x).
- C2 full (majors ~90k rows, ~40 fits + calibrations): ~0.5-1 h.
- Evaluation (4 folds x 4 phases x ~4 s sim): ~2-4 min on Kaggle CPU.
