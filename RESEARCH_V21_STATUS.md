# v21: nested validation TCN training — 2026-09-06

## Latest verified state

FIRST REFITS SAVED: fold0seeds1729/1730 both selectedepoch1 after5nonimproving
validationepochs, scratchrefit completed and reportedstatecomplete/GPUparitypass.
Atleast2/33finalcheckpoints saved; nextinnerselectionjobs observed. Still noPnL.

LIVE VERIFIED: TeslaT4x2,torch2.10.0+cu128; bothworkers inner_selection started.
Fold0seeds1729/1730 observedepochs1–4; selectedepoch remains1 while trainingloss
falls andvalidationloss rises. This is early overfit evidence, NOT outerportfolio
results. Runtimehealthy; no need to resubmit. Stoppinglocallogviewer leavescloud
training running. All33finalrefitcheckpoints required beforeevaluation.

Private Kaggle kernel version1 successfully submitted:
https://www.kaggle.com/code/nguynchtrai/btc-swing-v21-val-20260906
API stateRUNNING. Dataset`nguynchtrai/btc-swing-v21-val-20260906-data` READY.
RequestedNvidiaTeslaT4,timeout12000sec; bootstrap refuses hardware otherthanT4x2.
Actual v21GPUallocation/firstepoch still pending live-logverification at this update.
Pre-run freequota29GPUhours. No paidcompute,liveorders or localheavytraining.
**131tests passed**, including nestedpurge,validationloss,epochselectionaudit,
modelgradients,cloudexportreplay andcalibrationgate. CPUtests only.

Read RESEARCH_V19_V20_RESULTS.md: v19/v20 arecompleteandfailed, notactive.
V19fullauditpassed, butmean1x lost40.98% with59.82%DD;all10v20branches failtarget.

## Registered changes

- Same24,106,627parameter TCN+attention5framearchitecture and16bracketheads.
- Inner180day chronologicalvalidation,8daylabel-endembargo onbothboundaries.
- Perfoldinnertrain772–2140rows,validation660rows; decisionoverlap remains.
- Max32selectionepochs,patience5,earliestlossimprovement1e-4. Objectiveunchanged.
- Resetseed/reinitialize, refit allpast730day maturedtraining forselectedepochs.
- Learningrate1e-4,weightdecay.05,AMPbatch32accum2. Jointoptimizationchange,
  notisolatedearlystopablation. All3seeds x11folds. No outerfoldPnLselection.
- Validationconstantcomparison diagnostic only, no hindsighttradegate.
- Persistinnerselectedweights/indices/losses andfinalrefitweights/provenance.
- No confidenceleverage. Targetgeometric5%monthlynet/globalDD20%stillunmet.

## Reproducibility

Config`configs/swing_v21_tcn_validation.json`.
Trainer`scripts/train_tcn_validated.py` reuses immutablev19run_fold/coremodel.
Splitter`src/agentic_alpha_lab/models/temporal_validation.py`.
Package`artifacts/kaggle/btc_swing_v21_20260906` (Gitignored).
Archive61,629,814bytes;SHA256
`2d07db094f53b364ef6d0f59be20b67bffb8c9e2ca26d61bf70e64a854584e73`.
BootstrapSHA256`8a60ba23f0b691d45be14baf883bd9f506c8007f36bd678a62c3e17885afd4ed`.
Currentpackager/bootstrap now selects theoneTCNplan andexplicitallowlisteddriver;
oldv19cloudpackage/sourcehashes unchanged. No token/credentialinbundles.

## Next actions (do not resubmit)

FromAlphaLabroot:

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\kaggle.exe kernels status nguynchtrai/btc-swing-v21-val-20260906
.\.venv\Scripts\kaggle.exe kernels logs nguynchtrai/btc-swing-v21-val-20260906 --follow
```

Oncompletiondownloadfresh`artifacts/kaggle/v21_download`; expectedcloudfolder
`tcn-training`, roughly6.4GBbecause innerselected+finalweightsbothpreserved.
Thenlocalinferenceaudit andONEstateportfolio; do not usepartialseedselection.

```powershell
.\.venv\Scripts\kaggle.exe kernels output nguynchtrai/btc-swing-v21-val-20260906 -p artifacts\kaggle\v21_download
.\.venv\Scripts\python.exe scripts/audit_tcn_export.py --plan configs/swing_v21_tcn_validation.json --source artifacts/kaggle/v21_download/tcn-training --output artifacts/research/v21_local_audit --device cuda
.\.venv\Scripts\python.exe scripts/research_temporal_continuous.py --plan configs/swing_v21_tcn_validation.json --training-source artifacts/kaggle/v21_download/tcn-training --replay-audit artifacts/research/v21_local_audit/audit.json --output artifacts/research/v21_local_portfolio
```

Auditnowverifiesnestedtrain/valindices,selectedepochrule,innersavedweighthashes,
metadatarefitepochs andallforecast/policyequality. Portfolio auditgate rehashes
innerartifacts too. If GPUtrainfailures or numericpolicyparityissues occur, save
evidence and investigate; neverloosentolerances or selectsubset to pass.
Allhistoricaldates areopeneddevelopment; profit or5%target isnotguaranteed.
