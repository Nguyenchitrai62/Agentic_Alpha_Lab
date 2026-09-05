# v19 TCN + cross-timeframe attention — 2026-09-06

## Current verified state

CURRENT2026-09-06: v21 is complete and failed the target; v22 ranked-loss TCN
kernel `nguynchtrai/btc-swing-v22-ranked-20260906` version1 is running. Do not
resubmit v22. After completion, download/audit all33 models and run the single
continuous portfolio. See RESEARCH_V21_RESULTS.md for v21 evidence.

FINAL2026-09-06: Full local audit PASSED; continuousv19 andall10v20calibration
branches COMPLETE and FAIL usertarget. Read RESEARCH_V19_V20_RESULTS.md for full
table/provenance. Mean1x−40.984%net/DD59.824%;mean−std1x−47.642%/DD62.605%.
Allcalibratedvariants also lose undernormalcosts. Do not deploy or increaseleverage.
Separatev21nestedvalidationtrainer implemented; package/upload in progress. Older
active/download-pending notes below are historical. v19weights preserved intact.

DOWNLOAD COMPLETE2026-09-06: CLI full download finishedexit0 (~3.2GB) at
artifacts/kaggle/v19_download. Local full audit ACTIVE session28359, output
artifacts/research/v19_local_audit; first two folds passed full forecast replay
with errors~2e-6 on GTX1650.8sample preflight error9.5367e-7. No localtraining.
Current126tests pass including forecast diagnostics and calibration audit-gate
tests. Added scripts/diagnose_tcn_value.py to compare out-of-sample payoff/fill
forecasts against train-mature candidate means after auditpass. Baselineportfolio
and v20calibration still pending; older download-pending paragraphs historical.

LATEST2026-09-06: Kaggle version1 COMPLETE. Downloaded runtime/summary/all33
metadata:33/33statecomplete, workerexitcodes[0,0], missing_or_failed[], all GPU
reload paritypassed; maximum replayerror2.384185791015625e-6. Sum per-model
elapsed3535.82seconds across two workers (not wall-clock duration). Full ~3.2GB
export downloading to artifacts/kaggle/v19_download; do not start full audit
until downloader succeeds and all hashes are present. No local audit/portfolio
result yet. Initial metadata download hit Windows log-encoding error AFTER all
metadata were downloaded; full download sets PYTHONUTF8=1 as well as UTF8stdout.
v20calibration config registered before inspecting predictions/portfolio; same
past-mature1/2/4/all-quarter maps asv17, identitycomparator, exposures1/.5. The
calibration runner now requires passed TCN audit too. Old RUNNING notes historical.

CONFIRMED2026-09-06: live stream `kaggle kernels logs ... --follow` shows
**Tesla T4 x2, torch2.10.0+cu128**, both training workers active. At least the
first3/33models (fold0,seeds1729/1730/1731) finished16epochs, saved checkpoints,
and reported `state:complete` including GPU reload parity. Approximately62–69sec
per first-fold model; later folds have more training rows, so this is not a final
runtime estimate. Fold1 training observed. No portfolio evaluation yet. The
earlier empty-log/hardware-unverified notes below are superseded. No job restart.
Use --follow for LIVE logs; bare `kernels logs` reads persisted logs and can be
empty while a run is healthy. Stopping local log streaming does not stop cloud
training. Post-run full local inference audit is still mandatory.

UPDATE2026-09-06 (~01:49Asia/Saigon): approval recovered. Dataset status READY;
all package/source/data hashes reverified; quota29.50GPUhours available before
submission. **Kernel version1 submitted successfully** to
`https://www.kaggle.com/code/nguynchtrai/btc-swing-v19-tcn-20260906` with
`--accelerator NvidiaTeslaT4 -t12000`, private metadata. API status RUNNING.
Initial logs/output are still empty; GPU allocation and first training epoch
not yet verified. Do not submit again. Older NO-SUBMISSION paragraphs below are
historical and superseded by this update. Next: `kaggle kernels logs` and status;
download all outputs after completion, then full local audit/backtest.

Local follow-up completed after the cloud approval block: full-forecast replay
auditor and mandatory backtest gate implemented; **121 tests passed** across the
full suite (CPU tests, no local heavy training). Tests include all-WAIT handling,
changed trading instructions, numerical drift, missing models and mutated weights.
The auditor has not yet replayed v19 trained weights because no cloud run exists.

- Implemented model: **24,106,627 trainable parameters**, five independent causal
  TCN encoders (dilations1/2/4/8/16,125-candle receptive field),16 tokens/frame,
  six512-wide cross-frame attention layers, macro4h/1d gated micro5m/15m/1h.
- Existing40 causal summary features and16 entry/SL/TP1/TP2 bracket candidates.
  Learned unconditional net return and fill heads plus macro auxiliary loss.
  This version does not regress unconstrained prices or train MFE/MAE heads.
- Fixed3seeds x11quarterly folds x16epochs =33models;730day past-only training,
  label_end before refit minus8days. All4076 evaluation decisions belong to
  already-opened development periods. No seed/epoch winner selection.
- Intended compute: private free Kaggle T4x2, one independent worker per GPU;
  AMP microbatch32, accumulation2, FP32 inference. No heavy local training.
- **116 tests passed**, including five new causal/gradient/reload/capacity/bundle
  tests. Data preflight verified shapes(5628,5,128,6),(5628,40),(5628,16,3), all
  hashes and eleven chronological splits. Local tests were small CPU work only.
- Kaggle CLI quota checked:29.50GPU hours remaining of30; refresh2026-09-12.
  Previous relevant v5 cloud job COMPLETE. This is a pre-submission quota snapshot.
- Private dataset upload succeeded:
  `nguynchtrai/btc-swing-v19-tcn-20260906-data`.
  API response: private Dataset being created; processing status not yet verified.
- **NO v19 kernel submitted yet.** Next status-check call was rejected by automatic
  approval review because of account usage limit. Do not bypass that rejection.
  No v19 training result or new profit claim exists.

## Reproducible package

- Config: `configs/swing_v19_tcn_fusion.json`.
- Model: `src/agentic_alpha_lab/models/tcn_fusion_value.py`.
- Training-only worker: `scripts/train_tcn_kaggle.py`.
- Bootstrap: `scripts/kaggle_tcn_bootstrap.py`.
- Allowlisted packager: `scripts/package_tcn_kaggle.py`.
- Ignored package directory: `artifacts/kaggle/btc_swing_v19_20260906`.
- Archive61,625,947bytes; SHA256:
  `51cac4386eb70caf1f55ffa38adca9ada67d79c56ad4fd5a42183318b80ff530`.
- Bootstrap SHA256:
  `a0dfefd94f3910f6301fd53b69b017cc69d73a19ce173fbf0ecfd241bda69b91`.
- Allowlist contains only model/trainer source, config, features/labels/decision
  clocks and their manifests. No API tokens, raw candles, credentials or old
  weights. Dataset and artifacts remain Git-ignored. No push/commit performed.
- Windows CLI upload must use backslashes in `-p`: CLI2.2.4 resume-state filename
  sanitization mishandles forward slashes. First attempt failed locally before
  upload; the subsequent backslash-path upload succeeded. No duplicate dataset.

## Original submission procedure (already executed; do not resubmit)

Run from `C:\TRAI_NC\Source_code\Agentic_Alpha_Lab`, not upstream Kronos:

```powershell
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\kaggle.exe datasets status nguynchtrai/btc-swing-v19-tcn-20260906-data
.\.venv\Scripts\kaggle.exe kernels list --mine --page-size 20 --csv
.\.venv\Scripts\kaggle.exe quota
```

Verify dataset ready and no matching v19 job already submitted. Then, once only:

```powershell
.\.venv\Scripts\kaggle.exe kernels push -p artifacts\kaggle\btc_swing_v19_20260906\kernel --accelerator NvidiaTeslaT4 -t 12000
.\.venv\Scripts\kaggle.exe kernels status nguynchtrai/btc-swing-v19-tcn-20260906
```

Bootstrap requires exactlyT4x2; refuses alternate hardware. It retains partial
checkpoints on worker failure and marks incomplete runs; never evaluate a chosen
subset as if all33models completed. Runtime actualGPU allocation/training remains
unverified until the submitted job logs show it.

On completion download into a NEW ignored directory using `kernels output`.
Cloud output is `tcn-training/...` containing weights, replay samples, prediction
files, per-fold provenance, bundled source, plan and complete/incomplete summary.
Local audit is now implemented in `scripts/audit_tcn_export.py`. It verifies every
checkpoint hash, saved train/test indices, source/config/data identity and replays
ALL4076 forecasts perseed using the local model. Incomplete or parity-failed runs
are rejected. Fixed numeric tolerance rtol/atol0.001 plus EXACT ordered
entry/SL/TP/clock/direction policy agreement; do not loosen after observing results.
`research_temporal_continuous.py` now requires `--replay-audit` forTCNexports,
including re-verification of every prediction/weight hash before portfolio replay.
Keep ONE global cooldown/monthly quota/position/equity state with fee/fill stress.
Example once cloud output has actually been downloaded (paths below are future
output locations, not a claim that they exist yet):

```powershell
.\.venv\Scripts\python.exe scripts/audit_tcn_export.py --source artifacts/kaggle/v19_download/tcn-training --output artifacts/research/v19_local_audit --device cuda
.\.venv\Scripts\python.exe scripts/research_temporal_continuous.py --plan configs/swing_v19_tcn_fusion.json --training-source artifacts/kaggle/v19_download/tcn-training --replay-audit artifacts/research/v19_local_audit/audit.json --output artifacts/research/v19_local_portfolio
```

The original immutable package hashes above are unchanged: these local audit and
portfolio scripts are deliberately outside the cloud training bundle.

## Research acceptance remains unmet

Target geometric net>=5%/month (~79.5856%/year), globalDD<=20%, after costs.
Latest corrected v17 four-quarter calibration development result:1.71505%/month,
77.3981% total over2.809years, normalDD18.8565%; execution-stressDD19.4311%.
It does not meet target. Larger parameter count is a hypothesis, not evidence of
profitability. All opened historical periods remain development, not a fresh test.
