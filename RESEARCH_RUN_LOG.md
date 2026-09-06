# BTC research ledger

CURRENT ACTIVE 2026-09-06: v32 top-action/WAIT GRU version1 was submitted once
to private Kaggle kernel `nguynchtrai/btc-swing-v32-top-action-20260906`; API
status is RUNNING. Package archive SHA-256 is
`ed68a90b153fe8caea81148501096330323d40ad81a5aeb97eeb3bb4425e0cb7`, bootstrap
SHA-256 is `410cb05dc61ff09c71bcd32842d575d6bd1c9adfa6bbfda03a0673454458379c`,
and the pre-submit quota was28.01 GPU-hours. The new fixed objective classifies
the best executable action versus WAIT and retains Huber payoff/fill/direction
terms; chronology and full pytest (`145 passed`) are verified. Wait for the
complete 33-model export; do not resubmit or inspect a partial subset as a
portfolio result.

CURRENT 2026-09-06: v31 short-window residual-GRU is COMPLETE/REJECTED. The
private Kaggle export finished once with33/33 models; the local full replay
audit passed all forecasts (maximum error1.073e-6), and the continuous replay
covered4,076 decisions. Best drawdown-safe fixed branch was mean-minus-std
0.5x: normal+14.244% net/DD15.044%/+0.396% monthly; fee stress+12.024%/
DD15.224%/+0.337%; execution stress+17.198%/DD15.031%/+0.472%. The 1x rows
exceeded20% DD and every row missed5% monthly. Read `RESEARCH_V31_RESULTS.md`;
do not resubmit. The next registration must change action-ranking
representation, not repeat short-window residual-GRU or calibration.

CURRENT AUTHORITATIVE 2026-09-06: v30 causal calibration of v29 is COMPLETE
as a read-only local probe. The strongest fixed map was isotonic-4 at1x:
normal+122.798% net/DD20.086% and fee-stress+112.963%/DD20.473%, only
2.405%/2.268% monthly; it misses both the5% monthly and20% DD gate. The
0.5x isotonic-4 row stays below11% DD but reaches only1.233% monthly. Preserve
all mappings; do not promote a map or increase leverage. Full table and hashes
are in `RESEARCH_V30_RESULTS.md`.

V29 COMPLETE 2026-09-06: residual-GRU cloud export finished once on2×Tesla T4,
all33 models, and local replay audit passed with maximum error5.722e-6. Best
normal row was mean-minus-std1x+29.138% net/DD26.255%; its0.5x row was
+15.358%/DD13.481%,+0.425% monthly. Diagnostics: MSE9.8944 vs constant8.3653,
rank correlation.0739. Reject; read `RESEARCH_V29_RESULTS.md` and do not
resubmit.

V28 COMPLETE 2026-09-06: hurdle-GRU cloud export finished all33 models and
local replay audit passed with maximum error7.153e-6. Every continuous branch
failed; the best0.5x mean-minus-std row was−9.915% net/DD18.849%. Read
`RESEARCH_V28_RESULTS.md`; do not resubmit.

V26 COMPLETE 2026-09-06: small-GRU/pairwise-ranking export and full local audit
passed; its best drawdown-safe0.5x branch was+9.539% net with12.302% DD and
only0.271% monthly. V27 causal calibration improved development net but still
missed5% monthly. Read `RESEARCH_V26_RESULTS.md` for provenance; no live
approval.

V25 COMPLETE 2026-09-06: ranked-gate TCN finished all33 private
Kaggle models finished on2×T4; full local replay/policy audit passed, maximum
error2.1458e-6. Continuous v25 failed every branch: mean1x normal−43.614% net /
DD62.773% /110fills; best mean−std0.5x normal−14.207% /DD31.939% /107fills.
Ensemble MSE9.1237 vs past constant8.3653, fill Brier.19558 vs.19556, rank
correlation.0258; the fixed.3–1% bucket predicted.6127% but realized−.1156%.
Full provenance/table in `RESEARCH_V25_RESULTS.md`. No live approval.

V24 DIAGNOSTIC COMPLETE 2026-09-06: past-only isotonic calibration of v22
predictions was run without retraining and did not meet target. The best fixed
window probe was isotonic4 at1x net+1.74%, DD16.68%, only18fills; fee stress
net+.46% and execution net−12.24%. It is not a candidate or a tuned result.

V23 COMPLETE 2026-09-06: listwise WAIT-aware TCN export passed all33-model
replay/policy audit, but mean1x normal ended−13.526% net /DD49.510%; mean−std
0.5x ended−8.124% /DD26.535%. Forecast MSE9.9539, Brier.19483, rankcorr.0014.
Reject; detailed artifact paths are preserved under v23 download/audit/portfolio.

V22 COMPLETE 2026-09-06: ranked-loss TCN export passed all33-model replay and
policy audit, then produced mean1x normal+17.690% net /DD35.015%, fee+11.186%
/DD35.581%, execution+12.212% /DD35.578%; mean−std0.5x normal+3.335% /
DD19.102%. Positive development net did not meet5% monthly,30-fill,or global
DD20% gates. V25 was the fixed gate-margin follow-up; do not resubmit v22.

V21 COMPLETE2026-09-06: nested180day validation/refit kernel finished with33/33
models, full local replay/policy audit passed (max error2.861e-6), then failed
continuous acceptance. Mean1x normal−33.684%/DD40.327%/22fills; fee stress
−34.722%/DD41.142%; execution stress−38.984%/DD46.037%. Mean−std0.5x had
−14.583% normal/−14.925% execution,DD15.178%,10fills. Forecast diagnostic
MSE8.4876 vs constant8.3653,fill Brier.2133 vs.1956,rankcorr.0261. Full
provenance inRESEARCH_V21_RESULTS.md; no deployment or leverage.

V22 REGISTERED2026-09-06: ranked TCN utility hypothesis packaged and submitted
once to private Kaggle kernel `nguynchtrai/btc-swing-v22-ranked-20260906`,
version1. Keep polling this job; do not resubmit. It keeps causal5-frame TCN+
attention/export audit but uses width256/tcn_width64/4attention layers, fixed8
epochs, Huber payoff loss plus fixed pairwise candidate ranking against WAIT.
Full pytest passed before upload; quota was28.74h. Evaluation remains local.

USER-IDEA DIAGNOSTIC2026-09-06: see RESEARCH_USER_IDEAS_20260906.md. Currentv19
SL/TP1minimum~2%,median3.93%;minimum.5/1%constraintchangeszeroorders. Fees+funding
6.77points vsnetloss40.98points: primarylossnotfees. Replayedoppositeside with
mirroredpassivelimitentry/samebrackets: mean1x+17.17%total,monthly.471%,DD27.65%,
executionstress−19.66%/DD37.61%;mean−stdinverse−28.14%,DD48.87%. Neitherpasses.
Read-onlysimulation; nochange to livepolicy,model orv21cloudtraining. No leverage.

V21 LIVE VERIFIED:2TeslaT4,torch2.10.0+cu128,inner_selectionstartedbothworkers.
Fold0seeds1729/1730 validationloss increases afterepoch1 despite fallingtrainloss;
earliestselectedepoch1 at epoch4. No portfolioevidenceyet. All33refits required.

CURRENT v21 RUNNING: privateKaggleversion1 pushed successfully to
nguynchtrai/btc-swing-v21-val-20260906.131tests pass;29hGPUquota prejob.
See RESEARCH_V21_STATUS.md forpackagehashes/nestedvalidation/refit/auditcommands.
V19/V20 completeFAILED, no targetmet. Do not submitduplicatejobs.

LATEST2026-09-06: v19audit PASSED all33;v19portfolio/v20calibration COMPLETE/FAIL.
Detailed table in RESEARCH_V19_V20_RESULTS.md. Mean1x−40.984%net,DD59.824%;all
v20normalnetsnegative. PayoffMSE12.161vsconstant8.365;rankcorr−.00589. v21 keeps
24.1Marchitecture,adds nested180dvalidation/8dpurge/earliestearlystop/refit plus
lr1e-4/wd.05. Newtrainer/tests/package implemented; datasetuploadsession67399,
kernelnotyet submitted atupdate. Old activev19sessions allfinished. No targetmet.

LATEST2026-09-06: full Kaggle v19download finishedexit0; localGPUfullaudit ACTIVE
session28359, artifacts/research/v19_local_audit. First2folds numericreplay~2e-6,
all33required.126tests pass. Diagnostic comparator script and v20calibration
registered before v19portfolioinspection. Next continuousbaseline and calibration.

LATEST v19 COMPLETE2026-09-06: Kaggle finished33/33models; all GPUreloadparity
passed,maxerror2.384e-6; workerexitcodes[0,0]. Metadata verified; full checkpoint
download session84333 to artifacts/kaggle/v19_download. No portfolio result yet.
v20calibration plan registered before prediction/PnL inspection; uses same
mature-label windows asv17 and now enforces completed localTCNaudit. Next audit,
continuousbaseline then calibration. No heavy localtraining or liveorders.

VERIFIED2026-09-06: v19 live logs confirm2xTeslaT4,torch2.10.0+cu128. First3/33
models (fold0,seeds1729/1730/1731) saved COMPLETE after16epochs and GPUreload
parity; trainloss3.77–3.81 to1.55–1.64 (not test/portfolio evidence). Fold1 active.
Read live logs with --follow; historical one-shot logs may be empty mid-run.
No v19 profit result yet; next completed-export full local replay/backtest.

LATEST v19 CLOUD RUNNING2026-09-06 (~01:49Saigon): private kernel version1 pushed
successfully: nguynchtrai/btc-swing-v19-tcn-20260906, T4request, timeout12000sec.
Dataset READY, all immutable bundle/source/data hashes verified, pre-run quota
29.50GPUhours. Initial log/output empty: actual GPUs/epochs not yet confirmed.
DO NOT submit duplicate. Follow logs/status, then download33checkpoints for local
audit and ONE-state portfolio. No new profit results. Prior blocker is resolved.

LATEST v19 2026-09-06: TCN+cross-frame attention24,106,627params implemented;
121tests passed. Private61.6MB dataset upload succeeded to
nguynchtrai/btc-swing-v19-tcn-20260906-data. NO kernel submitted: approval-review
usage limit blocked next status query. Read RESEARCH_V19_STATUS.md for exact
package hashes, compute/data constraints and single-submission resume commands.
No new training/profit results. Corrected v17 remains below5%monthly target.
Local full-forecast replay auditor implemented; continuous evaluator rejects TCN
exports without complete passed audit and matching weight/prediction hashes.

LATEST REVIEW2026-09-06: v18 STOPPED at fold8 ofseed1729 (CPU/GPU numerical replay
assertion,1/768elements;maxabs0.00116229).8complete folds +partial ninth weights;
no ensemble summary. Session61208 finished. DO NOT restart heavy training locally.
User requests Kaggle CLI for heavy training; local inference/backtests. Read
ARCHITECTURE_REVIEW_20260906.md for evaluation of suppliedTCN+Transformer plan,
1d/label/path-order corrections and recommended capacity/data scaling. CLI2.2.4
available; no new cloud job submitted in this review. Older ACTIVE notes superseded.

CURRENT2026-09-06: v17 corrected calibration COMPLETE; v18 Transformer ACTIVE
localGPU session61208, artifacts/research/swing_v18_transformer_20260906.
Latest check:3/33fold checkpoints complete (seed1729 folds0–2), next fold training.
CPU replay uses rtol1e-3/atol1e-3; observed max absolute differences across saved
eight-example checks0.0008943/0.0003438/0.0017056 (combined relative tolerance
passed). These are numerical parity checks, not bit-exact full-evaluation replay.
Latest fullsuite111tests passed after acceptance evaluator now enforces geometric
monthly target and refuses missing calendar duration. No target achieved yet.
Read RESEARCH_20260906_CORRECTION.md for withdrawn leaky calibration claims.
New target5%monthly geometric net,globalDD<=20%; no current pipeline meets it.
v17four-quarter1x: net77.3981% over2.80909years,monthly1.71505%,normalDD18.8565%;
fee net69.4226%,DD19.3585%;execution net57.3992%,DD19.4311%. Development only.
All1/2/4/allquarter windows and both exposures retained; no winner declaration.
v18 is6layers6heads width192 joint attention over80past patches,3,056,451params.
Same cached data/loss/16epochs asv15,33models total, alltrainable. GPU64sample
forward/backward smoke finite,508.7MiB allocated; fullsuite110tests passed.
Command: .venv/Scripts/python.exe scripts/research_temporal_continuous.py --plan
configs/swing_v18_transformer.json --output artifacts/research/swing_v18_transformer_20260906
Final training/summary.json and continuous/summary.json will be written; inspect
progress/checkpoints before starting another GPU job. No cloud job or live orders.

v17 artifacts: artifacts/research/swing_v17_causal_20260906/summary.json.
Every calibrator saves eligible dataset rows,latest_label_end and JSON knots;
8day label-end embargo enforced,first quarter WAIT,global policy applied once.
Identity exactly reproduces v15. The warmup differs from prior identity-first
leaky probe; do not attribute all return changes solely to removing leakage.
This is a correction audit on already-opened windows, not preregistered unseen
confirmation. Every v17 variant fails5%monthly target; preserve all failures.

LATEST2026-09-06: Read RESEARCH_20260906_CORRECTION.md FIRST. User now targets
geometric5%monthly net (+79.5856%yearly),globalDD<=20%,prefers deep learning.
v15 COMPLETE; no candidate meets target. Previous read-only isotonic results
(including+41.46%) have lookahead from unmatured quarter-end labels and reset
cooldowns; withdraw causal claims. Correct embargo/global-state audit is next.

Read this compact index before proposing another experiment. Detailed manifests,
source snapshots, predictions, trades and reports live in ignored artifact/data
directories. Preserve failures as well as winners. All percentages below are
net after the configured fee/funding; drawdown is candle-close sampled.

## Objective and evidence rules

User allows any learned model/architecture, including replacing Kronos entirely.
Desired1–4 alerts/month, holding3–7 days, macro4h/1d and micro5m/15m/1h, explicit
entry limit/SL/TP1/TP2. Capital100 compounded; fee0.02% each fill, long funding
0.01%/8h, shortfunding0. MaxDD20%; baseline1x. No live orders or paid compute.
History already inspected is development forever; no new independent test is
created by renaming a split. Neither many parameters nor one profitable slice
is a success criterion. Registration and forward paper evidence still required.

## Completed model trials

| Trial | Hypothesis | Measured outcome | Decision |
|---|---|---|---|
| Kronos v2 | Full12-block pretrained trunk, five-frame fusion | Validation and policy all WAIT | Not useful trading output |
| Kronos v5 | Full100.3M trunk/head, candidate interactions and ranking, expanded data | All WAIT; validation-selected epoch1 | Reject; preserve full weights and audits |
| ExtraTrees v3 | Candidate payoff regression | Opened holdout−14.7835%, DD23.215%,9 fills | Reject |
| ExtraTrees v4 | Regime search,5 purged folds, freeze one pipeline | Opened reserve+5.1135%, DD4.2228%,ONE fill | Insufficient evidence; frozen comparator only |
| v7 flow | Add taker imbalance/trade-count features viaPCA16,3 seeds | Every seed fails; policy−23.6995%/−31.6113%/−26.2512% | Reject this feature/head combination |
| v8 static recent slice | Shared HGB action-value model,40 market+6 candidate inputs | Validation+1.1815%,6 fills; policy+3.7949%,19 fills | Initially promising; wider audit below rejects |
| v8 monthly | Refit same model monthly with mature labels | Policy−3.1555%, DD20.9860%,21 fills | Reject |
| v8 eight folds | Frozen hyperparameters,730d trailing train and8d embargo | Mean fold−2.4293%,4/8 jointlypositive,73 fills,worstscenarioDD22.0652% | Reject |
| v9 hurdle | Learn fill/win/gain/loss separately, same eight folds | Mean fold−0.6964%,3/8 jointlypositive,64 fills,worstDD24.5948% | Reject |
| v6 Kronos context | Frozen768 context,train-onlyPCA32 plus raw40, same tree3 seeds | Policy−21.1886%/−36.4311%/−16.7531%,17/18/14 fills; validation about+2.93–2.97% | All seeds fail; no deployment |
| v10 derivatives48h | Add20 OI/positioning values+20 masks, same8fold HGB | Mean fold+1.7084%,5/8 jointlypositive,67 fills,worstDD15.4192% | Fails registered screen |
| v10 derivatives72h | Same hypothesis with an extra day of availability delay | Mean fold−1.4252%,3/8 jointlypositive,73 fills,worstDD19.8272% | Both-delay robustness fails; no deployment |
| v11 macro/micro neural | Learned macro gate on micro features,42,563parameters,3seeds/8folds | Meanfold−4.2736%/+1.0104%/+5.4608%; worstDD25.2025%/29.4290%/24.8381%; jointlypositive3/4/3folds | All3seeds fail; no winner-seed selection |
| v12 seed mean | Average unconditional payoffs from all3 v11 models | Meanfold−2.2569%,3/8positive,63fills,worstDD27.8499% | Reject |
| v12 mean−std | Penalize cross-seed candidate disagreement by1std | Meanfold−0.7367%,3/8positive,61fills,worstDD26.0467% | Reject; disagreement not calibrated risk |
| v13 patch-GRU | Learn128closedcandles/frame,40,707params,3seeds/8folds | Meanfold−2.5743%/+5.3377%/+0.9314%;4/8jointpositive each; worstDD25.0702%/17.2299%/14.9396%;55/56/61fills | All seeds fail original screen |
| v14 temporal mean | Equal unconditional-payoff ensemble of ALL3 v13 seeds | Meanfold+6.2321%,5/8jointpositive,57fills,worstfoldDD14.4224% | Promising development, fails original6/8screen |
| v14 mean−std | Same preregistered1std disagreement penalty asv12 | Meanfold+2.3822%,3/8jointpositive,56fills,worstfoldDD17.1794% | Fails originalscreen |
| v14 stitched mean1x | Replay fixed fold signals with capital carried between folds | 100→154.3990,DD23.9068%; fee stress+48.3873%,DD24.7050%; executionstress+35.2895%,DD20.5281% | FAIL user's20% global DD; fold DD had hidden cross-fold drawdown |
| v14 stitched mean0.5x | Fixed half-exposure baseline, no signal/threshold change | 100→125.6370,DD12.6895%; fee stress+23.1593%,DD13.1445%; executionstress+17.4605%,DD10.7955%;57normal/48stressfills | Development risk/net screen positive, not independent or full-period evidence; continuev15 |
| v14 stitched mean−std0.5x | Preserve second branch, not cherry-picked | Net+7.5217%,DD16.9288%; fee+5.4277%,DD17.5315%; execution+5.4279%,DD14.9503% | Weaker development comparator, no deployment |

Fold mean is not the return of one continuous compounded portfolio. Each fold
starts at100, with gaps between folds; full dates are in each plan/report.
v6/v7/v8/v9 reuse opened development. v5 checkpoint was validation-selected.
The v6 result does not establish that every possible use of Kronos is useless.

## Artifact index

- v2/v5 fullweights: `artifacts/kaggle/swing_results_v2/checkpoint` and
  `artifacts/kaggle/swing_results_v5/checkpoint`; integrity/backtest audit JSONs
  in `artifacts/research/swing_v2_cloud_full_audit.json`, `swing_v5_cloud_audit.json`.
- v3 holdout: `artifacts/evaluations/swing_tree_v3_first_holdout`.
- v4: `artifacts/research/swing_regime_search_v4/checkpoint`,
  `artifacts/evaluations/swing_v4_reserve`, `RESEARCH_V4_RESULTS.md`.
- v5 diagnostics: `artifacts/research/kronos_swing_v5_head_diagnosis_v1`.
- v6: `artifacts/research/swing_v6_context_probe_20260905/summary.json`.
- v7: `artifacts/research/swing_v7_flow_probe_20260905/summary.json`.
- v8: `artifacts/research/swing_v8_adaptive_20260905/summary.json`,
  `artifacts/research/swing_v8_walkforward_20260905/summary.json`.
- v9: `artifacts/research/swing_v9_hurdle_20260905/summary.json`.
- v11: `artifacts/research/swing_v11_macro_micro_20260905_r2/summary.json`.
- v12: `artifacts/research/swing_v12_consensus_20260905/summary.json`.
  All24 v11 checkpoints hash-verified and ALL fold evaluation predictions replayed,
  maximum absolute error0. This verifies artifacts, not profitability.
- v13: `artifacts/research/swing_v13_temporal_20260905/summary.json`.
- v14: `artifacts/research/swing_v14_temporal_consensus_20260905/summary.json`;
  all24 temporal checkpoints hash-verified and ALL evaluation predictions replayed
  onCPU against GPU output with declared1e-3 numerical tolerance.
- v14 compounded audits: `artifacts/research/swing_v14_portfolio_audit_20260905`
  and `artifacts/research/swing_v14_half_exposure_audit_20260905`, each summary.json.
  Every scenario has fee/funding/gross/net/trade CSVs. Flat during fold gaps;
  these are NOT returns from continuous coverage of the whole calendar interval.
- Details forv8/v9: `RESEARCH_V8_V9_RESULTS.md`.

## Data acquisition and availability

Frozen Kronos cache is COMPLETE:4,448/308/752 rows,44 chunks,2,237.8seconds on local
GPU. `artifacts/features/swing_v5_context_20260905`. Do not re-extract.

Derivatives archive is COMPLETE:1,542/1,542 dailyZIP checksums,443,963 rows, no
duplicates,2022-01-01 through2026-03-22. Root:
`data/processed/btc_derivatives_metrics_20260905_v1`. Four intraday gaps:
2023-09-12(20min),2024-02-16/17(10.5h),2024-10-28(15min),2025-08-29(20min).
OI fields are present; top-trader ratios only12.73% present in2022. Missingness is
preserved. Archive timestamp is not verified historical publication/receipt time.

Both exploratory48h/72h-from-source-day features are cached for5,628 development
decisions at `artifacts/features/btc_derivatives_lag48_v1` and
`artifacts/features/btc_derivatives_lag72_v1`.20 values+20 missing masks, no
forward/backward fill; daily contexts expire after24h. Both explicitly mark
`point_in_time_availability_verified=false`. They cannot certify live availability.

## Current trial and next action

v13 COMPLETE: `configs/swing_v13_temporal.json`, session14743 finished at
`artifacts/research/swing_v13_temporal_20260905`. Trainable shared patch encoder
andGRU read128closedcandles on each of5frames, then combine with summary features
for macro/micro gating and16bracket scores. Fixed16epochs,3seeds,8purgedfolds,
same costs/policy/loss family. Shorter epoch count is a disclosed compute change,
so this is not a strictly architecture-only comparison. Check process/artifacts
before relaunch. Checkpoints include replay inputs and CPU/GPU comparison.

CURRENT v15 ACTIVE localGPU session94744, root
`artifacts/research/swing_v15_continuous_20260905`; plans
`configs/swing_v15_temporal.json` and `configs/swing_v15_continuous_folds.json`.
Command: `.venv/Scripts/python.exe scripts/research_temporal_continuous.py --plan
configs/swing_v15_temporal.json --output artifacts/research/swing_v15_continuous_20260905`.
33models=3seeds×11quarterly refits; same architecture/16epochs/thresholds asv13.
730d past-only training,8d label_end embargo. Forecast every available decision
from2023-06-01 until the final mature-label cutoff before2026-03-23, including
quarter-end days. Assemble all forecasts BEFORE applying global cooldown,
monthly cap, position exclusion and one compounded equity state. No gaps between
quarters, no per-quarter equity resets in the final result. Training fold-local
reports are diagnostics and cannot pass advancement; final output will be
`continuous/summary.json`. Primary mean and secondary mean−std both retained,
1x and0.5x each. All opened development, not a new locked test. Do not duplicate.
105tests passed, including boundary coverage and gap/overlap rejection.

Sequence cache COMPLETE: `artifacts/features/swing_sequences_v13_20260905`,
5,628x5x128x6, exact decision alignment and40feature replay checked for all rows.
Window-only log-price/vol normalization; SHA of sequences.npy:
`30fde3e7f05120a32723c1d1e2036ad3dd42a1e1ac9d7a01ec9c95650dd8bb8f`.
No new data/test dates opened. Fullsuite102tests passed in this continuation.

v11 first attempt session59584 FAILED at first checkpoint serialization: candidate
buffer was a noncontiguous view into repeated action inputs. No fold reports or
deployable weights saved. Original source snapshots retained in
`artifacts/research/swing_v11_macro_micro_20260905`. Constructor now makes that
buffer contiguous; replay test covers a genuinely strided candidate input.
Rerun COMPLETE (session57591 no longer exists); output is
`artifacts/research/swing_v11_macro_micro_20260905_r2`, plan
`configs/swing_v11_macro_micro.json`. Shared frame encoders, learned macro4h/1d
gate on micro5m/15m/1h embedding and candidate interactions, direct payoff/fill
heads plus macro directional-payoff auxiliary.40 causal summaries, not raw
sequences. Three seeds, eight past-only folds, fixed40epochs; no early stopping
or epoch selection on evaluation. Each fold saves safetensors, scaler buffers,
candidate order, training logs and eight replay examples. Fullsuite98tests passed
before this serialization fix; both affected neural tests PASSED after the fix.

The existing hourly schedule was updated again at the user's explicit request to
state the full architecture freedom and prioritize a useful learned trading model
or pipeline. It explicitly requires reusable logs of both success and failure.
Same automation ID, target thread and hourly cadence; no duplicate created.

v10 (`configs/swing_v10_derivatives.json`): compare same v8 shared HGB head with
added derivatives features on both fixed delays, all eight folds, unchanged
policy/model settings. Artifact root:
`artifacts/research/swing_v10_derivatives_20260905`. Exec session36977 COMPLETE;
both-delays screen FAILED. No cloud job needed.

v10,v11,v12 failed;v13/v14 failed original per-fold robustness. v14mean has positive
stitched development net with lower risk at0.5x, motivating full-coveragev15 before
another architecture trial. IMPORTANT: maximum per-fold DD does not establish a
20% portfolio DD limit. Always run one continuous equity audit. If v15 fails,
inspect past-held-out score calibration and overlapping-label redundancy; never
calibrate on a model's own training tail or tune against future evaluation labels.
No successful live candidate yet; do not pick a favorable lag/seed retrospectively.

## Interpretation corrections from fallback-model continuation

- Quarterly realized LONG/SHORT mean differences show changing outcomes after the
  fact. They do not prove causal regime detection is possible or identify a unique
  reason existing models fail. Any learned regime hypothesis needs testing.
- PCA32 retained92.2% of768-context variance. A prior diagnostic correlated PCs
  with the mean payoff across ALL long/short candidates. Opposite directions can
  cancel in that target; maximum correlation0.0494 is not a valid stand-alone
  test of representation quality. v6's actual multi-candidate backtest is stronger
  evidence for its particular head than that aggregate correlation.
- Usage limits previously blocked writes/probe; current continuation successfully
  ran tests, v6 and feature caches. Old notes saying jobs50466/99026 run are stale.
  No reset credit was redeemed. Record future runs here so model switches preserve
  decisions and reuse completed computations.
