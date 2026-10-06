# ops_jitterjob REPORT (2026-10-06): joint-jitter robustness job for deployed G2

## What was built (no commits, no uploads; credentials never touched)

- `artifacts/kaggle_stage/engine_kernel/jobs/jitter_g2.json`: 13 rows — 1 BASE
  (`R2B1D17BFG2`, byte-identical sleeve/hook to `oc_expiry4p.RUNS` and the
  `job_example.json` base) + 12 joint-jitter rows `R2B1D17BFG2_J01..J12`.
- `tests/test_ops_jitterjob.py`: 4 tests, all passing (see Verification).
- No custom hook module was needed: every row uses the builtin `bear` hook
  (nothing written next to the job file besides the job itself).

## Jitter spec (pre-registered, seeded, no result peeking)

- Deployed base: `rule=inv, k=1.0, kd=1.7, bear=true, G=2.0`, `book_hook=bear`.
- Jitter: independent seeded uniform draws within +-10% of deployed values,
  jointly on all three axes per row: `kd ~ U[1.53,1.87]`, `G ~ U[1.8,2.2]`,
  `k ~ U[0.9,1.1]` (`k` = sleeve flush-threshold/risk multiplier,
  `kd` = corr-size multiplier, `G` = sleeve gross cap).
- Seed `20261006` fixed in the file (`perturb.seed`); draws consumed in
  `kd,G,k` order per row `J01..J12` via `numpy default_rng(seed)`, rounded to
  4 decimals; all 12 triples distinct. Recompute:
  `rng=numpy.random.default_rng(20261006); u_kd,u_G,u_k=rng.random(),...`.
- TP / stop multiples NOT jittered: `engine_harness` sleeve keys are only
  `rule/k/kd/G/bear/cool/bm/xrp` — there is no TP_MULT / stop-multiplier key
  (`m_sleeve_sl` appears only as a read default for the `xrp` coin override),
  so they are left out per the brief. (One-at-a-time TP/SL/G plateau is in
  `research/diagnostics/oc_plateau2/REPORT.md`: all within 0.3 %/mo and
  1.5 pp full-path DD of base.)

## Every row's parameters

| row | kd | G | k | rule | bear | hook |
|---|---|---|---|---|---|---|
| R2B1D17BFG2 (BASE) | 1.7000 | 2.0000 | 1.0000 | inv | true | bear |
| R2B1D17BFG2_J01 | 1.8058 | 1.9290 | 1.0989 | inv | true | bear |
| R2B1D17BFG2_J02 | 1.6059 | 2.0194 | 0.9421 | inv | true | bear |
| R2B1D17BFG2_J03 | 1.7306 | 1.9083 | 1.0776 | inv | true | bear |
| R2B1D17BFG2_J04 | 1.8393 | 1.8660 | 0.9611 | inv | true | bear |
| R2B1D17BFG2_J05 | 1.8347 | 2.1287 | 1.0131 | inv | true | bear |
| R2B1D17BFG2_J06 | 1.8685 | 1.8108 | 1.0793 | inv | true | bear |
| R2B1D17BFG2_J07 | 1.7328 | 1.9300 | 1.0096 | inv | true | bear |
| R2B1D17BFG2_J08 | 1.6342 | 1.8926 | 1.0205 | inv | true | bear |
| R2B1D17BFG2_J09 | 1.7413 | 2.1144 | 1.0667 | inv | true | bear |
| R2B1D17BFG2_J10 | 1.8230 | 2.1428 | 1.0714 | inv | true | bear |
| R2B1D17BFG2_J11 | 1.6254 | 1.9996 | 0.9807 | inv | true | bear |
| R2B1D17BFG2_J12 | 1.6651 | 1.8083 | 0.9061 | inv | true | bear |

## Verification done here (full 5-year job NOT run locally, per brief)

- Job parses; BASE sleeve == `oc_expiry4p.RUNS["R2B1D17BFG2"]` ==
  `job_example.json` row 0; all 12 jitter rows reproduce the seeded draws
  exactly and sit inside the +-10% boxes; all sleeve keys in-schema.
- Smoke (shift 0, 60 bars from 2024-03-01, BASE row only, `ENGINE_NO_SCORE=1`,
  via `heavy_slot` tag `ops_jitterjob`): `kernel_run.main` output
  (`results.json` sans `seconds`, `runs.pkl`) is compare/byte-equal to the
  direct `engine_harness.run_rows` call (`bars={0:60}`) — the bundle-report
  smoke contract holds for the new job file.
- `pytest tests/test_ops_jitterjob.py -q`: 4 passed.
- Reproduction gate for the Kaggle full run: BASE must equal the v421
  `run.log` row (5y 5.41 %/mo, max yearly DD 16.91, full-path DD 16.82);
  else stop and report (same rule as `oc_expiry4p` / `ops_kaggleengine`).

## Expected Kaggle runtime

- ~8-12 min/row (bundle report) x 13 rows sequential => ~105-155 min
  (~1.75-2.5 h) total, plus dataset attach; 4 shifts x 13 rows = 52 engine
  legs at ~0.5 GB each, strictly sequential. Outputs in
  `/kaggle/working/out_eng/`: `results.json` (per-row `mean5y/worst/maxDD/
  losing/dev4/full_path_dd/years`) + `runs.pkl` (per-phase equity legs).

## Exact leader commands (NOT executed here; account 2, private)

```powershell
# 0. with account-2 Kaggle credentials active (leader-only), replace <owner>
#    with the account-2 username in artifacts/kaggle_stage/engine_data/dataset-metadata.json
#    and artifacts/kaggle_stage/engine_kernel/kernel-metadata.json (both stay private)
# 1. stage the jitter job as the bundled job (kernel default-runs job_example.json),
#    rebuild the self-extracting entry (never hand-edit kaggle_entry.py):
Copy-Item artifacts/kaggle_stage/engine_kernel/jobs/jitter_g2.json artifacts/kaggle_stage/engine_kernel/job.json
Copy-Item artifacts/kaggle_stage/engine_kernel/job_example.json artifacts/kaggle_stage/engine_kernel/job_example.json.bak
Copy-Item artifacts/kaggle_stage/engine_kernel/jobs/jitter_g2.json artifacts/kaggle_stage/engine_kernel/job_example.json
.venv/Scripts/python.exe artifacts/kaggle_stage/engine_kernel/build_bundle.py
# 2. create the engine dataset (private) from artifacts/kaggle_stage/engine_data/
#    (populated per its MANIFEST.json mirrored layout; ~935 MiB, see ops_kaggleengine REPORT):
kaggle datasets create -p artifacts/kaggle_stage/engine_data
kaggle datasets status <owner>/oc-engine-4p-data
# 3. poll status until ready, then push the script kernel (private, CPU, no internet):
kaggle kernels push -p artifacts/kaggle_stage/engine_kernel
# 4. after push, restore the example job and rebuild the entry:
Move-Item artifacts/kaggle_stage/engine_kernel/job_example.json.bak artifacts/kaggle_stage/engine_kernel/job_example.json -Force
Remove-Item artifacts/kaggle_stage/engine_kernel/job.json
.venv/Scripts/python.exe artifacts/kaggle_stage/engine_kernel/build_bundle.py
.venv/Scripts/python.exe -m pytest tests/test_ops_jitterjob.py tests/test_ops_kaggleengine.py -q
# 5. download /kaggle/working/out_eng/{results.json,runs.pkl}; check BASE == 5.41/16.91/16.82 first
```

## Leakage / causality notes (blind-audit checklist)

- Jitter values are pre-registered seeded draws fixed before any result is
  seen; no statistic from any test year (incl. 2025-09-24+) feeds any choice.
- Books/members/R2 tables are frozen pre-anchor fit artifacts (same inputs as
  `ops_kaggleengine`); hooks stay causal (builtin `bear` only, applied before
  the shifted-clock ffill). This job makes no selection — robustness
  diagnostic only; any row comparison stays on anchors 2021-2024 per the user
  rule, 2025 scored never selected.
