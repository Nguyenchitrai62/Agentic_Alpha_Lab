# ops_kaggleengine REPORT (2026-10-06): generic Kaggle CPU bundle for 4-phase engine studies

## What was built (no commits, no uploads; workers never touch credentials)

- `artifacts/kaggle_stage/engine_kernel/`: `kernel_run.py` (dataset wiring like
  C2's `kernel_run`, runs a job file's rows sequentially), `engine_harness.py`
  (row-driven port of the `oc_expiry4p` worker: v421 R2B1D17BFG2 wiring,
  `phase_offset_full` prep + `pipe_setup("v321", agents on)` + kd corr-size +
  bear-book filter + G gross cap + `win_start=5`, gate costs, reset-metric
  scoring via `reset_metric.year_reset` + `v388.mix` full-path DD),
  `hooks.py` (`base` / `bear` / `bear_expiry` + `<module>.py:<fn>` custom tilt
  modules bundled next to the job file), `job_example.json` (reproduces the two
  `oc_expiry4p` rows), `build_bundle.py` (resolves the code closure, writes the
  self-extracting `kaggle_entry.py`), `kaggle_entry.py` (built, 196090 bytes;
  the ONLY file the leader uploads as a script kernel), `kernel-metadata.json`
  (dataset source `<owner>/oc-engine-4p-data`), `INPUTS.json`.
- `artifacts/kaggle_stage/engine_data/`: `dataset-metadata.json` (placeholder
  owner `<owner>`) + `MANIFEST.json` (exact repo-relative paths + byte sizes;
  multi-GB data is NOT copied, only listed).
- `tests/test_ops_kaggleengine.py`: 6 tests, all passing (see below).

## Minimal harness inputs (measured 2026-10-06; total 980519037 bytes = 935.1 MiB)

| group | paths | bytes |
|---|---|---|
| 1m klines BTC (8 files `klines_1m_20*.parquet`) | `data/raw/btc_intraday_20260924/` | 223126429 |
| 1m klines majors (29 files `{BNB,ETH,SOL,XRP}USDT_1m_20*.parquet`) | `data/raw/majors_intraday_20260924/` | 749779487 |
| book grid cache + O1/D members (8 parquets) | `artifacts/research/engine_real/` | 5300421 |
| per-shift hidden R2 tables (4 parquets) | `.../v376/tables_hidden/` | 2313112 |
| code closure (39 `.py`, zip 146612 bytes) | embedded in `kaggle_entry.py` | 334296 (unpacked) |

Code closure (from `build_bundle.py --check`): `engine_user`, `engine_real`,
`v221`, `v216`, `v215`, `v214`, `v213`, `v204`, `v172`, `v171`, `v170`, `v169`,
`v144`, `v142`, `v135`, `v129`, `v125`, `v115`, `v114`, `v113`, `v111`,
`v103`, `v104`, `v110`, `v99`, `v94`, `v92`, `v154`, `v151`, `v150`,
`history_tm` (v321 pipe), `forward_v205` (research_books_d2), `carry_lab`,
`phase_offset_dips` (minutes), `phase_offset_full` (prep/pipe_setup),
`reset_metric`, `v388` (mix), `v421`, `oc_expiry4p` (reference wiring).
Funding is formulaic (adverse longs 0.0001, shorts zero) — no funding file.

## Job file schema

`{"name", "rows": [{"name", "book_hook", "sleeve"}]}`; `book_hook` in
`base|bear|bear_expiry|<module>.py:<fn>` (applied after the bear filter, before
the shifted-clock ffill); `sleeve` keys `rule/k/kd/G/bear/cool/bm/xrp` with the
`oc_expiry4p` RUNS meaning. Outputs per run dir: `results.json` + `runs.pkl`
(per-phase equity legs `t/eq/eq_min` + book/rung exits).

## Expected Kaggle runtime per row (from local timing, no new heavy run)

- Reference: `oc_expiry4p/results.json` `seconds=537` for 2 rows x 4 shifts
  (8 engine legs) on this host => ~67 s/leg, ~269 s/row.
- Smoke measured here: 60-bar 1-shift leg ~30 s wall (imports + 1-year 1m
  load dominate; engine itself is seconds).
- Estimate for Kaggle CPU (slower cores + ~1 GB dataset attach): ~2-3 min/leg
  => ~8-12 min/row; the 2-row example job => ~20-30 min total. Rows run
  strictly sequentially (one engine process at a time); legs need ~0.5 GB.

## Exact leader commands

```powershell
# 1. stage the dataset (copy EXACTLY the MANIFEST.json paths, mirrored layout)
# 2. create the Kaggle dataset (private) from artifacts/kaggle_stage/engine_data/
#    after replacing <owner> in dataset-metadata.json with your username
# 3. create the script kernel (private, CPU, no internet) uploading ONLY
#    artifacts/kaggle_stage/engine_kernel/kaggle_entry.py, attach the dataset
# 4. job file: put job.json next to kaggle_entry.py before upload
#    (default job_example.json reproduces the oc_expiry4p rows), run, then
#    download /kaggle/working/out_eng/{results.json,runs.pkl}
# local smoke (subset, must reproduce the direct harness call exactly):
$env:KAGGLE_INPUT_BASE="C:\TRAI_NC\Source_code\Agentic_Alpha_Lab"; $env:KAGGLE_WORKING_BASE="<tmp>\work_eng"
$env:ENGINE_SHIFTS="0"; $env:ENGINE_SMOKE_START="2024-03-01"; $env:ENGINE_SMOKE_BARS="60"; $env:ENGINE_NO_SCORE="1"
.venv/Scripts/python.exe artifacts/kaggle_stage/engine_kernel/kernel_run.py --job <job.json>
# rebuild after any code change (never hand-edit kaggle_entry.py):
.venv/Scripts/python.exe artifacts/kaggle_stage/engine_kernel/build_bundle.py
.venv/Scripts/python.exe artifacts/kaggle_stage/engine_kernel/build_bundle.py --check
# tests:
.venv/Scripts/python.exe -m pytest tests/test_ops_kaggleengine.py -q
```

Fake-kaggle equivalent: stage a SYMLINK tree of the MANIFEST paths under
`artifacts/kaggle_stage/fake_kaggle/input/oc-engine-4p-data/` (mirrored
repo-relative layout) and point `KAGGLE_INPUT_BASE` at the `input` dir.

## Verification done here

- `job_example.json` rows equal `oc_expiry4p.RUNS` exactly; `hooks.EXP` frame
  equals `oc_expiry4p.EXP`; `bear_expiry` output equals the manual halving on
  the real book grid (test asserts all three).
- `kaggle_entry.py` extracts to a tree byte-identical to the repo files.
- Smoke (shift 0, 60 bars from 2024-03-01): `kernel_run.main` output
  (`results.json` sans `seconds`, `runs.pkl`) is byte/compare-equal to the
  direct `engine_harness.run_rows` call on the same subset.
- Reproduction gate for any full run: the BASE row must equal the v421
  `run.log` row (5y 5.41 %/mo, max yearly DD 16.91, full-path DD 16.82);
  else stop and report (same rule as `oc_expiry4p`).

## Leakage / causality notes (blind-audit checklist)

- Books/members/R2 tables are frozen pre-anchor fit artifacts used as inputs;
  no 2025-09-24+ statistic feeds any choice (2025 is scored, never selected).
- Custom tilt modules MUST be causal (row t uses only data at that bar close);
  the harness applies hooks before the shifted-clock ffill (no look-ahead).
- Row selection across studies stays on anchors 2021-2024 per the user rule.
