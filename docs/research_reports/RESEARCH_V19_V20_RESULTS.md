# v19/v20: complete, rejected — 2026-09-06

## Scope and reproducibility

Kaggle v19 trained33models,24,106,627parameters each, on2TeslaT4 GPUs. Both
workers exited0. All33weights downloaded; full local GTX1650 inference replay of
12,228decision-model forecasts passed with maximum error1.7166e-5. Both ensemble
branches produced exactly the same135ordered trading instructions locally/cloud.
Audit: `artifacts/research/v19_local_audit/audit.json`.

Evaluation2023-06-01 through2026-03-23,2.809092589years.4076unique decisions;
3seeds,11quarterly refits. All opened development, not an independent test.
Single global cooldown/month/position/equity state. Capital100, compounded.
Entry/exitfees0.02%eachfill,longfunding0.01%/8h,shortfunding0. Stress also checks
higherfees and adverse limitpenetration/slippage. Drawdown is OHLCsampled, not
true exchange mark/intrabar risk. No live orders or deployment approval.

## v19 baseline portfolio (all failed)

| Ensemble / exposure | Final capital | Net total | Monthly geometric | Normal DD | Execution-stress net / DD |
|---|---:|---:|---:|---:|---:|
| Mean /1x |59.02|−40.98%|−1.55%|59.82%|−41.74% /54.95%|
| Mean /0.5x |78.83|−21.17%|−0.70%|35.24%|−21.91% /31.54%|
| Mean−std /1x |52.36|−47.64%|−1.90%|62.61%|−57.74% /67.05%|
| Mean−std /0.5x |74.20|−25.80%|−0.88%|37.49%|−33.52% /41.45%|

Mean1x:91fills,winrate41.76%,grossPnL−34.21096,fees2.72056,funding4.05262.
Mean−std1x:90fills,winrate42.22%,grossPnL−41.40096,fees2.56529,funding3.67580.
Both generate135alerts, effectively saturating the4/monthcap: their scores do
not yet provide selective high-confidence swing entries. No confidence leverage.
Full results: `artifacts/research/v19_local_portfolio/continuous/summary.json`.

## v20 causal calibration (all10branches failed target)

Same1/2/4/allpreviousquarter windows as correctedv17, label_end strictly before
refit minus8days; firstwarmupWAIT. Registered before v19portfolioinspection.
No repeated-quarter portfolio resets. Identity results exactly match v19
mean−std in all three scenarios at both exposures.

| Calibration window | Normal net1x | Normal DD1x | Normal net0.5x | Normal DD0.5x |
|---|---:|---:|---:|---:|
|1quarter|−4.23%|29.57%|−0.97%|15.80%|
|2quarters|−8.36%|36.61%|−3.09%|20.001%|
|4quarters|−14.09%|34.40%|−5.95%|18.60%|
|Allprevious|−12.32%|34.40%|−5.02%|18.60%|

Calibratedbranches have40–44normalfilledtrades and49–63alerts. Filtering helps
reduce v19damage but does not produce positive normal-fee returns. Some execution
stress returns exceed normal because stricter fills skip losing trades; this is
path sensitivity, not a robust profit improvement. Allvariants fail5%monthly.
Full results: `artifacts/research/v20_tcn_calibration/summary.json`.

## Forecast diagnosis

- Ensemble payoffMSE12.1613 vs past-mature candidate-constant8.3653 (~45.4%worse).
- Within-decision action-rank correlation−0.00589: no useful positive ordering.
- FillBrier0.195438 vsconstant0.195558: negligible improvement.
- Scores predicting>2%net average3.0744%, actualmean−0.0541% across these
  overlapping candidate observations. This is not an independent trade sample.
- Thus falling trainloss is not evidence of generalization. The larger24.1M
  architecture did not outperform the earlier small GRU pipeline in this setup.

Diagnosis: `artifacts/research/v19_value_diagnostics/summary.json`. This supports
testing overfit controls; it does not prove that modelsize alone caused failure.

## Next registered experiment

v21 keeps samearchitecture, adds nested180day chronologicalvalidation with
8daypurge on both boundaries, max32selectionepochs,patience5,earliestloss-tie.
Then reinitialize and refit on all730day maturedtraining rows for selectedepochs.
Learningrate1e-4,weightdecay0.05. Compareconstantvalidation loss without posthoc
gating. All3seeds/11folds retained. This changes selection andoptimization jointly,
not a clean single-factor ablation. Config`configs/swing_v21_tcn_validation.json`.
Separatetrainer preserves immutablev19trainer/model/source hashes. Innerselected
weights,training/validationlosses,indices andfinalrefitprovenance persisted;
localaudit validates both stages. Heavytraining stays privatefreeKaggle.

No current model meets target5%monthlynet/20%globalDD. Prior correctedv17 result
~1.715%monthly is still only opened-development evidence, not a live recommendation.
