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

## 8. Final (ops_kaggle_final, 2026-10-06 — C2 first, then C1; staged only, never pushed)

No `kaggle` CLI create/push call was made, no credentials touched, `.env` never
read or copied. Writes were confined to `artifacts/kaggle_stage/` except this
section. The §4 open item (unbundled `research/parallel/rounds/parallel-20260906-r2`
runtime imports) is closed below; dry-runs also closed three missing-data gaps
in §2 (found only by running the kernels, never by guessing).

### 8.1 Kernel code bundle (both kernels, import paths preserved)

`common_impl.py` resolves `RD = research/parallel/rounds/parallel-20260906-r2`
relative to the kernel cwd, so the bundle mirrors that layout inside each
kernel folder (16 files, ~128 KB of code; `diff -r` identical between kernels):

- `research/parallel/rounds/parallel-20260906-r2/v92/v92_pooled_hgb_vt.py`
- `v94/v94_long_short_ensemble.py`, `v99/v99_candidate.py`,
  `v103/v103_flow_short_horizon.py`, `v104/v104_candidate.py`,
  `v110/v110_dd_governor.py`, `v113/v113_longer_history.py`,
  `v114/v114_bitstamp_history.py`, `v115/v115_candidate.py`,
  `v125/v125_tranching.py`, `v129/v129_vol_forecast_sizing.py`,
  `v135/v135_limit_offset.py`, `v142/v142_cross_sectional_features.py`,
  `v144/v144_deploy_v3.py`, `v231/tv_indicators.py`, `v236/flow_features.py`
- Closure verified from the kernel dir: `common_impl.load_stack()` returns 7
  modules and the full `v144` chain (`v142/v135/v129/v125/v115/v114/v113/v110/
  v104/v103/v99/v94/v92`) imports cleanly; the extended-history loader is live
  when its data is wired (no fallback triggered in either dry-run).

`kernel_run.py` (both kernels) keeps real-Kaggle behaviour unchanged
(`--full` to `/kaggle/working/out_C*` via sentinel search) and adds, for local
dry-runs only: `$KAGGLE_INPUT_BASE` / `$KAGGLE_WORKING_BASE` overrides honoured
by `_find_dataset_root()` / `_kaggle_default_argv()`, a `--smoke` flag forwarded
to the candidate (`--smoke --out …`), `--max-rows`/`--max-alts` passthroughs
(C1), whole-`$KAGGLE_INPUT_BASE` search for the split alts dataset (C1), and a
copy fallback when Windows blocks symlinks. C1 `kernel-metadata.json` now lists
both datasets (small + alts).

### 8.2 Missing-data fixes found by the dry-runs (all now in the datasets)

§2 omitted four runtime inputs the code actually reads (dry-run failures, fixed
by copying, repo-relative layout kept; no source logic changed):

- `data/raw/ma_ribbon_20260924/` (~6.9 MB): `v92.load_asset("BTCUSDT")` reads
  `klines_4h/klines_1d/funding` from here (C2 failed without it).
- `data/raw/coinbase_20260925/` (~15 MB) + `data/raw/bitstamp_20260925/`
  (~1.1 MB): `v113/v114` extended-history loader (`cb_bars`/`cb_bars_ext`) reads
  `BTC-USD_1h[_pre2017]`, `ETH-USD_1h[_pre2017]`, `btcusd_1h_2011_2015` (C2
  failed without them after the ma_ribbon fix).
- `data/raw/alts_intraday_20260926/` (~1.0 GB, 43 files: LTC/LINK/ADA/AVAX/DOGE/
  TRX): `common_impl.alt_bars()` falls back here when `alts2020_…` has no file
  for the symbol. The C1 smoke top-2 (`LTCUSDT`, `LINKUSDT`) live ONLY here, so
  C1 full needs BOTH alts dirs (~9.8 GB total), not just the §2 `alts2020` dir.

### 8.3 Final folder paths and sizes (local `du -sh`, file counts)

- `artifacts/kaggle_stage/C2_kernel/` (173 KB, 20 files): `c2_rank_calibrated.py`
  + `common_impl.py` + `kernel_run.py` (fake-kaggle/`--smoke` aware, INPUTS now
  8 paths incl. ma_ribbon/coinbase/bitstamp) + `kernel-metadata.json` (1 dataset
  source) + `research/…` (16 files above).
- `artifacts/kaggle_stage/C1_kernel/` (169 KB, 20 files): same shape with
  `c1_pooled_tvflow.py`; `kernel_run.py` INPUTS now 10 paths (small 8 + both alts
  dirs); `kernel-metadata.json` `dataset_sources` =
  `["<owner>/oc-c1-pooled-tvflow-data", "<owner>/oc-c1-alts2020-intraday"]`.
- `artifacts/kaggle_stage/C2_data/` (165 MB, 637 files + `dataset-metadata.json`):
  `data/raw/{xs_universe_20260924,ma_ribbon_20260924,spot_majors_20260925,
  coinbase_20260925,bitstamp_20260925,aggflow_20260928_orders}/` +
  `artifacts/research/engine_real/{members_v154,members_quarterly_D}.parquet`
  (repo-relative layout).
- `artifacts/kaggle_stage/C1_data/` (165 MB, 638 files + metadata): same as
  C2_data + `data/raw/um_universe_20260930/` (the SMALL dataset; no alts).
- `artifacts/kaggle_stage/C1_data_alts/` (5 KB: `dataset-metadata.json` slug
  `<owner>/oc-c1-alts2020-intraday` + `UPLOAD.txt`): staging for the ALTS
  dataset — populate with `data/raw/alts2020_intraday_20260930/` (445 files,
  ~8.8 GB) + `data/raw/alts_intraday_20260926/` (43 files, ~1.0 GB) before
  `datasets create` (full alts NOT copied locally; dry-run used a 14-file
  subset, see §8.4).
- Reference kpacks untouched: `artifacts/kaggle_stage/C1/` (36 KB),
  `artifacts/kaggle_stage/C2/` (40 KB).

### 8.4 Fake-Kaggle dry-runs (both reached the end and wrote member parquets)

Tree: `artifacts/kaggle_stage/fake_kaggle/input/<dataset-slug>/…` (mirrored
layout) + `…/work_C2/`, `…/work_C1/` (copies of the kernel folders; cwd there so
`RD` resolves to the BUNDLED code and all `artifacts/…` cache writes stay under
`artifacts/kaggle_stage/`). Run with `$KAGGLE_INPUT_BASE`/`$KAGGLE_WORKING_BASE`
pointing at the fake tree plus `--smoke`.

- C2: input `oc-c2-rank-calibrated-data` (165 MB copy of C2_data); work
  `work_C2` (wired copies + `out_C2`, 165 MB). Last log lines:
  `C2 wired data/raw/coinbase_20260925 -> …/oc-c2-rank-calibrated-data/…`,
  `C2 wired data/raw/bitstamp_20260925 -> …`,
  `C2 smoke anchor=2021-09-24 panel=(88818, 90) feats=83 rank_cov=0.995
  A_oos=10950 B_oos=10950 53.4s`.
  Wrote `work_C2/out_C2/` (88 KB): `member_C2_A_smoke.parquet` (42 KB,
  (2190, 5)), `member_C2_B_smoke.parquet` (41 KB, (2190, 5)); index `t` tz-aware
  4h from 2021-09-24, columns `BNBUSDT,BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT`.
- C1: inputs `oc-c1-pooled-tvflow-data` (165 MB small copy) +
  `oc-c1-alts2020-intraday` (360 MB subset: `LTCUSDT_1m_*.parquet` +
  `LINKUSDT_1m_*.parquet`, 7 files each, from `alts_intraday_20260926`, plus an
  (empty) `alts2020_intraday_20260930/` dir with `manifest.json` so wiring
  succeeds); work `work_C1` (527 MB with wired copies + `out_C1`). Last log lines:
  all 11 `C1 wired …` lines (both mounts, incl. both alts dirs) then
  `C1 smoke anchor=2021-09-24 panel=(117942, 91) feats=83 A_oos=10950
  B_oos=10950 38.6s` (matches REPORT smoke shape; 83 feats = post-F1 allowlist).
  Wrote `work_C1/out_C1/` (80 KB): `member_C1_A_smoke.parquet` (37 KB,
  (2190, 5)), `member_C1_B_smoke.parquet` (37 KB, (2190, 5)), same deployed
  format.

### 8.5 Leader upload sequence (exact; NOT executed here — split update)

Replace `<owner>` in all FIVE metadata files first
(`C1_data`, `C1_data_alts`, `C2_data` dataset metadatas + `C1_kernel`,
`C2_kernel` kernel metadatas; all private, CPU, no internet).

```
kaggle datasets create -p artifacts/kaggle_stage/C2_data
kaggle datasets status <owner>/oc-c2-rank-calibrated-data
kaggle kernels push -p artifacts/kaggle_stage/C2_kernel
kaggle datasets create -p artifacts/kaggle_stage/C1_data
kaggle datasets status <owner>/oc-c1-pooled-tvflow-data
kaggle datasets create -p artifacts/kaggle_stage/C1_data_alts
kaggle datasets status <owner>/oc-c1-alts2020-intraday
kaggle kernels push -p artifacts/kaggle_stage/C1_kernel
```

Poll each `datasets status` until ready before the matching `kernels push`;
the C1 kernel needs BOTH datasets attached. C2 full on Kaggle CPU ~0.5-1 h, C1
full ~3-6 h (±2x); `--smoke` above is minutes and already green.
