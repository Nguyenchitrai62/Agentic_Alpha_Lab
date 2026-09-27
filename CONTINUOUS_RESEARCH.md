# Continuous BTC research — active

LEADER 2026-09-28 (v210/v211, user: suggestions must be executable - one resting limit order, no fill in the first 5
minutes after the close, in a position only SL/TP may change): engine_user trade mode (tests/test_engine_trade_mode.py).
5-minute rule alone on continuous v205: dev4 5.58 / DD 19.88. Trade mode, full-target size: no management dev4 3.06
(2021 -23%, DD 40); + break-even at +2 sigma_d and stop tightened on an opposite signal (T2): 4.47 / worst 0.52 / DD
25.5, win rate 68% (half are break-even stops); + partial TP: 4.38 / DD 24.0. Selected T2, final 5y 4.25, last year
3.38 -> gate fails. v211 risk sizing (1-2% per trade, optional 5% open-risk cap) is worse (dev4 2.3-3.7, 2022 losing,
DD 23-33): sizing by signal strength carries the edge. The executable structure costs ~1.4pp/month and ~5pp DD vs
continuous re-sizing. v208, v209 audits PASS.

LEADER 2026-09-27 (v209, user: SL/TP move and most positions close by flips/rebalances - luck?): diagnostics of v205
(no selection): book-only alpha 0.117%/day, Newey-West t 3.53, beta 0.08 (R2 0.03); 40 circular-shift placebo books
all below the real book (real 3.60 vs placebo max 0.66 %/month 5y, mean -0.48); long-only |books| 1.91, -books -3.29.
Book and sleeve are positive in every anchor year. Book profit comes from 50 episodes ridden to TP (SL -34%, flips and
rebalances +27% net at ~49% win rate) - a trend-following profile; top-10 episodes 59% of book PnL. Discrete trades
(one entry, fixed SL/TP, exit by SL/TP/flip/close) keep every dev year positive but dev4 4.09-4.40 / worst 0.74-1.60
(vs 5.82 / 3.41): continuous vol-targeted sizing is part of the edge. v205 stays; v208 audit PASS.

LEADER 2026-09-27 (v208, user: entries look like market, want explicit limits / market when useful): execution policy
for the v205 book orders (engine_user exec_policy hook, default unchanged). Vol-scaled limit max(0.10%, 0.25 sigma_4h)
(mean offset 0.35%, fills 41670 -> 33900): dev4 5.881 / worst 3.514 but gate DD 20.03; + market on strong opens (74
orders): 5.853 / 3.51 / 20.17; + no-trade band (fills -> 7272): 5.628 / 3.29 / 20.13. All breach DD <= 20 -> v205
stays (robust selection). Market entries do not pay the taker fee on 4h signals; the band removes 83% of the churn
for -0.2pp/month. Web: every fill is now drawn at its exact price (the old flat box used the 162-fill average).

LEADER 2026-09-26 (v165-v179, user: evaluation must match reality): engine_real (audited) adds actual signed funding,
real carry fees, capital budget, min notional; v154 = 3.71%/month there; v170 60-minute limit rest -> 3.80 (audited).
Deep learning failed again on Kaggle (v165 MLP-PLR/FT-Transformer, v167 GRU). NEW LEAD: intrabar drops >= k sigma below
the 4h open rebound by the next open (liquidation overshoot; spikes do NOT revert, v174). Taker-entry sleeve (v172):
4.60%/month; resting limit bids (v175/v176) 5.2-5.6%/month; selection-free ladder 2.5/3/3.5/4 sigma (v178): 5.51%/month
at 4h-close DD 18.6% BUT 1m-marked DD 27.8% (2025-10-10 crash) and 4.79 under cost stress -> gate fails; a stress-loss
budget on sleeve notional (v179, ex post) gives 4.14%/month at 1m DD 19.8%. Gate DD is now max(4h, 1m-marked).
Prospective paper log of the frozen dip rules: scripts/dip_sleeve_forward.py (FREEZE 2026-09-26 16:00 UTC, loop.sh).

LEADER 2026-09-26 (v158-v160): more ensemble members all dilute the v154 ensemble: ETH options in the options member
(v158 3.44%/month), Fear & Greed (v159 3.34), CFTC COT CME positioning (v160 2.68). Data added: Deribit ETH options,
alternative.me Fear & Greed, CFTC TFF Bitcoin. v154 (base + BTC options + Coinbase premium, audited bit-exact) frozen as
scripts/v154_advisor.py and logged (v154_deploy_v5). Best within DD 20%: ~3.5%/month (0.25) to 3.67% (0.28, ex post).

LEADER 2026-09-26 (v150-v157): Deribit BTC options trades 2019-2026 fetched (aggregated per 4h). Options-flow member
alone is unstable (v150), but information-diverse ENSEMBLES help: v151 (base + options) 3.53%/month, full-path DD 19.4%;
v154 (base + options + Coinbase premium, audited bit-exact) 3.52%/month, DD 19.2%, hidden year +56%, all years positive;
v155 frontier: target 0.28 -> 3.67%/month at DD 20.0% (ex post). Members that dilute: positioning (v153), DVOL (v156),
macro (v157). v152: even a 30% governor only reaches ~4.1%/month at DD 25% (leverage cap binds). v151 frozen as
scripts/v151_advisor.py (live options update each run). Gate not met; next: ETH options in the options member.

LEADER 2026-09-26 (v141-v149): best realistic configuration v144 = v142 books (selected cross-sectional deviation/rank
features vs the other majors, +0.11pp in all flat-fee scenarios) + vol-forecast sizing + tranching + 10 bps limit
execution simulated on 1m data + v110 drawdown governor at portfolio target 0.25 (ex-post frontier choice): 3.37%/month,
full-path DD 19.6%, yearly +20/+42/+89/+60/+41% (hidden year last); reproduced to the last digit by the blind
v141_v142 audit. Frozen as scripts/v144_advisor.py (ungoverned weights logged; apply the governor on paper equity).
v148 block bootstrap: median 1y +45%, P(DD>20%) 19% (conservative), P(loss) 8.5%, P(>=5%/month) 24.5%; at target 0.15
ungoverned P(DD>20%) 5%, median +30%. Rejected: cross-asset attention NN (v143), xs for all features (v145), relative
positioning (v146), 12h horizon (v147), xs vol forecast (v149). In progress: Deribit BTC options-flow features (v150;
data being fetched to data/raw/deribit_opt_20260926). Gate (5%/month at DD<=20% in all scenarios) not met.

LEADER 2026-09-26 (v127-v140, alpha-lab-leader Claude skill created at .claude/skills/alpha-lab-leader): honest
deployable candidate v133 = tranched v115 books + v129 vol-forecast sizing: 2.44/2.22/1.95 %/month (normal/fee/execution),
full-path DD 15.2/16.6/18.4%, hidden year strict 1m execution +29.0% DD 10.1% (audited exact), frozen as
scripts/v133_advisor.py and logged (v133_deploy_v2). v135 execution: limits 10 bps better than the 4h open, market at
minute 15 -> realistic 1m-execution 5y 2.24%/month, full DD 16.3%, hidden year +30.5%. v137 realistic frontier (ex post):
target 0.19 -> 2.73%/month at DD 19.3%. Rejected: halving-cycle features (v128), spot-vs-perp flow/basis (v130),
signal-strength leverage (v131), DOGE/TRX/ADA breadth (v132), bear-only shorts (v134, biased), feature selection
(v136), HGB+ridge (v138), Binance OI/long-short metrics (v139), forward-Sharpe targets (v140). Gate still not met.

LEADER 2026-09-26 (v116-v126): IMPORTANT CORRECTION (v126): the daily rebalance hour matters by luck. v115 uses phase 0
(decisions on the 00:00 UTC 4h bar), the best of six phases; per-phase ranking changes each year. Luck-free (phase-mean)
v115: 2.31%/month normal, 2.09 fee, 1.82 execution stress; worst phase full-path DD 24.3% (execution). All earlier
phase-0 results are inflated by ~0.3pp/month (relative comparisons unaffected). Other results (all audited or pending):
v117 slower rebalance worse; v118 no-trade band 0.05 +0.07-0.22pp in flat-fee scenarios but v124 shows no gain under
strict 1m execution (hidden year 33.95% vs 36.0%, orders /17); v119 nested-CV hyperparameters worse; v120 risk
frontier: full-path DD <= 20% in all scenarios only up to target 0.15; v121 bagged v103 worse; v122 28-day book neutral;
v123 multi-timeframe MA-ribbon features add nothing (daily ribbon already captures it); v125 tranching = phase mean.
Gate (5%/month at DD <= 20%) remains far: honest level ~2.3%/month at DD ~17-24%.

Exploratory (not registered): Binance vs Bybit funding differential (data/raw/bybit_20260925) is too thin for a
cross-venue arbitrage sleeve: naive sign-following earned ~1-1.4 bps per 8h settlement in 2020-21 but only 0.1-0.3 bps
in 2025-26 (autocorr 0.26-0.52), ~2-3%/yr gross on notional before 4-leg switching costs and two-venue capital.

LEADER 2026-09-26 (v111-v115): v111 Coinbase premium features rejected (hidden-year IC up to 0.29 but 2024 IC ~0;
5y worse). v112 sign classifiers rejected (0.83%/month). Longer history WORKS modestly: v113 (Coinbase BTC 2015 / ETH
2016 prefix) v96 blend 2.62%/month (was 2.47), v92 LO DD 23.5% (was 28.5%); v114 (+ Bitstamp BTC 2013-2015) v96 blend
2.74%/month, DD 22.8%, v94 LS 2.50%. v115 = v104 with v114-history v92/v94 books: 2.61%/month normal, 2.39% fee,
2.11% execution stress; full-path DD 16.8/17.3/19.1% (all <= 20%); hidden year strict 1m execution +36.0%, DD 10.3%,
Sharpe 1.88 -> NEW BEST DD<=20% CANDIDATE (audit running); frozen in scripts/v115_advisor.py (cutoff 2026-09-08),
logged prospectively as v115_models_portfolio. Governed 25% variant 3.64%/month but full-path DD 20.8-25.1%.
Gate (5%/month in all scenarios) still not met. Next: v116 nested inner-CV hyperparameters on the v114 panel.
Advisor logging: duplicate-loop rows removed (corrections.log); advisor_shadow now runs under a lock file.

LEADER 2026-09-26 (v103-v110): v103 (1d/3d horizons + order-flow features: taker buy ratio, flow imbalance,
trade size/count z, intrabar range; LS daily book) 2.67%/month, DD 24.6%; 50/50 with v96 books 2.62%/month,
worst DD 17.9% (execution stress 2.09%, 19.8%). v104 = v99 wrapper with v103 added: 2.44%/month normal, 1.95%
execution stress, worst-year DD 15.8/16.9%, hidden year strict 1m execution +28.3%, DD 11.5%, maker 85.5%;
frozen (scripts/v104_advisor.py, cutoff 2026-09-08) and logged prospectively as v104_models_portfolio.
v105 ablation: flow adds ~0.5pp/month at short horizons but hurts the 7d model. v103-v105 audited bit-exact.
Rejected: v107 intrabar 1h features (spot 1h prefix fetched) no gain; v108 4h/12h rebalancing worse than daily
under costs; v109 trailing-IC gate cuts return (0.97%/month) without cutting DD (audited exact). v110 (v104 at 25%
vol target + causal DD governor on the 90-day equity peak): 3.28%/month normal with full-path DD 19.7% (all years
positive), but fee/execution stress 2.96%/2.56% with full-path DD 21.9%/24.9% -> best return inside the 20% DD
budget under normal costs, still below the gate (audit running). Next: v111 Coinbase premium features (Coinbase
1h BTC/ETH fetched to data/raw/coinbase_20260925).

LEADER 2026-09-26 (v97-v102): audits v97 (spec-wording deviation only: leader code imputes for ExtraTrees
only; no leakage), v98 (bit-exact) and v99 (normal within 0.18pp; hidden-year 1m execution 1.26pp lower
under the blind minutes-2..15 window -> conservative figure +17.43%, DD 17.11%, maker 0.868 adopted) all
passed. New, all rejected (audit v100_v102 running): v100 4x phase-shifted 4h training rows 2.05%/month
(leaf 1200) / 2.33% (leaf 300); v101 training on majors + 13 large-cap perps (trade majors only) 2.80%/month,
DD 30%, hidden year +5.7%; v102 market-neutral cross-sectional majors book 0.25%/month alone (hidden IC
-0.02), corr 0.10 with v99; 25/75 blend 1.80%/month at DD 10%. Conclusion: more rows, more assets,
ensembles and relative-value books do not lift the 7-day trend model (IC ~0.1). Next (v103, prepared):
breadth route IR ~ IC*sqrt(N): 1d/3d horizons with order-flow features (taker buy ratio, flow imbalance,
trade size/count z, intrabar range), long/short daily book.

LEADER 2026-09-26 (after usage reset): v90 Kaggle run COMPLETE (15 checkpoints; local reload parity 3.6e-6)
but IC -0.03/0.19/0.02/0.04/-0.03 (hidden -0.028), every run early-stopped at epoch 9 -> rejected; deep
sequence models again lose to HGB. v95/v96 audited (v96 exact). v97 tree ensemble (15 HGB + ExtraTrees):
2.67%/month, worst DD 23.8% (lower return and DD than v92). v98 recency weights (half-life 2y): 2.69%/month,
worst DD 20.8% (1y: 2.21%, DD 31%). v99 deployment candidate (80% v96 books + 20% carry x3, 15% portfolio vol
target): 2.27%/month normal, 2.07% fee, 1.82% execution stress, worst-year DD 15.3/16.7/18.4%, all five OOS
years positive; hidden year with 1m execution +18.7% (1.44%/month), DD 16.6%, maker fill 90% (audits of
v97-v99 pending). v99 frozen (models trained to 2026-09-08 cutoff, scripts/v99_advisor.py) and logged
prospectively as v99_models_portfolio. Gate (5%/month) still not met; plateau ~2.3-2.9%/month at DD 15-28%.

LEADER 2026-09-26: v93/v94 audited-rejected (v94 exact; v93 within 0.41pp). v95 (rich cross-asset,
positioning, macro, DVOL features on the v92 pipeline) FAILED: IC 2021 -0.09, hidden 0.123, book
0.44%/month, DD 38.9% -> extra sources add noise (staggered start dates act as time proxies); keep
the compact v92 feature set. v96 (fixed 50/50 v92 long-only + v94 long/short, own vol targets):
2.47%/month, all five OOS years positive (+4.2/+26.8/+67.5/+48.9/+31.2%), worst-year DD 20.9%,
hidden year DD 16.4% -> most balanced so far, still below the 5% gate (audit pending).
v90 submitted to private Kaggle 2026-09-25T17:04Z (kernel nguynchtrai/v90-pooled-majors-seq v1,
dataset nguynchtrai/v90-majors-4h-bundle; single submission; hashes in v90/cloud_submission.json).

LEADER 2026-09-25 (later): v89 audited-rejected (blind audit exact on rows, IC diff 0.008). v91
audited-rejected (leader re-run 149/149 metrics identical): 3-book hidden year +10.7% realistic
execution, 0.85%/month. v92 audited-rejected (auditor's independent script reproduces all ICs,
rows and hidden +16.69%/DD 28.47% exactly on 5 assets): pooled majors HGB + 2017 spot prefix +
causal 20% vol target, positive every OOS year (+8.1/+52.6/+87.9/+56.8/+16.7%), 2.93%/month
(fee 2.73, execution 2.48), worst-year DD 28.5% -> best result of the program, still below gate.
v93 (v92 70% + carry 30% x3, 15% portfolio vol target): 2.31%/month, worst DD 21.6%, all years
positive (awaiting audit). v94 (3d/7d/14d ensemble; long/short): hidden year +45.5% DD 14.4% but
2021-23 weak -> 1.93%/month; long-only ensemble 2.45%/month (awaiting audit). v90 package under
revision (per-asset masking so training starts ~2020, open-based labels) before a Kaggle run.

LEADER 2026-09-25 (Claude Code, alpha-lab-leader skill): stale v82/v84 (never executed) and v88
(preflight only, no kernel; parent v62 kernel ended ERROR) were closed as rejected/not-executed and
rotated into v89 (A: pooled majors HGB 7d sizing), v90 (B: pooled majors sequence model, Kaggle
package; leader submits after audit) and v91 (C: 3-book portfolio 1m execution audit). Successors
inherit inactive Codex worker IDs from the registry; they are executed by OpenCode sessions
(muse-spark-1.3-contributor) under leader supervision (see artifacts/research/opencode_background).
v89 result (awaiting blind audit): IC rises with pooled data 0.036/0.032/0.066/0.129/0.168 (hidden
year); hidden-year model +10.7%, DD 5.4% at K=0.35 while unsized TSMOM lost 8.4%; 5-year monthly
0.45% (first-year overfit forces K=0.35) -> rejected vs gate, hypothesis direction supported.
Program context: RESEARCH_VF_RESULTS.md, RESEARCH_MJ_RESULTS.md, RESEARCH_MA_RIBBON_SR_EVALUATION.md.
Best gate-relevant evidence so far: 3-book portfolio ~2.6%/month OOS 2021-2026, DD 19% (not 5%).

V44 COMPLETE/REJECTED 2026-09-06: the causal v29 meta-ranker reached only
0.218%/month in execution stress with24.745% DD and66 fills; normal was
0.559%/month with28.423% DD. Read `RESEARCH_V44_RESULTS.md`.

V43 COMPLETE/REJECTED 2026-09-06: combining the v42 7-day horizon with score
tiers reached2.071%/month in execution stress at39 fills; the0.5% tier reached
1.784% with30 fills. No variant reaches the5% monthly,20% global-DD,30-fill
gate. Read `RESEARCH_V43_RESULTS.md`.

V40-V42 COMPLETE/REJECTED 2026-09-06: score tiers, cross-timeframe HGB
features, and direction/horizon filters were run over the causal v30 output.
None reached the5% monthly,20% global-DD,30-fill gate; the best was holding_7d
at2.071% monthly in execution stress. Read `RESEARCH_V40_V42_RESULTS.md`.

CURRENT BLOCKER 2026-09-06: v36-v39 local causal probes are complete and
rejected; none reaches5% monthly,20% global drawdown, and30 fills in every
scenario. Full metrics and hashes are in `RESEARCH_V36_V39_RESULTS.md`. V33
is packaged but not submitted because the approval boundary rejected sending
internal BTC research source/data to Kaggle. No upload occurred. Further heavy
progress requires explicit user authorization; do not bypass the boundary.

V33 REGISTERED/PACKAGED 2026-09-06: separate candidate-vs-WAIT action-margin
GRU was prepared for one private Kaggle run. Its fixed logit-margin inference
adapter, chronology and loss are in `configs/swing_v33_action_margin_gru.json`;
pytest passed147 tests. Package archive SHA-256 is
`915f89e4476684646f11f44895830ec6d0eadd54b21e504b94ff27287e58766f` and the
last quota snapshot was27.98 GPU-hours. Submit only once after confirming the
inventory and receiving upload authorization, then require all33 models, full replay audit and one continuous
portfolio evaluation.

V32 COMPLETE/REJECTED 2026-09-06: the top-action/WAIT causal GRU kernel
`nguynchtrai/btc-swing-v32-top-action-20260906` finished once with33/33 models;
full local replay passed (maximum error2.384e-6) and continuous replay covered
4,076 decisions. Every registered branch missed5% monthly. Best drawdown-safe
row was mean0.5x at−1.967% normal net/DD18.807%; diagnostics had MSE8.7939 vs
constant8.3653 and rank correlation−.00178. Read `RESEARCH_V32_RESULTS.md`.
V33 must separate action logits from the payoff score and register its inference
adapter before any cloud run; do not resubmit v32.

V31 COMPLETE/REJECTED 2026-09-06: private kernel
`nguynchtrai/btc-swing-v31-short-residual-20260906` finished once with33/33
models; local replay audit passed all forecasts (maximum error1.073e-6), then
continuous replay covered4,076 decisions. Best drawdown-safe mean-minus-std
0.5x was+14.244% normal net/DD15.044%/+0.396% monthly; fee stress+12.024%/
DD15.224%/+0.337%; execution stress+17.198%/DD15.031%/+0.472%. No branch
met5% monthly; the1x rows exceeded20% DD. Read `RESEARCH_V31_RESULTS.md`.
Next hypothesis must address candidate action ranking with a materially
different representation; no short-window residual or calibration duplicate.

V30 COMPLETE 2026-09-06: the pre-registered causal calibration probe of
immutable v29 predictions finished locally at
`artifacts/research/v30_v29_calibration`. Isotonic-4 at1x reached+122.798%
normal net with20.086% DD and+112.963% fee-stress net with20.473% DD; monthly
geometric returns were2.405% and2.268%. At0.5x DD stayed below11% but monthly
was only1.233%. No mapping passes the user gate; preserve every result and do
not promote or increase leverage. Read `RESEARCH_V30_RESULTS.md`.

V29 COMPLETE 2026-09-06: residual-GRU cloud export finished all33 models on
2×Tesla T4; local audit passed at maximum error5.722e-6. Best normal row was
mean-minus-std1x+29.138% net/DD26.255%; the0.5x row was+15.358%/DD13.481%
and+0.425% monthly. Read `RESEARCH_V29_RESULTS.md`; do not resubmit.

V28 COMPLETE 2026-09-06: hurdle-GRU export and all-33 local audit passed at
maximum error7.153e-6, but every continuous branch failed. Read
`RESEARCH_V28_RESULTS.md`; do not resubmit.

CURRENT VERIFIED 2026-09-06: v25 ranked-gate TCN is COMPLETE and rejected.
The private Kaggle kernel `nguynchtrai/btc-swing-v25-ranked-gate-20260906`
version1 completed with 33/33 models, full local replay/policy audit passed
(maximum error2.1458e-6), and the one-state continuous portfolio failed every
registered branch. Best v25 row is mean-minus-std0.5x normal: net−14.2073%,
DD31.9393%, 107 fills; mean1x normal is net−43.6138%, DD62.7726%, 110 fills.
Read `RESEARCH_V25_RESULTS.md`; do not resubmit v25 or deploy it.

V22 COMPLETE: ranked-loss TCN's mean1x normal row was net+17.6895% with
DD35.0154%; positive development net but still failed the user target. V23
listwise TCN and the v24 read-only calibration probes also failed. No accepted
model exists; preserve all artifacts and register any next hypothesis before
training.

V21 COMPLETE2026-09-06: full audit passed but continuous net/drawdown/fill gate
failed. Read RESEARCH_V21_RESULTS.md. No target met; v22 is the next hypothesis.

HISTORICAL v21 RUNNING NOTE: the v21 kernel is now COMPLETE and its local audit
and continuous portfolio are recorded in RESEARCH_V21_RESULTS.md. Do not treat
the older running/submission paragraphs below as current state. V19/V20 also
finished failed; no accepted trading model exists.

LATEST: v19/v20 finished and FAILED. Read RESEARCH_V19_V20_RESULTS.md;fullaudit
passed butmean1x−40.98%/DD59.82%,allcalibratednormalnetsnegative. v21nested
validation implemented andprivateuploadsession67399; nextcheckdatasetready and
sendoneT4job aftertests. Preservev19artifacts. Target5%monthly/20%DD unmet.

LATEST v19 CLOUD COMPLETE2026-09-06:33models saved/complete, all GPUparitypassed.
Full3.2GBdownload session84333; localfullreplay+portfolio pending. Do not resubmit
Kaggle. Follow RESEARCH_V19_STATUS.md; v20calibration pre-registered only after
localTCNauditpass. Target5%monthly/20%globalDD still unmet pending evaluation.

VERIFIED v19 TRAINING2026-09-06:2TeslaT4 allocated,torch2.10.0+cu128,first3/33
models complete with savedweights+GPUreloadparity; fold1 active. Stream live logs
with --follow, do not resubmit. All33required before full local replay+portfolio.

LATEST v19 CLOUD RUNNING2026-09-06: private kernel version1 now submitted to
nguynchtrai/btc-swing-v19-tcn-20260906. Dataset READY; pre-run quota29.50hGPU.
Initial log empty, actual GPU/epoch pending verification. Do not submit duplicate;
poll logs/status then download and run full local audit plus continuous backtest.
RESEARCH_V19_STATUS.md has exact identity and next commands. Older approval-block
and no-submission notes below are superseded. No local heavy training launched.

LATEST v19 2026-09-06:24.11M TCN+attention implemented and121tests passed;
private Kaggle dataset uploaded, kernel NOT submitted because automatic approval
review hit usage limit. RESEARCH_V19_STATUS.md is current resumable state. Check
dataset ready and existing jobs before submitting exactly once after permissions
recover. No local heavy training. Target5%geometricmonthly/20%globalDD unmet.

LATEST2026-09-06: v18 FAILED CPU/GPU replay atfold8;8complete +1partial checkpoint,
session61208 ended. No active local training. Heavy training now Kaggle CLI only
per user, local inference/backtest. ARCHITECTURE_REVIEW_20260906.md evaluates
suppliedTCN+Transformer design and next steps. No new cloud job yet; prior ACTIVE
paragraphs below are historical. Keep5%monthly geometric/20%globalDD target.

CURRENT2026-09-06: v17 corrected8day calibration COMPLETE; all variants fail new
geometric5%monthly target. Four-quarter1x net77.3981% in2.809years (~1.715%/month),
normalDD18.8565%,executionDD19.4311%. v18 Transformer ACTIVE session61208,
artifacts/research/swing_v18_transformer_20260906:6layers/6heads/192width,
3,056,451params,3seeds×11folds×16epochs, localGPU.110tests passed. Check it before
relaunch; final continuous/summary.json includes calendar annual/monthly returns
and explicit new-target flag. Old positive-net flag alone cannot indicate success.

LATEST2026-09-06: RESEARCH_20260906_CORRECTION.md supersedes status below.
Target geometric5%monthly after costs,annual+79.5856%,globalDD20%; deep learning
preferred. v15 COMPLETE, no target pass. Read-only isotonic+41.46% claim INVALID:
unmatured quarter-end labels leaked future outcomes; fix8day embargo and global
policy state before calibration work. Session94744 is finished, not active.

The user explicitly requested repeated autonomous research, not a final handoff
after each experiment. This document is the resumable working state, not a success
declaration. Read AGENTS.md and the dated experiment reports before acting.

## Continuation mechanism

An ACTIVE hourly heartbeat is attached to the existing task, created2026-09-05:
automation ID `nghi-n-c-u-btc-swing-li-n-t-c`, name `Nghiên cứu BTC swing liên tục`.
Do not create duplicates. Use the app automation tool to view/update its status.
Local scheduled work needs the host and app available and remains subject to
permissions and account usage limits. Do not redeem resets or buy compute.
Current turn may work continuously; hourly wakeups resume unfinished work rather
than waiting for the user to say continue. Check existing jobs before launching.

Only notify on a meaningful finding, failure, required action, or evidence-backed
milestone; no repeated unchanged status messages. If no forward candles/job changes
are available, do useful development work; do not manufacture fresh test evidence.

## Objective and boundaries

LATEST USER CLARIFICATION: No Kronos/base requirement. Any learned model or
pipeline, simple or complex, and arbitrary architecture/layer redesign is allowed
within research scope. Prefer evidence-backed learned signals; execution/risk
logic is support, not the primary predictive engine. Do not keep Kronos merely
because earlier notes or the recurring prompt prioritized it. Existing Kronos cache
is just a comparator. Profit/risk objective and no-live/no-paid-compute remain.

Find and deliver a reproducible BTC futures model/pipeline with robust net profit
and controlled risk, entry limit/SL/TP1/TP2, macro4h/1d plus micro5m/15m/1h,
roughly1–4 useful alerts/month,3–7-day positions. User maxDD20%. Fees/funding,
capital100 compounding and execution assumptions remain as in AGENTS.md.
No live orders, paid GPU, public datasets or credentials in Git. Kaggle free T4x2
allowed. ExtraTrees, boosted trees and Kronos are comparators; no family is
mandatory. Larger models require a measured hypothesis.

No finite search proves global best performance or future profit. Do not declare
success from one positive historical test, a tiny sample or leverage amplification.
Current acceptance config gives provisional floors; add seed/regime stability,
causal availability and realistic execution stress before calling a live candidate.
Keep fitting/selection on development. All opened test ranges stay in the ledger;
never silently reset their status or overwrite previous artifacts.

## Current state

NEWEST RESUMPTION: v13/v14 COMPLETE. All-seed temporal mean ensemble has positive
development net, but stitched1xDD23.9068% (fee stress24.7050%) FAILS20%; do NOT
quote only its14.4224% per-fold DD. Fixed0.5x stitched mean:100→125.6370,
DD12.6895%; execution stress+17.4605%,DD10.7955%. Flat in gaps, not full-period
evidence and original6/8fold gate still failed(5/8). See RESEARCH_RUN_LOG.md.
v15 ACTIVE localGPU session94744, artifacts/research/swing_v15_continuous_20260905.
33models,11contiguous quarters,3seeds; final continuous/summary.json will contain
ONE policy/equity state with no quarterly gaps/resets. Both mean/mean−std and1x/0.5x
are registered; no seed picking or live orders.105tests pass. No cloud job.
Prior active-session notes below are historical and superseded by this paragraph.

LATEST: v10 finished, FAILED both-delay robustness.48h meanfold+1.7084%,worstDD
15.4192%,5/8 jointlypositive;72h−1.4252%,worstDD19.8272%,3/8. See run log.
v11 first attempt59584 failed noncontiguous candidate-buffer serialization;
fixed constructor and regression test passed. Rerun ACTIVE session57591; inspect
artifacts/research/swing_v11_macro_micro_20260905_r2 before relaunch.98tests passed
beforefix plus2affected neural tests passed afterfix. First failed source preserved.
User explicitly requested schedule clarification again: existing hourly prompt
UPDATED successfully with full architecture freedom and reusable run-log contract.

AUTHORITATIVE RESUMPTION2026-09-05: read `RESEARCH_RUN_LOG.md` for compact trial
history and interpretation corrections. Writes work again;93tests passed before
the v10 runner/feature-cache validator edits (rerun after them). Cache50466 and
derivatives download99026 COMPLETE. v6 probe54873 COMPLETE; both raw40 and
raw40+Kronos fail all-seed screen. Kronos policy returns−21.1886%/−36.4311%/−16.7531%.
Derivatives features lag48/72 COMPLETE,5,628rows each; historical availability
still only a declared proxy. v10 session36977 ACTIVE, eightfold models on both
fixed delays, artifacts/research/swing_v10_derivatives_20260905. Check before
relaunch. Historical status paragraphs below retain previous states only.

LATEST USER TURN2026-09-05: model-agnostic requirement implemented; existing hourly
automation prompt UPDATED successfully (same ID and schedule).90 tests pass.
Read `RESEARCH_V8_V9_RESULTS.md`: v8 recent static two-split result looked positive,
but wider8-fold study FAILED (73 fills,4 jointlypositivefolds, worststressDD22.0652%).
v8 monthly also FAILED. v9 four-head hurdle model FAILED (64 fills,3jointlypositive,
worststressDD24.5948%). No candidate deployed and no leverage increase.
Artifacts `swing_v8_adaptive_20260905`, `swing_v8_walkforward_20260905`,
`swing_v9_hurdle_20260905` under artifacts/research. Processes53870/58939/6305 COMPLETE.

ACTIVE NEW DATA AUDIT: session99026 runs `download_derivatives_metrics.py --output
data/processed/btc_derivatives_metrics_20260905_v1`. Four publicHTTP readers fetch
Binance daily BTC metrics2022-01-01 to2026-03-22 withchecksums. Inspect progress.json,
manifest.json and process before resume; do not start duplicate. Script resumes
verified raw pairs if interrupted, completed manifest is immutable. Downloading
does NOT certify historical feature availability; feature_ready=false by design.
Once complete inspect gaps/missing-by-year and explicitly design lag/staleness
handling before any training. Missing positioning ratios in2022sample are real.
Never silently join event timestamps as contemporaneously available live data.

Existing session50466 GPU cache still active; latest observed train4448complete,
validation256/308, policy not yet logged. After final cache manifest, run existing
v6 probe command below. No cloud job currently active.

Heartbeat2026-09-05T13:47Z ran successfully in this existing task. No duplicate
automation/job created. Cache session50466 still running; current turn added an
explicit optional UTC decision anchor for future dataset builds and audited the
old clock mismatch.83 tests pass. `artifacts/research/decision_clock_audit_v1.json`
records v2/v5 timestamps and real-source history-offset invariance. Existing
datasets, frozen modules and running cache script were NOT modified.
Future neural dataset configs must set
`"decision_anchor_utc": "1970-01-01T00:04:59.999Z"` with stride72.
`build_swing_dataset.py` supports this and records clock mode in new manifests;
omitting it preserves legacy positional selection only for reproducing old runs.
The separate old `build_swing_research.py` still uses legacy stride; do not use it
for a new controlled comparison without adding explicit anchoring/versioning.

LATEST continuation2026-09-05: v5 is COMPLETE, NOT RUNNING. Full v2 and v5 weights
downloaded and hash/prediction/backtest audits passed on local GPU. v5 best epoch1,
stopped4,1204.60s, confirmed2T4 and100321928 trainable parameters. Validation308
and policy752 all WAIT. No new GPU cloud job submitted. Full v5 audit:
`artifacts/research/swing_v5_cloud_audit.json`; v2 audit:
`artifacts/research/swing_v2_cloud_full_audit.json`. Later details below are historical.

ACTIVE LOCAL WORK (check these before restarting):

- `cache_swing_context.py`, exec session50466, extracts frozen v5 context on GTX1650
  to `artifacts/features/swing_v5_context_20260905`. About52s/128 decisions;5508
  decisions total. Writes verified chunks and final manifest. Resume same command
  only if original process no longer exists. Missing chunk SHA means interruption
  requiring inspection, not permission to silently trust/overwrite that chunk.
- v7 local CPU probe COMPLETE at `artifacts/research/swing_v7_flow_probe_20260905`.
  No process32542 remains active. Both branches FAIL every-seed screen. Policy net
  raw40 seeds1729/1730/1731: -20.3310%/-12.2551%/-19.6933%; flow branch:
  -23.6995%/-31.6113%/-26.2512%. No branch advanced, no winning-seed selection.
  Full source/test77 tests passed. Execution stress preserves these conclusions.
- After Kronos context cache completes, run `probe_swing_context.py --plan
  configs/swing_v6_probe.json --output artifacts/research/swing_v6_context_probe_20260905`.
  This compares raw40 vs raw40+frozenKronos/PCA32; no cloud training or test opening.
  Persist all seeds and do not pick only winners. Scripts export portable forests
  and train-only PCA arrays; inference wiring remains to implement if promising.
- v5 head diagnostic `artifacts/research/kronos_swing_v5_head_diagnosis_v1`:
  conditional mean MSE8.09%/7.06% WORSE than train-only candidate constants.
  All expected-net outputs negative; only candidate4/12 ever rank first. This
  supports probing representations rather than another blind full-trunk rerun.
  Additional design caveat: Huber/ranking-trained point output is NOT constrained
  to estimate conditional arithmetic-mean payoff. The v5 `expected_net_percent`
  label is a legacy heuristic, not a calibrated expectation. Next model should
  separate mean-payoff estimation, tail-risk and rank/abstention, or calibrate
  utility from train/validation out-of-fold predictions before threshold use.
- New `backtest/execution_stress.py` is versioned, leaves old engine unchanged.
  Zero-stress parity passed synthetic paths plus actual v4 report. Sensitivity
  output `artifacts/research/swing_v4_execution_stress_v1`: 10bps penetration/
  market slippage and marketfee0.055% gives+5.04235%, still ONE fill. Adverse-price
  sampledDD4.43273% vs closeDD4.22281%; not true mark/intrabar risk. No live approval.
- `data/flow_features.py` uses existing total/buy volume and number of trades,
  only complete5frames backward-joined. Future/incomplete-day invariance tests pass.
  Cache `artifacts/features/swing_flow_20260905`; plan `configs/swing_v7_flow_probe.json`.

Verified decision-grid confound: v2 validation starts2025-06-09 04:14:59.999UTC,
v5 starts00:04:59.999UTC (both6h stride). Do not attribute differences between
v2/v5 trade outcomes solely to architecture/history. v6/v7 within-run branches
share exact v5 grids/labels. Future comparisons must pin a UTC decision anchor.

At an earlier attempt, app automation view and v2 audit were denied because the
automatic approval reviewer hit the account usage limit. User requested continue;
subsequent v2/v5 command executions succeeded. Never work around quota rejections.
Hourly automation was created successfully previously; status recheck was blocked,
so that status-view call did NOT succeed. The13:47Z heartbeat has now actually
arrived and performed work, providing direct evidence of a subsequent scheduled run.

- v2 Kronos-base99.86M trainable, full12-block updates on2T4; all WAIT.
  Full weights still on Kaggle, reports/predictions local. No active GPU job.
- v3 tree failed first holdout. v4 expanded-history tree has+5.1135% on reserve
  but ONE fill, not sufficient; keep frozen as comparator.
- Completed artifact paths/hash ledger: `RESEARCH_V4_RESULTS.md`.
- Head diagnosis COMPLETE: saved v2 net regression beats train-constant MSE only
  1.639% validation/2.315% policy; median temporal output std0.0825/0.0902 percentage
  points versus label std roughly2–4.7 points. Only candidates1/3 ever rank first.
  This suggests weak discrimination, not proof of insufficient model size.
- Artifact: `artifacts/research/kronos_swing_v2_head_diagnosis_v1/diagnosis.json`.
- v5 interaction head and robust/WAIT-aware ranking loss implemented separately
  in `models/swing_v5.py`; experiment plan `configs/swing_v5_experiment_plan.json`.
  Drivers `train_swing_v5.py` and `infer_swing_v5.py` reuse v2 mechanics without
  changing frozen trainer source; package/bootstrap now support v5 explicitly.
  Expanded dataset `data/processed/kronos_swing_v5_20260905`:4448 train/308 val/752
  policy. Full CPU and local GPU FP16 smoke PASS, all12 blocks changed,100321928
  trainable parameters. Smoke two-example returns are NOT performance evidence.
  49 tests pass. Full cloud training has not completed; no performance claim.
- Staging `artifacts/kaggle/kronos_swing_v5_20260905`,430936353-byte ZIP SHA256
  `5a6e79241dff99726850cbc17ff618b5b2c82e6553dae44b645f59b87f7c6cce`.
  Private dataset `nguynchtrai/kronos-btc-swing-v5-20260905-data` upload complete,
  API status READY. Kernel `nguynchtrai/kronos-btc-swing-v5-20260905` version1
  successfully submitted with T4 accelerator and timeout7200. Do NOT push again.
  API status subsequently confirmed RUNNING. Actual GPU allocation still requires
  runtime/log evidence from the job; no completed training metrics yet.
  Existing v2 status rechecked COMPLETE; credentials work. New v5 slug lookup
  returned inaccessible before creation, not a known running job.

## Ordered next work (update after actual evidence)

0. v30 is complete and rejected: do not submit another calibration, residual
   GRU or hurdle-GRU duplicate. The next research turn must first produce a
   measured diagnosis of the remaining action-selection/label bottleneck and
   register a materially different fixed hypothesis. Keep the current v29/v30
   artifacts immutable; Kaggle quota is reserved until that diagnosis supports
   one new private T4 job.
1. Complete head diagnosis, log findings below. Do not lower the trading threshold
   on an opened test to make WAIT disappear. Retrieve full v2 weights for replay
   if needed, checking existing private kernel rather than resubmitting it.
2. Design a versioned v5 neural experiment using expanded development history.
   Investigate absolute-return MSE domination, candidate ranking, outcome scaling,
   event redundancy and macro/micro feature bottlenecks. Compare robust/risk-scaled
   regression plus net-utility ranking with v2 loss; measure gradient flow/output
   discrimination. Preserve v4 source hashes: add versioned modules instead of
   altering frozen source in place. Test new losses with synthetic known outcomes.
3. Build5-frame training windows from expanded source with chronological train,
   validation and policy splits, purged labels and8-day embargo. Manifest exact
   ranges. Existing2026 intervals are development/research, not pristine test.
4. CPU/GPU smoke then one free Kaggle job at a time; record run ID before leaving
   the turn. Compare multiple fixed seeds and held-out development folds; do not
   treat training loss or parameter count as the objective. Failed experiments
   produce an explicit diagnosis and a different next hypothesis, not an identical
   rerun. Respect Kaggle quota and stop duplicate/failed runs before replacements.
5. In parallel in the research plan (not necessarily multiple agents), improve
   execution realism: mark/index candles, adverse fill/stop slippage, limit nonfill
   sensitivity, and intrabar/mark DD. Public funding/basis/OI only if timestamps
   and historical availability can be verified; never backfill future knowledge.
6. Pre-register forward paper capture using the frozen comparator, immutable
   as-of decisions and known portfolio state. Do not backdate alerts or assume
   fills before observation. New variants need a later forward registration.
7. Evaluate net after costs, PF/trade count/concentration, drawdown and stability;
   confidence-sizing calibration stays separate. Keep iterating development when
   a model fails. On a genuinely sufficient candidate, notify user with artifacts
   and remaining risks; do not mark the project complete merely because a turn ends.

## Run log

- 2026-09-05: hourly continuation created successfully. No paid resources or live
  execution enabled. v2 head diagnostics completed;45 tests passed before v5 prototype.
  Added v5 candidate interactions and robust/ranking loss with dedicated tests.
- v5 dataset complete; CPU/GPU smoke and49 tests pass; private upload READY and
  version1 submitted. Smoke audit `artifacts/research/swing_v5_gpu_smoke_audit.json`
  verifies hashes, full-trunk probes, predictions (max error0.0004883) and backtest.
  Inference v5 loads successfully. These smoke outputs do not establish utility.
  Next inspect existing kernel status, then download outputs to a NEW ignored
  `artifacts/kaggle/swing_results_v5` folder when complete. Use
  `scripts/audit_swing_v5.py` for v5 class-aware full weight replay. Read diagnosis
  and policy reports, compare constants/v2/tree and evaluate next ablation/seed.
  Kernel internally refuses anything other than2T4. Allocation not yet confirmed
  by a runtime artifact; submission acknowledgement is not training completion.
  Keep package frozen; do not modify its hashed code/data after submission.

```powershell
$env:PYTHONUTF8='1'
.\.venv\Scripts\kaggle.exe kernels status nguynchtrai/kronos-btc-swing-v5-20260905
.\.venv\Scripts\kaggle.exe kernels output nguynchtrai/kronos-btc-swing-v5-20260905 -p artifacts/kaggle/swing_results_v5
.\.venv\Scripts\python.exe scripts/audit_swing_v5.py --checkpoint artifacts/kaggle/swing_results_v5/checkpoint --dataset data/processed/kronos_swing_v5_20260905 --output artifacts/research/swing_v5_cloud_audit.json
```

If kernel fails, preserve the log and exact failure before fixing; create a new
version only after diagnosis. If quota blocks GPU, use local development/forward
capture tasks while waiting; do not silently buy compute or reuse a test as fresh.
