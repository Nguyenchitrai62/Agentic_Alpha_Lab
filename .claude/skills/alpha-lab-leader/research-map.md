# Research map (update after every rotation)

Last update: 2026-09-30 (after v284).

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
v229 hourly dip ladder in trade mode (bids x4, 2022 -30%, DD 42-44: rejected). v230 Korean (Upbit) premium member K (USDKRW lagged 2 days; K alone dev4 3.69 -> dilutes like DVOL/macro/COT; best K3 replace A 4.98 DD 20.09: rejected). Dev-only diagnostics (not registered): D2 DD episodes - worst (2023-04..06, 17.2%) is 11pp dip sleeve; the sleeve earns most of the return (2021-24: +27.5/+5.5/+54.7/+44.6% of equity vs books ~+1/+32/+37/+59) and is uncorrelated with the book; sleeve losses are NOT serially dependent (daily autocorr 0.03-0.06, next-week return after a sleeve drawdown equal or better) -> equity-curve throttles would hurt. Untested data left: none of note (on-chain / stablecoins / OI / options / Coinbase / Korea / macro / COT / F&G / DVOL all tried).
QUALITY DATA (user 2026-09-28): data/raw/binance_premium_20260928 = Binance 1m premium-index klines + settled funding, 5 majors, 2020-01.. (scripts/fetch_binance_premium.py); predicted funding reconstructed exactly (MAE 0.05-0.07 bp; BNB interest 0). Funding-hunter study (pre-anchor only, research/diagnostics/funding_premium): positive predicted funding -> premium pushed down in the last minutes, price +14 bps in the 15 min after the settlement (t 7.5); negative -> +15 bps before, -20 after; the move sits in the settlement minute -> not tradable with the minute-5 rule, used as features. v231: TradingView indicators (v231/tv_indicators.py, 17 causal features) in member A = FIRST foundation gain in a long time: dev4 5.46, 5y 5.115 (first >= 5), DD 20.0, last year 3.74; premium+F&G member worse (dilutes, DD 23). Next: TV features in the quarterly half, RL v232 on the V1 foundation.
v232 disciplined RL (cut losers only; dev DD -1pp, last year 3.13) rejected; v233 T3 (TV in all members) 5y 5.156 DD 18.41 last 3.851; v234 daily/weekly TV (dev 5.82, last 2.94) rejected; v235 TV-state dip-bid bandit (sleeve still unpredictable) rejected. BEST: v236 W2 = T3 + WHALE FLOW (Binance aggTrades taker flow by order size, v236/flow_features.py) in the A members: dev4 5.774, worst dev year 2.491, DD 19.51, 5y 5.442, last year 4.123 (scored once), hidden win 54.8% - first time new data lifted dev mean, worst year and the unseen year together. W1 (flow in all members) DD 27. Next: live whale-flow feed (daily archive + websocket), flow x open-interest composites.
v237 spot vs perp whale flow (data/raw/aggflow_spot_20260928): DD 21-22, rejected; v238 market-wide flow (BTC + cross-asset mean): DD 22-24, rejected -> per-asset perp flow (W2) is the useful form; more features on top of W2 raise DD. W2 robustness (research/diagnostics/w2_robustness): no losing year under cost stress / latency / parameter shifts; latency > 15 min hurts (30 min: DD 24); bootstrap median 5.33%/mo, P(loss year) 1.1%, P(DD>20) 7%. Deployed paper pipelines: D2 (v205 books), T3, W2 (live flow via scripts/aggflow_live.py + daily archive in the backend).
v240 O1 (order-level whale flow) = robust best (worst dev year 2.759, DD 19.08, 5y 5.364, last 4.069). Rejected on O1: v241/v242 learned sizing (per bar = churn; entry-locked = no gain), v243 flow-state dip filter, v246 W2+O1 ensembles (last year 4.28 but worse dev worst year). v245 SMALL ACCOUNT: Bybit lot minimums (BTC 0.001, ETH 0.01, SOL 0.1, BNB 0.01, XRP 0.1, 5 USDT) make BTC/ETH impossible at ~100 USDT (44% of O1 orders placeable; 96% at 1000 USDT); SOL/BNB/XRP-only O1 = dev4 4.55, last year 2.56. Dip intrabar diagnostic (dev only): fast pre-fill drops revert better (speed Spearman negative all 4 years) but every quintile is positive -> cancel rules cannot help; the sleeve's limit is the risk budget / DD, not selection (4th confirmation).
v244 Bybit cross-venue order flow: DD 22 (3rd flow extension raising DD; flow direction closed). v247 O1 sleeve budget 0.18 = current best (dev4 5.777, worst dev year 2.854, DD 19.65, 5y 5.436, last 4.082). v248 learned dip-EXIT agent (TP multiple at the fill, exact counterfactuals, engine hook sleeve_tp): dev4 6.05 (largest dev gain) but DD 20.7 and last year 3.85 -> rejected; fixed TP 1.0 sigma is the best fixed rule (0.5: 4.70, 1.5: 5.30, 2.0: 5.01). Data: aggTrades fetcher now keeps a 1m store (8 log-size bins) so future flow features need no re-download.
v249 learned ladder-depth window (six rungs, sleeve_filter): D1 DD 22.6, strict = reference -> rejected. v250 per-rung weights: inverse (heavier near) P3 dev4 5.914 / worst 2.968 / DD 19.0 / 5y 5.525 but last year 3.98 (< 4.082) -> no transfer; pyramid (heavier deep) worse. v251 strategy-level vol targeting (engine hook strat_vt): V1/V2 DD 28-30, de-risk only 4.32 -> rejected; the dev diagnostic (calm -> higher next-month return, all 4 years) was confounded by the 20% governor. Dev-only, not registered: 2023 DD = one bar 2024-08-05 (sleeve -12.3%); 5th-coin (market-wide) fills: most stops but positive mean; slide ladder vs 24h high: incremental fills ~0/negative. Sleeve knobs exhausted: TP (v248), depth (v249), size by depth (v250), budget (v247), selection (v220/v235/v243), concurrency (v177).
v252 intrabar whale flow from the 1m order-level store (in A members): dev below O1 -> rejected. v253 OKX cross-venue flow: registered, DEFERRED (user: OKX incomplete - starts 2021-10, BNB 2022-12 - keep as option; data kept in data/raw/okxflow_20260929). v254 adaptive ladder spacing by current 1m RV: much worse (buys ordinary pullbacks). Premium/predicted funding INSIDE A was already tested in v231 V2/V3 (worse) - do not repeat.
v255 dip ladder from minute 5/10 instead of 16: neutral (last year identical). OpenCode whale-burst reversal study (dev only, research/diagnostics/whale_burst): 0/108 stable rows, all negative, worse than random entries -> closed. O1 B18 ROBUSTNESS (research/diagnostics/o1_robustness, OpenCode): no losing year in any stress row, win 0.50-0.53 everywhere; DD FRAGILE (base 19.65; cost stress 20.75, latency 30 min 21.08, 60 min 23.18, band shifts 20.4-21.0, cool 12 22.7); bootstrap P(loss year) 1.4%, P(DD>20) 6.8%, P(>=5%/mo) 55%; at 2000 USDT 99% of book and 98% of dip orders placeable. A live bot must act within ~15 minutes of the 4h close.
v256 RL entry-execution bandit (limit offset per opening order, exact counterfactuals): neutral (agent deviates on 5-8%). v257 sequential PPO trader (per-coin simulator, walk-forward, engine evaluation): pure PPO trades win rate for return (win 56.5%, dev4 3.9, median hold 20h - cuts trends, as v214); PPO + rule prior = rule. RL CONCLUSION (10 learned layers): the rules are near-optimal given the information; learned managers either copy the rule or cut the fat-tailed trend trades. Next gains must come from new information.
v258 disciplined PPO (G2 pyramiding simulator, fidelity 0.985 vs engine; cut losers only): worse (win 43-49%, DD 20.6-26.7). v259 PPO daily RISK MANAGER (multiplier 0.5-1.25 on the governor, DD-aware reward): seed 259 passed the whole gate (5y 5.114, last 5.309, DD 17.45) BUT the seed diagnostic (4 other seeds, research/diagnostics/v259_seeds) gives last year 2.3-3.6, dev4 4.5-5.0 -> seed luck, rejected. RULE: every stochastic learner (PPO / NN) must report >= 5 seeds before any claim.
v260 PPO risk manager on block-bootstrapped paths, 5 seeds: median dev4 4.47, last year median 3.13 -> the stable learned policy is plain de-risking (no timing skill); not adopted. v258/v259 audits PASS (no leakage; v259 gate pass genuine for seed 259, seed-unstable). Dev-only diagnostic: BTC-hedging alt dip fills keeps only 15-30% of the edge (the sleeve is a market-rebound bet) -> closed.
v261 direct-reinforcement foundation member (differentiable net Sharpe, policy gradient, 5 seeds): member IC ~0-0.07 -> dilutes (dev4 5.50 / 5.58). RL now tried at every level (sleeve bandits, entry/exit bandits, fitted-Q, PPO trade manager, PPO risk manager, direct-RL member): 14 variants, none beats the O1 rules out of sample.
v262 Binance SPOT order-level flow (2017+, kept store): add DD 22.4, perp+spot sum DD 20.8, dev below O1 -> rejected; all venue / market extensions of whale flow (v237, v238, v244, v262; OKX v253 deferred) raise DD. Data catalog: docs/DATA_CATALOG.md.
v263 meta-labeling of entries (win classifier, skip p<0.35/0.40): +0.04pp dev, win rate unchanged (skips re-enter next bar) - neutral.
NEW BEST CANDIDATE (audit + robustness pending): v266 B1 = O1 B18 + dip-rung stops triggered on a 5m-block CLOSE (bot-watched, exit at the next minute open) + an 8-sigma exchange-native touch backstop: dev4 6.13, worst dev year 3.257, DD 19.70, 5y 5.795, most recent year 4.464 (scored once) - better than O1 on every selection metric and on the unseen year. Origin: dev event study of 2024-08-05 (18 rungs stopped at a liquidation-wick low, then recovery). v265 S2 close5 without backstop 6.178 / 19.29; v264 circuit breaker neutral; B2 (budget counts the 8-sigma stop) 5.725 / DD 18.08.
B1 robustness (research/diagnostics/b1_robustness): return higher in every stress row (+0.27-0.39pp dev4; bootstrap P(>=5%/mo) 60% vs 55%, P(loss year) 1.0% vs 1.4%) but DD worse in 12/13 rows (cost stress 22.8 vs 20.75, latency 15 min 21.9 vs 19.8); bot outage (8-sigma backstop only) safe (DD 18.7). -> v267 selects under a stress-robust rule (dev DD <= 20 in base, cost stress, latency 15).
v267 stress-robust selection (dev DD <= 20 in base, cost stress, latency 15): EMPTY pool - no design (not even O1: cost stress 20.75) holds the stress rows; rule keeps O1. DEPLOYED 2026-09-29 as an extra PAPER pipeline: C5 = v266 B1 (forward_trade --candidate v266_B1, backend history_tm 'v266', FE pipe C5) next to O1 (O1 stays the default / recommended view).
v268 book close stops: DD 21.6-21.9 (touch stays right for the book). v269 close-stop distance: 4 sigma DD 18.27 dev4 6.03 last 4.645 (robust criterion keeps B1); v270 stress rule on it: cost-stress DD 20.23 -> pool empty by 0.23 pp, O1 kept. v271 RL optimal-stopping agent for losing dip rungs (exact returns): early cuts free budget for deeper rungs of the same flush -> DD 21.3, rejected.
v272 = v271 + budget lock: identical results (freed-budget hypothesis falsified; wrong cuts miss recoveries). v273 book target 0.27 / 0.29 on M1: dev4 6.12 / 6.21 but weaker weak years (robust criterion keeps M1); T1 last year 4.684 (best unseen-year score so far, still < 5).
v274 dip TP 1.25 / 1.5 sigma under close stops: DD 26.6 / 27.4 -> TP 1 sigma stays optimal (non-TP rungs fall back).
Dev-only diagnostic (research/diagnostics/dip_carry): holding timed-out dip rungs 4h / 8h past the bar end under M1 rules is not consistent (2021 / 2023 negative, late fills worse, q01 -7..-9%) -> no cross-bar dip holding.
v275 hourly dip ladder WITH close stops: 2022 -35%, DD 44.7 -> hourly dips continue; the hourly ladder is closed for good (3rd failure).
v276 rung size 2.0 / 2.25 on M1: DD 20.5 / 22.0, weak year down -> M1 sits at the frontier.
Dev-only diagnostic (research/diagnostics/dip_funding): M1 dip outcomes by predicted-funding / premium-z quintile flip sign between years (2021 high = worst, 2023/2024 high = best) -> no funding-state sizing of the dip rungs.
v277 aligned dip sizing re-tuned under close stops: neutral ((1.5, 0.5) stays). Close-stop family fully explored (v264-v277).
v278 50/50 sub-accounts of stop designs (B1+M1: 6.08 / 3.11 / DD 18.4; O1+B1: 5.96 / 3.13 / 19.67): no diversification gain over B1.
v279 fill-time dip sizing by pre-fill drop speed (walk-forward terciles): best dev rows ever (F2 dev4 6.25, worst 3.44, DD 18.7) but the most recent year FELL to 3.90 (M1 4.65) - a four-year-consistent dev effect that did not transfer; another warning against dev-mean chasing.
M1 ROBUSTNESS (research/diagnostics/m1_robustness): M1 beats O1 in all 13 paired rows on dev4 (+0.17-0.51), holds DD <= 20 in 8 rows vs O1 7 (latency 30: 18.4 vs 21.1), bootstrap P(>=5%/mo) 59% vs 55%, P(loss year) 0.9% vs 1.4%; bot outage (backstop only) DD 18.7. DEPLOYED 2026-09-29: paper pipeline C4 = v269 M1 is now the RECOMMENDED default on the web (O1 and C5 stay as paper comparisons).
v280 monthly-retrained flow member on C4: dev worse (5.69 / 2.71) but most recent year 4.75 (highest) - rejected by the protocol; 'fresher models help new regimes' stays a hypothesis for prospective evidence, never a selection signal.
DATA LEADERBOARD (research/diagnostics/data_leaderboard, dev only; pooled HGB, 7d target, IC gain over base): all groups mean IC 0.051, Bybit flow and spot flow gain in 3/4 years, positioning (OI / long-short) +0.12 in 2023 but negative 2021/2024, premium and OKX nothing; members A / Aq / B / Bq / C4 books IC 0.070 / 0.052 / 0.068 / 0.057 / 0.057, all negative in 2022. v281 microstructure member (all exchange data) blended 20 / 33%: DD 27 / 34 -> rejected.
v282 FULL-ACTION RL trader (user suggestion: direction, size / leverage up to 150%, reversal, stop / target moved every bar; PPO, 10 seeds): every seed far below the G2 rule (dev4 2.8-4.7 vs 6.13, losing years, DD 22-53). RL now tried from single decisions up to full control; the rule on the pipeline signal stays best.
v283 walk-forward NNLS stacking of members (+ exchange member C): corner weights chasing last year's best member, C weight ~0; dev4 5.42 DD 22.1 -> equal weights (C4) stay best.
v284 spot order flow spliced before the perp archive (+2.5y flow history): worse (5.32 / 5.51 vs 6.03) - spot-era flow differs from perp flow.
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
