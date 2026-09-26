# Handoff for the next coding agent

ROUND parallel-20260906-r2 (2026-09-26, latest): use the Claude skill `/alpha-lab-leader` (.claude/skills/alpha-lab-leader,
research-map.md has the full state). Best realistic candidate v144 (3.37%/month, full-path DD 19.6%, realistic 1m
execution, governor, target 0.25 ex post), frozen in scripts/v144_advisor.py; also logged v99/v104/v115/v127/v133.
Next: v150 Deribit options-flow features once data/raw/deribit_opt_20260926/BTC_options_4h.parquet exists
(research/mj/fetch_deribit_options_4h.py BTC 2019-01-01; resumable monthly cache).

ROUND parallel-20260906-r2 now holds v89/v90/v91 (see CONTINUOUS_RESEARCH.md top). Next: audit v89
(OpenCode blind audit), then rotate v89 -> v92 (pooled majors model with 2017+ spot history and
ex-ante vol-targeted sizing). v90 Kaggle package must be reviewed by the leader before any submit.

HIDDEN-YEAR PROGRAM (2026-09-24, user protocol): read `RESEARCH_VF_RESULTS.md`.
Train/select on all data before 2025-09-14, hide 2025-09-24..2026-09-23, replay.
Lead candidate `vf_combo_fast20_don55_10_w0.5_k0.65`: hidden year +13.0% normal
/ +8.1% stress, DD 9.0%, 5/5 real years positive; audited blind (W9) and by
truncated replay. ~55 configs scored on the same hidden year; the trend variants
are statistically indistinguishable (rank corr 0.12). Patterns, indicators,
positioning, breadth, macro, DVOL, seasonality, HGB and TCN+GRU models all
failed to add robust value. Forward tournament of 5 frozen families logs every
4h via `scripts/advisor_shadow.py` (breadth family needs live alt data: TODO).

PATTERN LAB r1-r4 (2026-09-24): read `RESEARCH_PATTERN_LAB_RESULTS.md`. Candle,
chart and indicator features gave no model skill (AUC ~0.5); pattern models
failed the opened-year check. Frozen candidate `pattern_lab_r4_R0_scaled_0.65`
(4h EMA20/200 ribbon long, daily-ribbon entry gate, size 0.65) PASSED:
opened year +13.6% / +7.4% stress, DD 10.7%, 48 trades. The BTC opened year is
now fully spent; only prospective rows from `scripts/advisor_shadow.py`
(mode=prospective) are clean evidence. No live orders.

MA RIBBON R1 (2026-09-24, user request): read `RESEARCH_MA_RIBBON_R1_RESULTS.md`.
Pre-registered daily SMA50/SMA200 ribbon long/short (H4) passed the research
gate on the now-OPENED holdout year (+31.3% normal, +28.1% stress, DD 18.7%;
22.6% DD under daily-rebalanced sizing). Plain golden/death cross and all ML
rows failed. Only prospective data is clean now: run
`research/opencode_r82_ma_replication/shadow_log.py` daily; count only
`mode=prospective` rows. No live orders, 1x only.

V44 COMPLETE/REJECTED: read `RESEARCH_V44_RESULTS.md`. The causal v29
meta-ranker produced only0.218%/month in execution stress,24.745% DD, and66
fills; do not repeat this meta-HGB path without a new representation.

V43 COMPLETE/REJECTED: read `RESEARCH_V43_RESULTS.md`. The best local
combination was v42 holding_7d with the0.3% score gate:2.071%/month in
execution stress,15.531% DD,39 fills. The0.5% gate had30 fills but only1.784%
monthly. Do not repeat this combination without a new hypothesis.

V40-V42 COMPLETE/REJECTED: read `RESEARCH_V40_V42_RESULTS.md`. The strongest
local result was the immutable-v30 holding_7d filter at2.071%/month in
execution stress with15.531% DD and39 fills; it still misses5% monthly. The
score-tier, cross-timeframe HGB, and direction probes are already run; do not
repeat them without a new hypothesis.

CURRENT BLOCKER: v36-v39 local causal probes are complete/rejected and no
candidate reaches the5% monthly,20% global-DD,30-fill gate. See
`RESEARCH_V36_V39_RESULTS.md`. V33 is packaged but its private Kaggle upload
was rejected by the approval boundary because the package contains internal
BTC research source/data; no upload occurred. Do not retry through a browser or
another transport. Continue only after explicit user authorization for that
Kaggle upload.

V33 REGISTERED/PACKAGED: the separate candidate-vs-WAIT action-margin GRU was
prepared for one private Kaggle submission. Use
`configs/swing_v33_action_margin_gru.json` and package directory
`artifacts/kaggle/btc_swing_v33_action_margin_gru_20260906`; archive SHA-256 is
`915f89e4476684646f11f44895830ec6d0eadd54b21e504b94ff27287e58766f`, bootstrap
SHA-256 is `5840bb415fde8bdec54153f45b4571fda8087c42e52f7bdc2939cfbb83de9515`.
The causal probe was negative, but it did not include the registered sequence
encoder; the cloud hypothesis is the explicit action-logit adapter. Inventory
confirmed v32 COMPLETE, no v33 kernel, and the latest quota snapshot was
27.98/30.00 GPU-hours (refresh2026-09-12). Once upload authorization exists,
submit at most once; then download,
audit all33 models, run continuous replay and diagnostics. Do not use partial
outputs as evidence.

V32 COMPLETE/REJECTED: private Kaggle kernel
`nguynchtrai/btc-swing-v32-top-action-20260906` finished exactly once with
33/33 models. Local replay passed (maximum error2.384e-6); continuous replay
covered4,076 decisions and every branch missed5% monthly. Best drawdown-safe
row was mean0.5x at−1.967% normal net/DD18.807%. Diagnostics had MSE8.7939 vs
constant8.3653 and rank correlation−.00178. Read `RESEARCH_V32_RESULTS.md`;
do not resubmit. The next hypothesis is v33: separate candidate-vs-WAIT logits
with a registered inference adapter.

V31 COMPLETE/REJECTED: private Kaggle kernel
`nguynchtrai/btc-swing-v31-short-residual-20260906` version1 finished once
with33/33 models after the causal 60-day prior diagnostic. The full local
replay audit passed (maximum error1.073e-6) and one continuous replay covered
4,076 decisions. Best drawdown-safe branch was mean-minus-std0.5x:
normal+14.244% net/DD15.044%/+0.396% monthly; fee stress+12.024%/DD15.224%/
+0.337%; execution stress+17.198%/DD15.031%/+0.472%. All1x branches exceeded
20% DD and no branch reached5% monthly. Read `RESEARCH_V31_RESULTS.md` and do
not resubmit. Diagnostics found MSE8.6705 vs constant8.7271 but worse Brier
and rank correlation; v32 must change action-ranking representation.

V30 COMPLETE: the pre-registered causal calibration probe of immutable v29
predictions is finished at `artifacts/research/v30_v29_calibration`. Isotonic-4
at1x reached+122.798% normal net but DD20.086%; fee stress reached+112.963%
with DD20.473%; monthly geometric returns were2.405% and2.268%. The0.5x row
stayed below11% DD but reached only1.233% monthly. Preserve every mapping; no
mapping is a candidate and no leverage increase is approved. Read
`RESEARCH_V30_RESULTS.md`.

V29 COMPLETE and rejected: private Kaggle kernel
`nguynchtrai/btc-swing-v29-residual-gru-20260906` finished once with 33/33
models; local audit passed at maximum error5.722e-6. Best mean-minus-std1x
normal was+29.138% net/DD26.255%;0.5x was+15.358%/DD13.481% and+0.425%
monthly. Read `RESEARCH_V29_RESULTS.md`; do not resubmit.

V28 COMPLETE and rejected: private Kaggle kernel
`nguynchtrai/btc-swing-v28-hurdle-gru-20260906` finished all33 models and local
audit passed at maximum error7.153e-6. Every branch failed the target. Read
`RESEARCH_V28_RESULTS.md`; do not resubmit.

V26 and v27 are complete development comparators; read
`RESEARCH_V26_RESULTS.md`. No accepted model or independent test exists.

V25 COMPLETE and rejected: private Kaggle kernel
`nguynchtrai/btc-swing-v25-ranked-gate-20260906` version1 finished with 33/33
models. Local TCN replay/policy audit passed (max error2.1458e-6), but the
continuous portfolio failed every scenario. Best v25 mean-minus-std0.5x row is
−14.207% net / 31.939% DD / 107 fills; mean1x normal is −43.614% / 62.773% /
110 fills. Read `RESEARCH_V25_RESULTS.md`. Do not resubmit v25 or deploy it.

V22-v29 and v30 are complete failed development experiments; no accepted model
or independent test exists. Before a next heavy run, inspect the v29/v30
diagnosis, register a materially different fixed hypothesis/config, check
Kaggle jobs/quota, and submit at most one private free-T4 job. Keep local work
to inference, replay and backtests; do not repeat a calibration or residual
run without a new measured hypothesis.

V21 COMPLETE: all33 nested-validation refits, local replay and policy parity
passed, but mean1x net−33.684%/DD40.327%/22 fills and mean−std0.5x net−14.583%
/DD14.837%/10 fills. No target or deployment approval.

HISTORICAL v21 RUNNING NOTE: v21 is complete; read RESEARCH_V21_RESULTS.md for
the full audit/portfolio failure. Do not resubmit it or use the older pending
instructions below. V19/V20 completefailed; detailedresults in
RESEARCH_V19_V20_RESULTS.md.

LATEST RESULTS: v19fullaudit PASSED;v19baseline andv20calibration COMPLETE/FAILED.
Read RESEARCH_V19_V20_RESULTS.md. v19mean1x−40.98%/DD59.82%;allv20normalnets
negative. v21nestedvalidation implemented with separatetrainer/immutablev19base;
privatepackage artifacts/kaggle/btc_swing_v21_20260906, datasetuploadsession67399.
Check cloud dataset/job state before submitting. No v21kernel yet at this update.

LATEST v19 DOWNLOAD COMPLETE: full export exists at artifacts/kaggle/v19_download;
localGPU inference audit ACTIVE session28359, output artifacts/research/v19_local_audit.
First2folds passed (~2e-6error).126tests passed. After auditpass run baseline
continuousportfolio, diagnostics and pre-registeredv20calibration. No retraining.

LATEST v19 CLOUD COMPLETE2026-09-06:33/33metadata complete, bothworkers exit0,
GPUreloadparity allpassed (maxerror2.384e-6). Full ~3.2GBexport downloading to
artifacts/kaggle/v19_download (session84333 at update). Do not re-train. After
download, run audit_tcn_export then continuousportfolio; v20causalcalibration
config pre-registered for follow-up, only after audit passes. Read V19status top.

VERIFIED v19 TRAINING: live logs confirm TeslaT4x2,torch2.10.0+cu128; first3/33
models (fold0,all3seeds) complete16epochs +checkpoint/GPUreload parity; fold1
running. Use `kernels logs ... --follow` (bare logs may remain empty during run).
No new backtest yet. Do not resubmit; wait for all33, download and audit locally.

LATEST v19 CLOUD RUNNING2026-09-06: kernel version1 submitted successfully to
nguynchtrai/btc-swing-v19-tcn-20260906 (private,T4request,timeout12000seconds).
Dataset READY and all hashes verified. Initial logs empty; hardware/epochs not
yet confirmed. Read RESEARCH_V19_STATUS.md. DO NOT submit duplicate training.
Use `kaggle kernels logs` / status; download completed outputs then audit locally.
Older no-submission/approval-block notes below are superseded.

LATEST v19 2026-09-06: Read RESEARCH_V19_STATUS.md FIRST. TCN+attention24,106,627
params implemented;121tests passed; private Kaggle dataset uploaded successfully.
NO v19 kernel submitted: automatic approval review hit usage limit on status check.
Do not bypass rejection. Resume dataset-ready check then single T4x2 submission
when permissions recover. All older "no cloud data"/local-training notes superseded.
Local full-forecast audit and mandatory TCN backtest gate now implemented. Use
scripts/audit_tcn_export.py then continuous evaluator with --replay-audit; no actual
v19 weight replay yet because the training kernel has not been submitted.

LATEST2026-09-06: v18 STOPPED,8complete folds +partialfold8weights after CPU/GPU
replay assertion. Read ARCHITECTURE_REVIEW_20260906.md and topofresearchrunlog.
Heavy training MUST move to Kaggle CLI/freeGPUs; local machine inference/backtest.
No new cloud job submitted. Old running-session61208 notes below are superseded.

CURRENT2026-09-06: v17corrected calibration COMPLETE; v18Transformer ACTIVE
session61208 at artifacts/research/swing_v18_transformer_20260906.3,056,451params,
6layers,3seeds,11contiguous quarters,16epochs; same past128candles×5frames.
Read topof RESEARCH_RUN_LOG.md and RESEARCH_20260906_CORRECTION.md before work.
New target5%monthly geometric net,globalDD20%. No candidate meets target.110tests
passed. v17four-quarter1x only1.715%monthly despite77.398%total in2.809years.

LATEST2026-09-06: Read RESEARCH_20260906_CORRECTION.md FIRST. Target geometric
5%monthly net,79.5856%annual,globalDD20%;deep learning preferred. v15 COMPLETE.
Previous isotonic+41.46% result INVALID due future label leakage and quarter-reset
cooldowns. Correct past-only calibration/global-state audit is the next task.

START HERE: `RESEARCH_RUN_LOG.md` is the new compact experiment/result index.
NEWEST: v13/v14 COMPLETE. v14temporal mean0.5x stitched development net+25.6370%,
DD12.6895%, executionstress+17.4605%; BUT1xDD23.9068%, history has fold gaps and
original6/8fold screen failed. No live candidate. Read the run log for full costs.
v15 ACTIVE session94744 at `artifacts/research/swing_v15_continuous_20260905`:
33GPUmodels,11contiguous quarters, final ONE-state portfolio automatically follows
training. Inspect training progress and continuous/summary.json before relaunch.
105tests pass. All24v13checkpoint full evaluation forecasts CPU-replayed.
Current continuation completed v6 context probe (FAILED), both data caches and
derivatives48h/72h feature construction. Old cache/download-running notes below
are historical. v10 derivatives experiment session36977 active; exact artifact
path/next steps in the run log. No reset credits used and no live candidate.

NEWEST2026-09-05: Kronos is now OPTIONAL per user; choose any learned architecture
by evidence. See `RESEARCH_V8_V9_RESULTS.md` and top of`CONTINUOUS_RESEARCH.md`.
v8 shared-value and v9 four-head models both failed8-fold robustness; do not deploy
or quote only v8's positive recent slice.90 tests pass. Existing hourly prompt
updated to model-agnostic. Check cache50466 and new derivatives-data audit99026
before launching anything; artifacts/data remain ignored and no live orders.

LATEST: v5 finished all WAIT; v2/v5 full checkpoints downloaded and audited.
See `CONTINUOUS_RESEARCH.md` for active local feature-cache/probe processes and
their output paths. Do not duplicate those jobs.77 tests pass. No new live approval.
Heartbeat13:47Z:83 tests pass after optional UTC-anchored decision-grid support.
Future new dataset configs must pin decision_anchor_utc; see continuation log.

CONTINUOUS MODE: user requested autonomous repeated research. Read
`CONTINUOUS_RESEARCH.md` first for the active hourly continuation and next steps.
The prior handoff below is a completed iteration, NOT completion of the objective.
NEW v5: full-trunk candidate-interaction/ranking experiment implemented; expanded
4448/308/752 dataset; CPU/GPU smoke and49 tests pass. Kaggle private kernel
`nguynchtrai/kronos-btc-swing-v5-20260905` version1 submitted; inspect before any
new run. Do not confuse smoke output with full training performance.

LATEST — 2026-09-05: read `RESEARCH_V4_RESULTS.md` first, then `SWING_TRAINING.md`.
Kaggle full-trunk Kronos-base v2 is COMPLETE, not running: all WAIT on development.
Its reports/predictions are downloaded; full weights have NOT been downloaded.
Tree v3 first historical holdout FAILED: -14.7835%, DD23.215%,9 fills.
Extended BTC data to Jan2022; v4 searched12 configurations across5 purged walk-forward
folds, froze one pipeline, then opened the April–July2026 reserve ONCE.
Result: 100->105.1135 (+5.1135%), close-sampled DD4.2228%, but only ONE filled trade
and3 alerts, all June. Not sufficient evidence; no live approval, no validated leverage.
Selected pipeline is ExtraTrees/40 causal five-frame features, NOT a larger Kronos;
explicit regime gate was NOT selected. Kronos does not deserve credit for this result.
User now permits maxDD20%, superseding10%; config `swing_acceptance.json` is canonical.
43 tests pass; all3 historical alerts replayed exactly. See report/bootstrap limitations.
No GPU job or background monitor active. Do not submit duplicate Kaggle jobs.
April–July reserve is now opened; do not tune against it and call it independent again.
Next: keep v4 frozen as a paper comparator, acquire genuinely new forward evidence
and improve execution/derivatives data on development only. No profit guarantee.
Source/data/checkpoint hash manifests and exact commands are in the latest report.

Older sections below retain historical context; latest report/config supersede them.

This is the canonical continuation guide after cloning `Agentic_Alpha_Lab`.
Read this file and `AGENTS.md` completely before changing code or running an
experiment. The repository is a research and paper-trading system, not a live
order executor.

## Latest continuation — 2026-09-05, engine v2 + supervised smoke

NEWEST: read `KRONOS_TRADING.md` first for the implemented **actual frozen Kronos-mini
+ cross-timeframe attention + learned bracket selection** and private Kaggle run
`nguynchtrai/kronos-btc-mtf-20260905-v1`. COMPLETE on confirmed 2 Tesla T4.
Downloaded checkpoint and hash/replay verified at `artifacts/kaggle/results_v1`.
Best epoch 11, stopped 16; validation 971 decisions all WAIT, 0 trades, equity 100.
This does NOT pass trading acceptance. Do not submit duplicate runs. Read the
diagnosis and v2 proposal in the new document. Older notes below describe earlier baselines.
Source/tests/data builder/train/infer/Kaggle packaging are implemented; backbone
fine-tuning, calibration, locked-test evaluation and new web wiring are NOT done.

Newer data/Colab status: read `COLAB_3Y_STATUS.md`. Three-year data and the 56.6 MB
training ZIP now exist locally and are ignored by Git. Colab upload/training has
NOT started: browser control was blocked by Codex usage-limit approval failure.

Read `TRAINING.md` next; it contains exact commands and current unfinished work.
Dataset builder, MLP/logistic trainer, calibration, checkpoint evaluator, Colab
packager, and notebook now exist and the local end-to-end loop has run.
This is NOT Kronos fine-tuning, learned brackets, or RL. Excursion/touch labels
exist but their heads are not trained. The reference head intentionally uses FP32.

Local artifacts (ignored; regenerate after clone):

- `data/processed/btc_20260905_v1`: immutable snapshot, 4263/560/182/849 rows.
- `artifacts/checkpoints/mlp_20260905_v2`: canonical smoke checkpoint with source hashes.
- `artifacts/colab_btc_20260905_v1.zip`: training bundle; excludes test and raw candles.
- `reports/supervised/mlp_20260905_v1/summary.json`: opened research test, capital
  100 -> 99.6459, -0.3541% return, -0.9029% close-sampled DD, PF 0.8051, 12 long trades.

Do NOT tune thresholds on that result. This interval was already inspected in Phase A.
Next: acquire multi-year/mark data, implement multi-fold walk-forward/tree comparisons,
and improve explicit maker-vs-stop execution before training Kronos fusion heads.
Colab notebook syntax and equivalent local pipeline are tested; real Colab execution
and browser interaction/responsive QA are still unverified. Web build and TypeScript pass.

## 1. Objective

Build a leakage-aware BTCUSDT perpetual research loop that:

1. downloads closed market candles and related market data;
2. runs Kronos on several timeframes;
3. converts calibrated model outputs into `WAIT`, `LONG`, or `SHORT` plus an
   entry limit, TP1, TP2, stop loss, holding horizon, confidence, and position size;
4. backtests those decisions after fees, funding, fill rules, drawdown, margin,
   and liquidation risk;
5. packages training data for Google Colab and brings the trained checkpoint
   back into the same locked evaluation pipeline;
6. exposes inference and experiment results in the local web dashboard.

The immediate goal is robust positive out-of-sample net return. Do not optimize
accuracy alone and do not claim a usable strategy from an in-sample threshold.

## 2. Repository relationship

The expected sibling layout is:

```text
Source_code/
├── Agentic_Alpha_Lab/   # this repository
└── Kronos/              # untouched upstream reference repository
```

Clone the official Kronos repository beside this repo if `../Kronos` is absent.
Do not copy its checkpoints into Git and do not modify upstream Kronos merely to
make an experiment pass. Put reusable adaptations in this repository.

Downloaded checkpoints, raw data, generated reports, virtual environments, and
Node dependencies are intentionally ignored. A fresh clone must regenerate them.

## 3. Non-negotiable trading assumptions

- Instrument: linear `BTCUSDT` perpetual.
- Base data: closed 5-minute candles; aggregate only complete higher-timeframe candles.
- Entry/TP: limit-touch proxy. Fee scenario `0.0002` (0.02%) per fill, or 0.04% round trip.
  Stop/timeout are market-like exits at that scenario fee, not proven maker fills.
- Long funding scenario: pay `0.0001` (0.01%) at each 00:00, 08:00, and 16:00 UTC boundary held.
- Short funding income: always zero. This deliberately avoids optimistic funding income
  and acts as a small allowance for unmodeled slippage.
- Signal formed after candle `t` closes; the earliest possible entry is candle `t+1`.
- A limit order fills only if the following real OHLC range touches its price.
- If stop and take-profit are both touched in one OHLC candle, use `stop_first`.
- Initial capital is displayed as index `100`. Position notional is recalculated from
  current equity after every trade, so results compound.
- Default comparison is 1x. Confidence-based leverage must be reported separately,
  capped at 2x until calibrated, and must never be enabled because it improves the
  same sample used to design it.
- Bybit-style liquidation is triggered using mark-price logic in production. The
  current trade-OHLC approximation is not necessarily conservative and is not exchange-perfect.
- Never place authenticated or live orders without a new explicit user instruction.

## 4. Bootstrap a fresh Windows/NVIDIA clone

Run from the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install torch==2.12.1 --index-url https://download.pytorch.org/whl/cu126
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

On this Windows setup, GPU entry points must import `torch` before `pandas` or
`c10.dll` can fail with WinError 1114.

Download model files and market data:

```powershell
.\.venv\Scripts\python.exe scripts\download_kronos_models.py --variants mini small base
.\.venv\Scripts\python.exe scripts\download_btc.py --days 30
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider
```

Run the complete test suite (now includes training leakage/hash/packaging tests). If tests fail, stop and fix the
regression before running new experiments.

## 5. Reproduce inference and the dashboard

Generate a four-timeframe probabilistic snapshot using Kronos-mini:

```powershell
.\.venv\Scripts\python.exe scripts\generate_dashboard_data.py --variant mini --paths 16
cd web
npm ci
npm run build
npm run dev
```

Open `http://localhost:3000/`. The dashboard source is under `web/app/`; its
generated data is written to both `web/app/dashboard-data.json` and
`web/public/data/dashboard.json`.

The current dashboard covers:

- 5m context → 1-hour forecast;
- 15m context → 4-hour forecast;
- 1h context → 24-hour forecast;
- 4h context → 72-hour forecast;
- probabilistic P10–P90 bands from independent stochastic paths;
- timeframe consensus, entry/TP/SL candidates, compounded backtests, and a
  separate leverage comparison.

Web validation status and remaining work:

1. production build and TypeScript check pass; rerun after changes;
2. preserve existing social assets; do not generate or wire sharing features without a request;
3. validate the timeframe tabs and responsive layout in the browser;
4. validate the optional WebMCP `select_forecast_timeframe` tool where a supported
   browser context is available;
5. keep the dashboard read-only until there is a safe local inference API.

## 6. Current evidence — do not reinterpret it

All numbers below are historical **legacy OHLC v1** results: 0.02% entry plus
0.02% exit, long funding 0.01%/8h, short funding zero and compounded equity.
They predate the v2 fixes for entry-candle target ordering, funding notional and
truncated holding windows. They have NOT been silently repriced or revalidated.

| Experiment | Capital 100 becomes | Net return | Important note |
|---|---:|---:|---|
| Mini 1h, 2,706 windows | 86.47 | -13.53% | 400 trades; fees dominate |
| Mini 4h, threshold 30 bps, full sample | 102.66 | +2.66% | in-sample only |
| Mini 4h validation, threshold 30 bps | 101.83 | +1.83% | PF 1.43 |
| Mini 4h embargoed locked test | 99.74 | -0.26% | PF 0.95; direction accuracy 46.15% |
| Dynamic 1x/1.5x/2x, full sample | 102.34 | +2.34% | worse than fixed 1x and larger DD |

The zero-shot model therefore does not pass the acceptance gate. The full-sample
profit must not be described as validation. The previously opened locked interval
is no longer pristine for future tuning; collect a new forward interval for the
next locked test.

The last generated multi-timeframe snapshot was:

- 5m: `WAIT`, 50.0% sampled upside probability;
- 15m: `LONG`, 62.5%;
- 1h: `LONG`, 93.8%;
- 4h: `LONG`, 100.0%;
- weighted consensus: `LONG`, 85.625%.

This is a 16-path zero-shot snapshot, not calibrated confidence and not a live signal.

## 7. Research roadmap beyond the implemented baseline pipeline

Do not start with reinforcement learning or architecture search. First establish a
strong, cheap, reproducible supervised baseline.

### Data to acquire

Use at least 3 years and preferably a full bull/bear cycle. Store immutable raw
partitions with a manifest and SHA-256 hashes. At minimum collect:

- Binance and/or Bybit trade OHLCV at 5m;
- mark-price and index-price candles;
- historical funding rate and exact funding timestamps;
- open interest, turnover, taker-buy volume, and basis where available;
- exchange maintenance-margin/risk-tier metadata for realistic liquidation tests.

Use only fields known after the decision candle closes. Join 15m, 1h, and 4h
features backward onto the 5m decision clock and discard incomplete higher-frame bars.

### Labels

Create multi-horizon targets for 1h, 4h, and 24h:

- three-class direction: `SHORT / WAIT / LONG`, where the WAIT band is wider than
  round-trip fees plus a validation-selected safety buffer;
- return quantiles (P10/P50/P90), not only point MSE;
- future MFE/MAE for both sides to supervise TP and SL distances;
- limit fill probability for a small set of entry offsets;
- holding/timeout target and regime/volatility auxiliary targets.

Labels may use future data; features never may. Use purged chronological walk-forward
splits with an embargo at least as long as the longest horizon.

### Recommended architecture sequence

1. Train logistic regression, LightGBM/XGBoost, and a small MLP on engineered
   multi-timeframe features. These are mandatory baselines.
2. Freeze Kronos-mini and cache pooled embeddings for each timeframe. Train a
   small cross-timeframe fusion head with gated attention.
3. Use separate heads for direction probabilities, return quantiles, MFE/MAE,
   limit-fill probability, and holding time.
4. Calibrate direction probabilities on validation (temperature or isotonic
   calibration) and learn an abstention threshold.
5. Derive entry/TP1/TP2/SL deterministically from calibrated outputs. Keep risk
   sizing outside the forecaster so it remains auditable.
6. Only if frozen embeddings beat all cheap baselines, unfreeze the final one or
   two Kronos blocks with a low learning rate. Do not redesign the tokenizer first.
7. Consider offline RL only after the supervised policy is stable; otherwise an
   RL reward will mostly exploit simulator artifacts.

### Colab deliverables (implemented baseline; details in TRAINING.md)

- `scripts/build_training_dataset.py` for deterministic Parquet splits;
- `configs/training.yaml` for all feature, label, cost, model, and seed settings;
- `notebooks/train_colab.ipynb`, runnable top-to-bottom on a Colab GPU;
- a packaging command that creates `artifacts/colab_bundle.zip` containing processed
  splits, manifest, config, and code but no secrets;
- checkpoint metadata containing Git SHA, data hashes, seed, validation metrics,
  calibration parameters, and feature schema;
- `scripts/evaluate_checkpoint.py` that evaluates an imported checkpoint without
  touching validation thresholds.

The notebook uses direct upload/download without a Drive mount, verifies hashes,
installs pinned non-torch requirements, and trains the reference MLP in FP32 with
early stopping. PyTorch is supplied by the Colab runtime and its version is recorded.
Mixed precision/frozen Kronos fusion remains future work for a larger model.

## 8. Acceptance gates

Use `configs/swing_acceptance.json`, not the superseded short-horizon Phase A gates.
User's latest drawdown tolerance is20%, with desired1–4 alerts/month (never force trades).
Current provisional research safeguards require positive normal/stressed net return,
DD within20%, at least30 fills and12 evaluation months, and a held-out evaluation.
These sample floors are not statistical guarantees. A live candidate also needs
mark-price/queue/slippage robustness, calibrated sizing and forward evidence not
concentrated in one month, direction or a few trades. Close-sampled DD cannot prove
a live20% loss limit. v4 fails the sample and duration safeguards.

Leverage is a risk overlay, not a way to rescue a negative 1x strategy. Enable it
only when calibrated confidence buckets show monotonic out-of-sample expectancy.

## 9. Files worth reading first

- `AGENTS.md`: hard research and safety rules.
- `PHASE_A_RESULTS.md`: current feasibility summary.
- `configs/research.yaml`: current inference/execution defaults.
- `src/agentic_alpha_lab/models/kronos_adapter.py`: upstream model integration.
- `src/agentic_alpha_lab/backtest/engine.py`: compounding, costs, fills, funding,
  mark-to-market drawdown, leverage, and approximate liquidation.
- `src/agentic_alpha_lab/data/timeframes.py`: complete-candle aggregation.
- `scripts/generate_dashboard_data.py`: probabilistic multi-frame inference.
- `scripts/evaluate_confidence_leverage.py`: exploratory leverage comparison.
- `web/app/dashboard.tsx`: current visualization.

## 10. Definition of done for the next agent

Before handing off again, the agent must:

1. keep all existing tests passing and add tests for new leakage/cost logic;
2. record exact data ranges, hashes, seeds, model checkpoints, and cost assumptions;
3. report capital index, net return, mark-to-market drawdown, PF, trade count,
   coverage, long/short breakdown, fees, funding, and liquidation count;
4. distinguish train, validation, locked test, and exploratory/in-sample results;
5. update this file and `PHASE_A_RESULTS.md` with what changed and the exact next step;
6. never silently tune using a locked test result.
