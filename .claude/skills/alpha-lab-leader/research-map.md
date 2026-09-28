# Research map (update after every rotation)

Last update: 2026-09-28 (after v222).

## Honest status

EXECUTABLE TRADE MODE (user rules 2026-09-28: one resting limit order, no fill in the first 5 minutes after the 4h close, in a
position only SL/TP edits and discrete limit adds/reduces/exits, market only for stops; engine_user `trade=` + `trade["policy"]`):
best = v218 D2 = v216 G2 grid trader (limit size adjustments at most once/day when |target - w| > max(3%, 40% target), limit exit on
signal loss, break-even +2 sigma_d) + dip sleeve budget 0.15 / rung x1.75: dev4 5.26, worst year 2.18%/mo, DD 19.1, win 51%, final
5y 4.97, last year 3.82 (scored once). Deployed: scripts/forward_trade.py (FREEZE 2026-09-28 08:00 UTC) -> web trade plan.
Tried in this family (all audited): v208 execution policy (vol limit / market / band) DD > 20; v209 luck tests (alpha t 3.5, placebo
0/40, beta 0.08) + discrete fixed SL/TP 4.1-4.4; v210 trade mode T1-T3 (T2 4.47/DD 25.5); v211 risk sizing worse; v212 scale in/out
S3 4.83/DD 20.7; v213 limit exit on signal loss E1 4.22/DD 19.3; v214 value RL (fitted Q / MC) 3.3-3.8; v215 one-step improvement
cross-fitted 3.2-3.6 (value estimates favour early exits); v216 grid G1-G3; v217 ES policy search 4.0-4.6 (does not transfer);
v218 DD budget -> sleeve best; v219 sleeve budget 0.18-0.21 DD > 20; v220 learned dip-bid filter hurts; v221 exit hysteresis ~equal;
v222 sub-account bot ensembles ~equal. Diagnostic (dev only, not registered): dip-bid outcome vs open-interest drop at the fill
(5m metrics) - Spearman ~0, sign flips by year -> no liquidation-flush edge.
PLATEAU: every management layer lands at dev4 ~5.1-5.3 and last year ~3.8-4.0 at DD ~19 -> the foundation signal is the limit.
v223-v228 (all rejected, D2 stays): foundation component mixes slower/faster (0.25/0.25/0.5 local optimum), no long-only + trim
(best worst year 2.47 but dev4 4.97), member D / monthly schedule, causal coin bandit for the sleeve (DD > 20), deeper limit
offsets (non-monotone noise). Dev-only diagnostics: time-of-day / weekend dip effects unstable; per-coin sleeve XRP/SOL best, BNB
weakest. D2 robustness (research/diagnostics/d2_robustness): no losing year under cost stress, 15-60 min latency or any single
parameter shift; latency costs ~0.6pp/month at 30 min -> pipeline cycle now runs 1 minute after the close.


USER-RULE ENGINE (engine_user, 2026-09-27; limit entry + SL market + TP limit per position, maker 0.02% / taker 0.055%, adverse funding, no carry; selection on first four years): v188 v154+sleeve SL m=4: 5y 3.53, last year 3.55, DD 19.0; v189 comparison selects v151+sleeve (dev4 3.90) -> 5y 3.58, last year 2.34, DD 19.4. Gate needs 5y >= 5, last year >= 5, no losing year, DD <= 20. Then: v190 bracket (triple-barrier) targets rejected (2022 IC ~0); v191 sleeve rung stop 5 sigma best (dev4 4.05); v192 book limits resting the whole bar (4.07); v193 STOP-RISK sleeve budget X=0.08: dev4 5.046 (first >= 5), DD 19.3, 5y 4.60, last year 2.85 (+40%) -> fails on last year; v194 sleeve TP 1 sigma stays best; v195/v196 books-vs-sleeve allocation: keep books at 0.25 (sleeve is capacity-limited by rung size); v197 rung size x1.5 with budget 0.12: dev4 5.562, DD 19.32, 5y 4.996, last year 2.761 (+38.7%) -> BEST under user rules; fails only on the most recent year. v198 TSMOM blend hurts every year. v188 audit -> engine fix: 1m DD peaks include intrabar highs, stop wins same-minute ties; v197 re-scored DD 19.72 (v199). v199 ladder to 6 sigma: dev4 5.71 but DD 20.27 (excluded). v200 closer book SL/TP (user range) hurts (DD > 20); v201 hourly ladder fails (DD 39.7); v202 quarterly retrain helps weak years but DD 22.5; v203 annual+quarterly ensemble dev4 5.52 (better worst year, not selected under the mean criterion). ROBUST CRITERION from v204 (worst dev year). v204 sleeve aligned with book direction (x1.5 long-book / x0.5 otherwise): dev4 5.87, 5y 5.33, last year 3.21, DD 19.46 (gain carries to the unused last year). v205 annual+quarterly book ensemble + aligned sleeve: dev4 5.82, worst dev year 3.41, 5y 5.49, LAST YEAR 4.15 (+63%), DD 19.76 = NEW BEST (fails only on the last year; audited). v206 +member D and v207 +monthly schedule both worse (DD > 20). OVERFIT WARNING: dev4 rose 3.90 -> 5.56 across v189-v197 while the untouched last year only moved 2.34 -> 2.76.

| candidate | normal / fee / execution %/month | full-path DD | hidden year (strict 1m exec) |
|---|---|---|---|
| **v183 = ladder + TP maker exit at L(1+sigma) + budget on OPEN sleeve notional (audited)** | 4.28 (stress 3.88) | 18.8% 4h / 19.0% 1m (stress 19.1) | +67% |
| v179 = v178 + stress budget on sleeve notional (<= 1/6 equity, ex post) | 4.14 (stress 3.73) | 18.2% 4h / 19.8% 1m | +68% |
| v178 = selection-free ladder of limit bids (2.5/3/3.5/4 sigma) inside the vol target | 5.51 (stress 4.79) | 18.6% 4h / 27.8% 1m-marked (2025-10-10) | +106% |
| **v176 = v154 books + v170 exec + v175 limit dip sleeve inside the portfolio vol target (audit pending)** | 0.25: 5.24 | 20.7% (2021) | +123% |
| v175 = same, sleeve outside the vol target (audit pending) | 0.25: 5.63 | 22.8% | +119% |
| v172 = taker-entry dip sleeve, crash-aware slippage (audited) | 0.25: 4.60 | 22.4% | +92% |
| **v154 + v170 execution (60-min rest) on engine_real, audited** | 0.25: 3.80 | 18.9% close | +64.7% |
| **v154 on engine_real (actual signed funding, real carry fees, capital budget, min notional; audited PASS)** | 0.25: 3.71 | 18.9% close / 19.0% true 1m-marked (v169) | +63.0% |
| **v154 = (v144 + options + Coinbase-premium books)/3, realistic engine, 20% governor** | 0.25: 3.52; 0.28: 3.67 (v155, ex post) | 19.2% / 20.0% | +56.3% (0.25) |
| v151 = 0.5 v144 + 0.5 v150 (options-flow) books, realistic engine, governor, target 0.25 (ex post)** | 3.53 (realistic 1m path) | 19.4% | +36.5% |
| v152 frontier with a 30% governor (user decision) | 0.30: 3.76; 0.35: 3.93; 0.40: 4.09 | 25.0-25.3% | cap 2x binds |
| v144 deploy v3 = v142 xs books + 10 bps limits (1m) + v110 governor, target 0.25 (ex post)** | 3.37 (realistic 1m path) | 19.6% | +41.3% |
| v142 xs features (v133 pipeline, flat fees) | 2.55 / 2.33 / 2.06 | 16.3 / 17.2 / 18.3% | +31.2% |
| v133 deploy v2 = tranched + vol-forecast sizing (best honest)** | 2.44 / 2.22 / 1.95 | 15.2 / 16.6 / 18.4% | +29.0%, DD 10.1% |
| v133 + v135 limits 10 bps, realistic 1m execution 5y | 2.24 (single realistic path) | 16.3% | +30.5%, DD 9.7% |
| v137 realistic frontier (ex post) | target 0.17: 2.49; 0.19: 2.73; 0.21: 2.93 | 17.9 / 19.3 / 20.3% | |
| v127 = v115 tranched (deployable, luck-free) | 2.38 / 2.16 / 1.88 | 16.8 / 18.2 / 20.2% | +30.2%, DD 10.0% |
| v115 phase mean (v126) | 2.31 / 2.09 / 1.82 | up to 20.9 / 22.4 / 24.3% | phase 0: +36.0%, DD 10.3% |
| v129 vol-forecast sizing (phase mean) | 2.37 / 2.15 / 1.88 | 19.8 / 21.2 / 22.8% | - (small real gain, adopt next) |
| v120 frontier (v118 band 0.05) | target 0.15 -> 2.68 normal; 0.18 -> 3.06 at DD 20.4-21.4% | | ex-post risk dial |

FRONTIER (v186_frontier.py, ex post diagnostic, engine_real + sleeve, gate DD = max(4h, 1m)): target 0.25/0.28/0.31/0.34 -> majors sleeve 4.28/4.51/4.62/4.73 %/month at DD 19.0/20.0/21.7/22.5; 11-asset sleeve (research only) 4.29/4.44/4.57/4.64 at 17.7/18.7/19.8/21.1; stress ~0.4-0.5pp lower. CORRECTION (v187): at target 0.25 the 2x cap rarely binds (mean scale ~1.5); a confidence-gated 2/3/4x cap with Binance margin + 1m liquidation checks gives 4.33 (no liquidations) - the governor/DD, i.e. the return/DD ratio, is the real limit; more risk adds ~0.1pp per step. Ceiling ~4.5%/month at DD 20% (normal), ~4.0% (stress). Newer: v184 hourly ladder 3.89 (crowds budget), v185 sleeve outside governor 4.31 (neutral), v186 11-asset sleeve 4.29 at DD 17.7.

Gate (5%/month at DD <= 20% in all scenarios) not met. v148 bootstrap of v144 (target 0.25): median 1y +45%, P(DD>20%) 19%, P(loss) 8.5%, P(>=5%/month) 24.5%; at 0.15 ungoverned P(DD>20%) 5.4%, median +30%. Frontier: 5%/month would need DD ~35-40% with the
current signal (IC ~0.1 at 7d, ~0.05 at 1d; Sharpe ~1.5-1.9).

## Building blocks (audited, reuse via importlib from `research/parallel/rounds/parallel-20260906-r2/`)

- `v92/v92_pooled_hgb_vt.py`: pooled 5-majors 4h panel (`build`, `features`, `load_asset` with 2017 spot prefix),
  7d vol-normalised target, `train_predict`, `weights_from` (long-only, daily ribbon gate), `vol_target_scale`
  (20%, cap 2), `simulate`, `stats`, `SCEN`, `ANCHORS`, `EMBARGO_BARS`.
- `v94/v94_long_short_ensemble.py`: horizons 18/42/84 ensemble, `add_targets`, `weights_ls` (long/short).
- `v103/v103_flow_short_horizon.py`: 1d/3d targets + order-flow features (`build`, `flow_features`, `train_predict`,
  `evaluate`, `FLOW`, `HS`, `EMBARGO`).
- `v113/v113_longer_history.py` + `v114/v114_bitstamp_history.py`: extended panel (Bitstamp BTC 2013 + Coinbase BTC
  2015/ETH 2016 + Binance). Pattern: `ext = v115.v114.v113; v115.v114.v113.cb_bars = v115.v114.cb_bars_ext;
  ext.v92.load_asset = ext.load_asset_ext; p92 = ext.v92.build()`.
- `v115/v115_candidate.py`: `books_v115()` (0.25 v92 LO + 0.25 v94 LS on the extended panel + 0.5 v103 LS).
- `v110/v110_dd_governor.py`: sequential portfolio engine `run(panel, books, target, governed, fee, slip)` +
  `summarize` (80% books + 20% carry x3, portfolio vol target, cap 2; full-path DD).
- `v104/v104_candidate.py`: `fill_strict` (strict 1m execution), `HIDDEN`.
- `v125/v125_tranching.py`: `raw_lo`, `raw_ls`, `phased(W, phases)`; `v129.phase_mean(ext, p92, p103, lo, ls, fl)`.
- `v118/v118_no_trade_band.py`: `run_band` (per-asset no-trade band).
- Data: `data/raw/ma_ribbon_20260924` (BTC perp), `xs_universe_20260924` (other perps), `spot_majors_20260925`
  (spot 4h/1d + 2017 prefixes + 1h prefix), `majors_intraday_20260924` / `btc_intraday_20260924` (1m/15m/1h),
  `coinbase_20260925`, `bitstamp_20260925`, `bybit_20260925` (funding), `artifacts/research/carry/carry_oos_fee0.0004.parquet`.

## Evaluation standard (2026-09-26, user: match reality)

GATE DD = max(4h-close full-path DD, 1m-marked full-path DD incl. open sleeve positions). Stress row = maker 0.0004 / taker 0.0007 + 5 bps on taker fills.

`engine_real/engine_real.py` (`evaluate(books, opens)`, cached v154 books in artifacts/research/engine_real/): v144 loop +
actual signed Binance funding at the t+2 settlement, carry with spot 0.1% + perp taker 0.05% and t+2 funding, capital
budget (spot cash + perp gross/5 <= 95%), min notional at 10k USDT, intrabar DD bound. Ablation on v154: funding +0.20pp,
carry +0.02, budget -0.04, min notional 0. engine_real audit PASSED (bit-exact, funding timing verified). Report both engines for new versions.

## Tried and rejected (do not repeat without a new hypothesis)

Patterns (candles/chart), indicators, MA S/R bounces (15m-1d), 4h/weekly MA-ribbon features (v123), seasonality,
macro, DVOL, on-chain, positioning, breadth, ORB, pairs, lead-lag, capitulation; deep sequence models (v90 Kaggle
TCN+Transformer IC ~0); rich cross-asset features (v95); ExtraTrees/HGB ensembles (v97), bagging (v121); recency
weights (v98); 4x phase-shifted rows (v100); training on 13 alts (v101); market-neutral XS books (v102);
intrabar 1h features (v107); rebalance every 4h/12h (v108) or slower (v117); trailing-IC gate (v109);
Coinbase premium (v111, unstable); sign classifiers (v112); nested-CV hyperparameters (v119); 28-day book (v122);
no-trade band (v118 gain vanishes under strict execution, v124); tranching as a return booster (v125 = luck-free
level); halving-cycle features (v128, memorises 2-3 cycles); spot-vs-perp flow/basis (v130); signal-strength
leverage (v131, just more exposure); nested permutation feature selection (v136: 1.97%/month, worse); HGB+ridge blend (v138: 2.08, ridge IC unstable); Binance positioning metrics OI/long-short (v139: IC up 2022-24 but hidden year down, 2.42 vs 2.44); forward-Sharpe targets (v140: 1.37); cross-asset attention NN (v143: IC negative 2021-22, blend 2.36); xs features for ALL features (v145: 2.20, dilutes); relative positioning (v146: 2.52, DD 25%); 12h horizon in v103 (v147: neutral 3.33); xs vol forecast (v149: neutral); ensemble members that DILUTE: positioning (v153), DVOL (v156: 2.98), macro (v157: 2.94), ETH options added to the options member (v158: 3.44), Fear & Greed (v159: 3.34), CFTC COT (v160: 2.68); options flow alone (v150: 3.47/19.2 but hidden year +27% vs +41%); bear-only shorts (v134: lower DD 12.8% but 2.30%/month, hidden year +21% - diagnostic-motivated, keep only as a prospective hypothesis); trading DOGE/TRX/ADA as extra assets (v132: 2.13%/month, DD 24%, new assets IC ~0-0.04); cross-venue funding arbitrage (Binance vs Bybit, 0.1-0.3 bps/8h now); deep tabular MLP-PLR + FT-Transformer member on Kaggle (v165: IC ~0.03, val loss best at epoch 0, (A+B+D+E)/4 3.41 vs 3.52); agreement confidence (v166: neutral 3.55); quantile-HGB uncertainty sizing of v103 (v168: 2.67, median model loses signal; audit: median-only 2.66); 1m intrabar portfolio stop at k*sigma (v169 on engine_real: k=3 2.71, k=4 3.05, k=2 2.02 vs 3.71, DD not lower - intrabar dips mean-revert); GRU over 42 4h bars on Kaggle (v167: IC ~0/negative 2021-24, blend 3.15; 4th DL failure); funding-settlement microstructure (research/diagnostics/funding_settlement, PRE-ANCHOR data only: post-settlement +17 bps sits in the settlement minute itself, from S+1 only +4 bps gross = -10 net; pre-settlement effect only with the unknown final rate = look-ahead, -3 bps with the known previous rate) - rejected without touching test years; v177 sleeve concurrency cap (4.71/21.1); v180/v182 rebound gates (selection is not the binding constraint; budget is).

## What worked (keep)

Pooled majors HGB (v92), 2017 spot prefix, causal vol targets, long/short horizon ensemble (v94), blending books
(v96), funding carry sleeve (v99), 1d/3d order-flow model (v103, +0.5pp at short horizons), longer history
(v113/v114), vol-forecast sizing (v129, small), 10 bps limit execution (v135), selected cross-sectional features (v142, +0.11pp), realistic governor at higher risk (v141/v144), actual funding in the engine (engine_real, +0.19pp), 60-minute limit rest window (v170 audited: 3.80 vs 3.71, maker share 0.64 -> 0.81, all years better).

## Idea queue (next)

- NEW LEAD (v171, audit pending): intrabar dip-reversal sleeve on 1m data (buy after close <= -k sigma of the 4h open in minutes 16..238, exit next 4h open, taker both sides, k walk-forward): sleeve alone +8..+65%/yr, DD 7-9%, corr 0.04 with v154; v154+sleeve 5.96%/month but DD 21.85%. Robust to 10 bps slippage and 1-5 min delay (ex post diagnostic); top events are real crashes. v172 = crash-aware slippage + v170 execution. v173 learned rebound model: IC 0.08-0.17 but pred>0 too lax (3.98/25.1, rejected). v174 spike fade: spikes do NOT revert (rejected). v175 limit bids (maker on trade-through) let k 2.5-4 pay: 5.63/22.8. v176 sleeve inside the vol target: 5.24/20.72. Prospective log: scripts/dip_sleeve_forward.py (limit k=3.5 and taker k=4, FREEZE 2026-09-26 16:00 UTC, matches research events exactly).

- Information-diverse ensembles work only with members that are good alone (options, Coinbase premium). Next: ETH options (download running to data/raw/deribit_opt_20260926/ETH_options_4h.parquet) as part of the options member (v158).
- v151 frozen: scripts/v151_advisor.py (+ scripts/deribit_options_update.py appends live 4h options aggregates each run; backup BTC_options_4h.backup_20260926.parquet), logged as v151_deploy_v4.
- Data added: data/raw/deribit_opt_20260926 (BTC options trades aggregated per 4h, 2019-2026; research/mj/fetch_deribit_options_4h.py).

0. Frozen advisors: v154 (scripts/v154_advisor.py, best: base + options + Coinbase model sets; updates Coinbase/spot via scripts/coinbase_spot_update.py and Deribit via scripts/deribit_options_update.py each run), v151, v144 (scripts/v144_advisor.py, ungoverned weights at target 0.25; apply the governor on paper equity). Data added: data/raw/um_metrics_20260926 (Binance metrics 5m, BTC 2020-09+, others 2021-12+).

1. Execution adopted (v135): rest limits 10 bps better than the 4h bar open, market fallback at minute 15 (+~2pp/yr). 1 bp of cost per unit turnover ~ 0.055 pp/month.
2. Deployment v2 (v133) is frozen: scripts/v133_advisor.py (vol models artifacts/research/advisor_shadow/v133_vol_models.pkl, cutoff 2026-09-08), logged as v133_deploy_v2.
3. Kaggle (with authorization) only for a materially new model on the extended panel; DL has failed so far.
4. More history for XRP/SOL/BNB (other venues) if a source with clean hourly data exists.
