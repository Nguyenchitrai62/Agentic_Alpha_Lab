# Continuous BTC research — active

LEADER 2026-10-05 (late): OpenCode studies - oc_regime: no slow regime variable gates the majors' dip edge consistently (signs flip in >= 2 of 5 years); oc_newinfo: Wikipedia attention and CME weekend gaps not tradable (two fragile monthly / 7-day hints for prospective logging only); r2_4p_robust5: R2-4P over 5 years (reset metric) keeps no losing year under every friction, 5y mean 4.82 base / 4.01 cost stress / 4.64 latency 15 / 3.82 latency 30 / 4.40 stop slip 50 % / 4.43 Bybit prices, max year DD 25-28 -> realistic BOT expectation ~3.5-4.4 %/month, DD up to ~28 (deployment plan updated; ~80 % capital for DD <= 20). v397 book shape (EMA-smoothed / long-only book): 3.62 / 4.46 vs 4.82 -> rejected (shorts hedge, smoothing delays). Book and dip layers both at their local optimum on the current information; the remaining clean evidence is prospective.

LEADER 2026-10-05 (5-fold tournament, OpenCode): research/tournament/ext (fills / bar-open / market features extended to 2026-09-23, overlap bit-identical, harness5 with 5 folds) re-scored the graduates unchanged: kelly V2 +1.09 / +1.88 / +0.69 / +1.05 / -1.45 (2025-26), context V2 +0.35 / +0.04 / +0.06 / +0.26 / -0.68 (total +0.02), tp V2 -0.24 / +0.09 / +0.82 / +0.07 / +0.09 -> the bar-open dip size models lose the newest regime (confirms v395); tp gain = 'TP 1.5 more often', which lost in the engine (v391 R2T). Dip size / TP model direction CLOSED. v396 risk-to-book rejected (folds keep R2); audits v395 / v396 PASS. User 2026-10-05: no Claude subagents - Claude decides, OpenCode workers execute. Running (OpenCode): oc_regime (slow regimes of the dip edge, leave-one-year-out gates), r2_4p_robust5 (deployed BOT frictions over 5 years, reset metric).

LEADER 2026-10-05 (METRIC CORRECTION + decomposition): the per-year metric of the multi-phase rows (v376..v395, v388.mix / year_stats) used a CONTINUOUS never-rebalanced 1/4 mix from 2021, so the lucky phase-0 sub-account (43x over 5 years) dominated later years; a user starting a year gets the four sub-accounts at 1/4 each -> research/diagnostics/r2_decompose5/reset_metric.py (reset at each anchor; v376_final_hidden already did this). Reset metric, dev 2021..2024: R2 1.96 / 3.77 / 4.01 / 10.63 (geo 5.04, max DD 25.1), R2K 5.63 / DD 25.2, R2C 5.43 / 25.2, R2KS6 5.16 / 22.2, R2CS6 4.81 / 21.8 (so v394's 'DD 19.4' pass was a metric artefact). Former hidden year (now research data): R2 3.95 / DD 18.8. Decomposition (reset): book-only -0.32 / 2.65 / 2.96 / 3.91 / 3.65 %/month at DD 9-15; dip-only 0.59 / 0.43 / 1.30 / 3.16 / 0.34 -> the book is the steady engine, the dip sleeve erratic. From v396: five walk-forward years, reset metric, prospective validation. Running v396 (risk from dips to the book).

LEADER 2026-10-05 (v395 GATE - FAIL): the frozen finalist R2CS6_4P (context dip sizes + 6-sigma dip close-stop; dev4 5.15 / DD 19.4 / no losing year) scored ONCE on the most recent year: 3.48 %/month, conservative DD 25.15 (R2-4P on the same year 3.90 / 18.76) -> 5y 4.81, gate (a) / (b) / DD fail. The tournament's bar-open size models improved every dev year but did not transfer - the same pattern as v279 / v280 / v189-v197: dev-mean and dev-tail improvements of the dip sleeve do not survive the unseen year. R2-4P stays the BOT; Kronos (pretraining overlap) not engine-tested. Lesson: a dip-sizing gain must now show up in the prospective paper log before any further dev-selected change.

LEADER 2026-10-05 (v393, v394, crash dial): v393 MANUAL M5 with the tournament size tables: M5K 3.82 / DD 27.8, M5C 3.98 / 27.4 vs M5 4.09 / 24.4 -> M5 kept (the BOT size models do not help the two-rung MANUAL). v394 size models + dip close-stop 6 sigma on R2-4P: R2CS6_4P (context sizes) dev4 5.147 %/month, worst year 2.13, DD 19.39, NO losing year = first honest-harness row with mean >= 5 and DD <= 20 (AGENTS robust criterion choice); R2KS6 5.15 / 2.94 / 22.2; registered BOT-fitness folds prefer R2K (no transfer); robust-criterion folds (post-hoc, disclosed): fold 2 R2C, fold 3 R2CS6, return higher in both. research/tournament/crashrisk: market-state 24h crash classifier AUC 0.66-0.71 but scaling R2-4P by it does not lower DD (the BOT earns most in flagged states; the 2024-01-03 crash came from a calm state) -> closed. Hidden-year context tables built (anchor 2025-09-24 model, t_exit < 2025-09-17). Next: v395 = R2CS6_4P most-recent-year gate scored once (after the v393 / v394 audit).

LEADER 2026-10-05 (IDEA TOURNAMENT + v391 / v392): research/tournament/ = fast common screen for dip-rung decision models on the 61.8k exact rung outcomes (fills_U, 35 coins, walk-forward t_exit < anchor - 7 d, bar-open features only; harness.py fixes folds, equal-exposure scoring and the graduation rule; parallel Claude subagents per idea). Graduates: kelly V2 mean-variance sizing +4.72 vs the deployed agent (all 4 years; the deployed agent is trained on FILL-time states but applied with BAR-OPEN states - a train / serve skew the bar-open refit removes), market-context HGB +0.70, TP agents +0.66 / +0.75 but mostly 'TP 1.5 more often'. ENGINE (honest 4-phase BOT harness): v391 R2K (kelly sizes) dev4 5.85 / worst year 3.03 / DD 25.2 vs R2-4P 5.24 / 1.96 / 23.1 - every dev year higher, fold 3 lost by 0.0014 fitness (all-trade win term) -> no transfer; R2C (context) 5.58 / 2.33 / 23.1; R2T (TP 1.5 control) 4.84 / 1.69 / 24.3. v392 kelly x0.9 / x0.8: 5.59 / 24.3, 5.25 / 25.5 -> scaling does not lower DD (kelly moves size into the wrong episodes, suspect volatility chasing). Running: kelly round 2 (with market features, mean-only, vol-normalised target), Kronos zero-shot features; audit v391 + v392 dispatched.

LEADER 2026-10-05 (v390 + BOT execution): v390 ex-ante (covariance) book risk sizing in R2-4P via the book_size hook (m = s_ex / s_hist at each new book entry; X1 de-risk only, X2 clipped 0.5-1.5): dev4 4.82 / 4.87 vs 5.24, DD 23.2 / 24.2 vs 23.1 -> rejected (the book's one-way concentration DD is not fixed by entry sizing; audit dispatched). BOT EXECUTION: bot/ = order mirror of the merged R2-4P plan for Bybit USDT perps (hedge mode, per-piece reduce-only exits, dip budget shallow-first, close5 bot stops, time exits, never chases unfilled limits; docs/BOT_EXECUTION.md, tests/test_bot_mirror.py); modes dry / paper / testnet, live locked behind BOT_ALLOW_LIVE set by the owner. PAPER BOT running since 2026-10-05 ~04:50 UTC (5000 USDT, live Bybit 1m fills, artifacts/bot/paper/exchange.json equity_curve) = prospective evidence for the whole bot stack; it is a session process (restart after a reboot: python -m bot.run --mode paper --equity 5000; auto-start from the backend was refused by the safety classifier and reverted).

LEADER 2026-10-05 (two dev-only diagnostics, deployment realism): (1) research/diagnostics/rolling_anchor_dips: a clock-free dip anchor (price 240 min ago or the 4h running high, k sigma below) LOSES in 2021-2022 (k3 sums -0.39 / -0.28 and -1.24 / -1.08 vs anchored 4-phase +0.44 / +0.46, DD 5x higher) -> the 4h-open anchor with bids from minute 16 and the bar-end exit is a real part of the dip edge; direction closed. (2) research/diagnostics/manual_human: MANUAL with a real human (15-minute reaction, night bar skipped) on the honest 4-phase harness, agents on, dev only: M2 3.00 / DD 22.0 (worst phase 25.2), M3 3.52 / 23.8 (31.5), M4 3.60 / 23.7 (32.5), M5 3.50 / 24.2 (33.9) vs minute-5 every-bar 3.60 / 4.18 / 4.26 / 4.09 -> the human costs ~0.6 %/month; no MANUAL pipeline meets DD < 20 honestly; run MANUAL on ~80 % of capital for DD < 20 (~2.8 %/month). v389 audit PASS recorded (agent-level blindness caveat in the manifest). Blind audit of both diagnostics dispatched (research/diagnostics/diag_20261005_audit). Backend gap 2026-10-04 16:30 - 2026-10-05 02:10 UTC = machine off, catch-up ran at startup.

LEADER 2026-10-04 SESSION CLOSE (user asked to stop): ledger / registry up to date (next v390; active slots v376 C deployed, v388 B, v389 A; audits v373-v388 PASS, v389 audit dispatched). Paper scorecard snapshot 2026-10-04 10:09 UTC (too short to judge): G2 +1.07 % / CS +1.09 % after 4.3 days (p65), R2 +0.56 % after 1.3 days (p76), M2-M5 just started; R2-4P starts after the backend restart. No pipeline beats R2-4P (BOT) or M5 (MANUAL) on the honest evaluation. Resume with /alpha-lab-leader: paper evidence first, then the liquidation dataset.

LEADER 2026-10-04 (v388, v389, close of the round): v388 R2 dip close-stop 5 / 6 sigma = a risk dial (5.16 / DD 21.9, 4.94 / DD 20.0 vs 5.24 / 23.1), R2-4P kept. v389 PHASE-SPECIFIC BOOKS (research/diagnostics/phase_books: the CB members rebuilt walk-forward on each shifted 4h grid, s = 0 native reproduces the cached members bit-exactly, leakage checks pass): R2pb_4P 5.06 / W 1.52 / DD 22.9 vs forward-filled standard books 5.24 / 1.96 / 23.1 -> rejected. Quick dev checks closed without registration: per-coin dip weighting (rank persistence ~0), weekend dips (sign flips by year), funding-settlement trades (net negative pre-anchor). Audits v373-v388 PASS. ROUND RESULT: deployed BOT R2-4P (honest dev ~4.6 %/mo across 8 clocks, most recent year 3.9, DD 19-25), MANUAL M5 (~4 %/mo, single-clock DD ~24); the current information set is exhausted; next evidence = paper log + the live liquidation dataset.

LEADER 2026-10-04 (v386, v387): v386 crash breaker on R2-4P (sleeve_breaker 0.010 / 0.020): 4.52 / 4.86 vs 5.24, DD 22.6 / 22.4 vs 23.1 -> rejected (the breaker removes the recoveries that pay for crash fills; the drawdown is the price of the dip edge). v387 eight half-hour-shifted clocks: R2_8P 4.58 / DD 25.0 vs R2_4P 5.24 / 23.1 -> rejected; it shows the 4-clock mix still carries 1/4 of the lucky standard clock: the honest BOT dev expectation is ~4.6 %/month (most recent year 3.9). Audits v381-v386 PASS.

LEADER 2026-10-04 (NEW DATA round, v382-v385): free-source scan (research/diagnostics/newdata_scout/SOURCES.md) + three studies vs the dip-fill outcomes (dev only): Bitfinex margin long/short (2021+) and Binance 5m metrics show contrarian ICs that reverse in the 2024 bull year; Binance bookDepth (2023+, +-1 % depth vs 7-day median) has the same-sign IC every year and coin. v382 book family CB / O1 / T3 equivalent on the honest harness; v383 / v384 Bitfinex features in the R2 agents (BOT / MANUAL) rejected; v385 ONE-SHOT most-recent-year test of depth-based dip sizing (thresholds from pre-2025-09-16 fills): 3.37 %/mo DD 24.3 vs R2-4P 3.90 / 18.8 -> rejected: predictive ICs on fixed-rule outcomes did not translate into P&L. Started collecting data with no free history: backend/liquidations.py (Bybit all liquidations, Binance forceOrder, top of book) from 2026-10-04. Deployed: BOT R2-4P (v376), MANUAL M5 (+ M4 / M3 / M2 / M1); honest expectation BOT ~3.9-5.2, MANUAL ~4 %/month.

LEADER 2026-10-04 (v377-v381, honest harness): every lever re-tested on the 4-phase evaluation with agents on: v377 MANUAL dip budget 0.20 / book_mult 1.0 (rejected, M5 4.09 / DD 24.4 kept); v378 bear-regime dip filter (BTC < 200-day mean -> dips x0.5) on M5: every dev4 metric better (4.35 / DD 21.3 / worst year 1.25) but fold 3 lost by 0.011 -> rejected; v379 the same filter on R2-4P hurts (4.84 vs 5.24) -> not general; v380 R2-4P governor 0.16/0.08 and 0.25/0.15: no transfer; v381 phase-augmented R2 agents (trained on the fills of all four phases): 5.06 vs 5.24, rejected. R2-4P (v376) is the BOT paper pipeline (hourly phase plans since 2026-10-04 04-07 UTC). Cached 2-clock mixes: M5 2 clocks 4.22 / DD 19.6 vs 1 clock 4.08 / 24.2 -> MANUAL stays on the 4h cadence. Audits v373-v380 PASS. Honest ceiling of the current information: BOT ~3.9-5.2 %/month at DD ~19-23, MANUAL ~4.1 at single-clock DD ~24.

LEADER 2026-10-04 (v375, v376, agents per phase): v375 honest re-ranking on the 4-phase mean (agents off): M4 3.76 > M3 3.57 > M5 3.52 > M2 3.39 (no fold transfer, M5 stays recommended), BOT R2 4.21 > G2 4.01 > CS 3.94; single-phase DD 20-30. research/diagnostics/phase_agents rebuilt the R2 agent tables per phase (same per-anchor models; s = 0 identical): agents add +0.58 (M5) / +0.47 (R2) on the phase mean (R2: +0.84 on the standard grid, +0.35 off it) -> honest M5 4.09, R2 4.68 %/mo. v376 MULTI-PHASE BOT (four clock-shifted sub-books, 1/4 capital, never rebalanced): R2_4P dev4 5.24, worst year 1.96, conservative DD 23.1, no losing year (R2 single phase mean 4.65 / 0.64 / 32.2) - chosen in both folds -> TRANSFER; most recent year ONCE: R2_4P 3.90 %/mo, DD 18.8 (single phases 5.66 standard / 2.32 / 3.59 / 3.74: the deployed R2's 5.66 was phase luck). M5_4P x1.2 dev 4.95 / DD 19.8. Process: v376's first run had a normalisation bug (disclosed, re-run). Next: an R2-4P paper pipeline (needs hourly plan runs).

LEADER 2026-10-04 (whole-pipeline phase luck, v374): research/diagnostics/phase_offset_full replays the DEPLOYED pipelines (book + dips, agents off) on 4h grids shifted 0..3 h (s = 0 with agents reproduces history_tm within 0.003): dev4 standard / phase-mean / 4-phase mix (daily DD): M5 5.54 / 3.51 / 3.57 (18.5), M4 5.88 / 3.76 / 3.82 (15.8), M2 4.79 / 3.39 / 3.42 (14.2), R2 6.24 / 4.21 / 4.26 (18.8); the standard grid is best in every dev comparison but 3rd-4th on 2020-21 -> ~30-37 % of the standard-grid dev return is phase/selection luck (stale-book control: no effect). Honest expectation before agents ~3.4-4.3 %/month; the mixes have no losing dev year. v374 (dip-rule grid on the 4-phase mean, dip-only): both folds keep the deployed rule (3 / 4 sigma, TP 1, stop 8); on the untouched 2020-10..2021-09 period it earns 5.6-10.1 %/month dip-only on every phase -> the dip rule generalises, its standard-grid dev level does not. PROTOCOL from now on: judge every variant on the 4-phase mean. Running: v375 honest re-ranking of M2-M5 / R2 G2 CS on the phase mean.

LEADER 2026-10-04 (system audit + v373 + phase luck): SYSTEM AUDIT (research/diagnostics/system_audit/SUMMARY.md): blind OpenCode replay of 34k M5 / R2 simulated events vs raw 1m = 0 engine violations (one convention: dip exits checked from the minute after the fill, 1 / 5 fills affected, no PnL effect); leakage audit PASS (book vs future returns max corr 0.061, truncation test 20/20, fit windows end before anchor - embargo); live vs research parity: feature code identical, books corr 0.98-0.99; ONE DATA BUG fixed: the live whale-flow stores double-counted 2026-09 (repaired, verified 1.0x kline volume; the backend data check now flags flow/volume outside [0.7, 1.3]). Execution stress (default-neutral engine_user hooks): actual funding helps; stop slip 50% cuts M5 book win 0.65 -> 0.59; user decisions 2026-10-04: limit fills on trade-through stay (no extra bps), bots execute on time, Bybit data to be fetched and compared (OpenCode, running). v373 M2 + M4/M5 management (M2 / M2S / M2ST, goal-1 fitness): no transfer, final M2ST 5y 4.88 / last 4.27 / DD 17.1 -> M2 kept. PHASE LUCK (dev-only diagnostic research/diagnostics/phase_offset_dips): the dip-only sleeve on 4h grids shifted 0/1/2/3 h gives dev totals +452 / +34 / +126 / +104 %, and on PRE-research data 2020-06..2021-09 the ranking flips (+166 / +139 / +373 / +444 %) -> the standard grid's dev advantage is timing luck; every dip rule tuned on the standard grid carries it; phase correlations 0.29-0.62, 4-phase equal mix DD ~17 %. Running: whole-pipeline phase robustness of M5 / M4 / M2 / R2 (research/diagnostics/phase_offset_full). Next: select dip rules on the 4-phase mean; a multi-phase BOT (4 clock-shifted sub-books).

LEADER 2026-10-03 afternoon (v345-v347): M3 is a local optimum on every axis tried - v345 BOT book share (R2 book x0.75 / x0.5: DD 16.5 / 16.0 but dev4 6.43 / 5.73, folds keep R2), v346 MANUAL dip stop distance (6 / 10 sigma: folds unstable, ST6 last year 3.95), v347 walk-forward GA over the nine book-member weights under the fixed M3 structure (no leverage genes; kpack inputs make one simulation 4 s locally): evolved weights lose to the deployed CB mix on the unseen year in both folds, the dev4 GA final (path-heavy) has the higher dev F but last year 3.76 vs 4.70. M3 night check (research/diagnostics/m3_night): skipping the 03:00 VN bar keeps 5y 5.15 / last 4.69; skipping 23:00 too drops 5y to 4.41. Remaining MANUAL gap: most recent year 4.7 < 5 (bootstrap P(year >= 5) ~0.6); next gains need new information or the prospective log. v348 exhaustive 1296-rule grid of the dip-agent decision rules (flat choice): no transfer (fold 2 loses). v349 hour-of-day dip multiplier from pooled pre-anchor fills (M3 dev fills were positive at 08 / 12 UTC every dev year, but the pooled 35-coin hour means flip sign across years): DD 22, rejected. v350 dip agents refitted on M3-rule outcomes (touch 8 sigma; all depths MU / M3 depths M34): dev4 5.74 / 5.82 < 6.23, folds keep M3. v351 NEW DATA - Binance delivery-futures term structure (OpenCode fetcher scripts/fetch_quarterly_basis.py, data/raw/qbasis_20261003; BTC / ETH front basis, slope, 24h change as market-wide features in member A): dev4 6.55, worst year 3.78, book win 0.526 but DD 22.85 (same pattern as the flow extensions: more information, more one-way exposure) -> no transfer, M3 kept. v352 basis book + one-way control (book x0.6 / half-demeaned members): DD 20.6 / 20.5, no transfer; basis closed. Rip-fade SELL limits (dev event study research/diagnostics/rip_fade): no cell positive in every dev year -> closed. v353 BOT sub-account blend (exhaustive 15624 capital-weight blends of R2 / G2 / Q2 / B1 / T1 / M3, monthly rebalance, flat walk-forward choice): every fold and the final pick R2 alone -> the pipelines share one return source; R2 kept. v354 M3 governor (looser 0.25/0.15 ~ identical; tighter 0.16/0.08 DD 21.8): no transfer, M3 kept. v355 BTC-hedged dip rungs on R2 (engine_user sleeve_hedge hook, default-neutral; dev study: half of the dip edge is idiosyncratic): hedge 0.5 dev4 5.84 / DD 15.7, hedge 1.0 4.71 / 16.8 vs R2 7.08 / 18.4 -> folds keep R2. v356 third MANUAL bracket rung at 5 sigma: DD 23.3 / 21.3 (deep touch-stopped rungs concentrate crash risk) -> M3 kept. v357 richer bar-open dip-agent state (previous-bar / BTC / 24h moves, previous-bar flush; pooled refit): dev4 6.11 / 6.16 < 6.23 -> M3 kept. v358 M3 vol target 0.27 / 0.29 (cap 2 binds: dev4 6.28 / 6.33, DD up) -> folds keep M3. v359 M3 cap 2.5 / 3.0: DD 22.1 / 24.3 without return gain -> M3 kept; M3 risk level closed. Dip refills after TP (dev study research/diagnostics/dip_refill): refills lose in 3/4 dev years -> closed. v360 M3 book shorts x0.5 / long-only: win rises (0.66 / 0.68) but worst dev year falls (2.49 / 2.30 vs 3.44) - shorts hedge the bear years -> M3 kept. v361 M3 book entry depth 0.5 / 1.0 sigma: dev4 6.06 / 6.05 < 6.23 -> 0.75 kept. v362 M3 book SL / TP: the dev4 choice S5T10 (SL 5 / TP 10 sigma_d) has F 1.3172 vs 1.3139, fold transfer NOT confirmed (fold 3 loses by 0.004); its most recent year (once) is 5.04 %/month, 5y 6.12, gate DD 16.96, no losing year - numerically the first MANUAL design over the 5 %/month floor on both the 5-year and the most-recent-year rows; better than M3 on every robustness row (research/diagnostics/m4_robustness). Deployed as an extra paper pipeline M4 (v362_M4, from 2026-10-04 00:00 UTC); the prospective log decides. v363 BOT R2 book SL/TP 5/10, 6/12: dev4 7.18 / 7.12, DD 17.0 / 16.9 but worst year 3.69 < 3.96 -> BOT fitness keeps R2. v364 M4 neighbourhood: SL 4 / TP 10 = 6.43 dev4, 5y 6.15, last 5.07, DD 16.5 (same as M4 within noise); SL 5 / TP 8 = 6.18 / DD 18.1 -> the gain comes from TP 10; M4 sits on a plateau (supports M4, not a sharp peak). v365 partial TP on M4 (half at 3 sigma / a third at 2 sigma): book win stays ~0.50 (a book trade is scored on its position net), return falls -> M4 kept; the MANUAL book win rate (~0.52 over 5y) is the one goal-1 metric still below 55 % (all trades 0.64; book 0.556 in the most recent year). v366 management genes on M4: loss_act tighten lifts the book win to 0.648 (lock 3: 0.533) but the all-trade fitness keeps M4. v367 (POST-HOC, disclosed: the goal-1 / v310 book-win fitness, decided after seeing v366's dev rows): fold 2 keeps M4, fold 3 picks LT and beats M4 on unseen 2024 (2.12 vs 0.93); dev4 final LT = paper pipeline M5: 5y 5.855, most recent year 5.22, gate DD 18.62, no losing year, book win 0.657 / 0.686 (5y / last year) -> EVERY goal-1 metric met on the walk-forward replay for the first time; robust to latency 30 and the night skip; cost stress last year 4.64. Paper from 2026-10-04 00:00 UTC; the prospective log decides. v368 the tighten rule on BOT R2: all-trade win 0.70 (book 0.64) but dev4 6.64 / 6.85 and worst year 3.36 / 3.25 < R2 -> BOT fitness keeps R2 (BOT goal 2 still open: 8 %/month at DD < 15 is beyond every tested variant). v369 R2 / M5 / M4 sub-account blends: R2 alone in every fold -> R2 kept. v370 M5 neighbourhood (tighten distance 1.0 / 2.0 vs 1.5): tighten 1.0 = dev4 6.25, 5y 6.01, last 5.06, DD 17.3, book win 0.63; 2.0 ~ M5 -> the tighten rule is a plateau (every neighbour meets goal 1 on the replay); folds split -> M5 kept. v371 exhaustive 648-row BOT trader grid (book_mult x book SL/TP x tighten rule x dip budget x dip stop) on R2: every fold choice loses to R2 on the unseen year; dev4 final (TP 10, budget 0.30) 5y 6.91 / last 5.67 / DD 17.2 in-sample only -> R2 kept; BOT goal 2 (8 %/month at DD < 15) is out of reach of every tested design. v372 CNN dip size agent on bar-open 1m sequences of the coin and BTC (Kaggle GPU, pooled 72k fills, walk-forward): R2c 6.94 < 7.08, M5c 5.77 < 6.02, folds keep both references -> 6th deep-learning attempt without gain.

LEADER 2026-10-03 midday (v338-v341, MANUAL-feasible dip): the user's MANUAL rule set allows ONE resting limit per coin with exchange-native TP / SL attached; a single deep dip limit per coin (3.0 sigma_4h below the 4h open, fills from minute 16, native touch stop at 8 sigma, R2 agents' size / TP read at the bar open) is human-placeable, unlike the 20-bid ladder. v338 MD30 = M2 + that dip: transfers on both dev folds, dev4 3.905 (M2 3.011), 5y 3.95, most recent year 4.13, gate DD 18.83, all-trade win 0.62 (book 0.53, dip 0.72); 30-min reaction row 3.86 / 4.12. v339 intensity (2.5 sigma / dip x2): folds pick MD25, which loses to MD30 on the unseen year -> no transfer (MD30x2 5y 4.69 / last 4.47 / DD 19.8 in-sample only). v340 risk reallocation (book x0.75, dip x2.5 = RA2): transfers both folds, dev4 4.551, worst dev year 1.733, DD 16.0; 5y 4.386, last year 3.725 (dip win fell to 0.63 in the most recent year), gate DD 16.0. Still below the 5 %/month MANUAL floor. Needs hedge mode (dip buy must not net against a book short). v341 (RA2 vol target 0.28 / 0.31): folds pick 0.31, which breaches DD 20 on the unseen 2023 -> no transfer (leverage again). v342 L2 = TWO bracket dip limits per coin (3.0 + 4.0 sigma): transfers both folds, dev4 5.779, worst 2.251, DD 19.71; 5y 5.531, last 4.544. Deployed on the live CB books as paper pipeline M3 (2026-10-03 08:00 UTC; replay dev4 6.233, 5y 5.925, last 4.704, DD 17.73, all-trade win 0.64, book win last year 0.556; research/diagnostics/l2_robustness: cost stress DD 20.3, 30-min latency 5.2 / 4.5 / 19.4, 60-min breaks). v343 depth pairs (3+5, 2.5+4) and v344 book share (0.5 / 1.0) both keep L2 -> M3 sits at a local optimum. MANUAL floor: 5y and DD and win met; the most recent year 4.7 < 5.

LEADER 2026-10-03 later (v322-v333): MANUAL frontier confirmed - theta x target (v322), break-even grid (v331), pooled trend-regime overlay (v324), pooled GRU on Kaggle GPU (v326, 5th DL failure), alt spot-history prefix (v329), pooled short-horizon / bigger-tree members (v332) and consistent-gene selection from 9.6k GA genomes (v333) all fail the walk-forward folds; the MANUAL book trades win rate against return (win 0.64-0.68 at ~3%/month, or ~3.2-3.8%/month at win 0.52-0.58); best general MANUAL stays M2 (5y 3.16, last year 3.76, DD 20.6). BOT: R2 stays (v325 77-coin agents, v327 evolved sub-account ensemble -> R2 alone, v328 fill-time agents, v330 closer native backstop: no gain). R2 robustness (research/diagnostics/r2_robustness): beats G2 on return in all 17 stress rows, bootstrap P(>=5%/mo) 0.71 vs 0.65, but DD > 20 if the bot is down (22.2) -> R2 needs a reliable bot, G2 is the fallback. R2 paper plan verified live at the first bar (2026-10-03 00:00 UTC).

LEADER 2026-10-03 (v306-v321; evolutionary computation, pooled experience, two products): WALK-FORWARD GAs over 20-28 genes (v306 BOT, v307-v310 / v313 MANUAL) overfit - every dev4 final picks leverage 4-6x and fails the most recent year (0.1-3.1 %/month, DD 22-30) while dev folds are mixed; book leverage is not general (v314). General MANUAL gains: pullback entry limits (v315), the POOLED-EXPERIENCE TV member (v316 / v317, audits PASS: 5 majors + 72 survivorship-free U2020 alts for training only, IC 2023 0.17 vs 0.08) -> MANUAL M2 (2A + 2PT + D, pullback, cap 2): 5y 3.16, most recent year 3.76, DD 20.6, win 58.5% last year; management genes (v309 / v318) lift the book win rate to 63-68% at lower return. MANUAL floor (5%/month) NOT met; MANUAL frontier ~3-3.7 %/month. BOT: in v306 the best existing pipeline on the training years was R2 in every fold (G2 + 5-sigma rung, agents fitted on all rung depths) and beat the evolved winners; v321 scores it once on the most recent year: 5y 6.79, last year 5.66 (G2 5.35), DD 18.39, all-trade win 0.66 -> R2 deployed as paper pipeline v321 (frozen agents scripts/v321_r2_dip_agents.py, cutoff 2026-09-11; paper from 2026-10-03 00:00 UTC; admin-only on the web until unlocked). Kaggle CPU kernels (kpack) ran the GA searches; OpenCode blind audits PASS for v304, v305, v307, v314-v318.

LEADER 2026-10-02 (v306-v309, IN PROGRESS; user: two products, evolutionary recombination, full authority): the MANUAL product (book orders only, a human can follow it) and the BOT product (book + dip ladder) are scored separately (AGENTS.md). MANUAL today = G2 books alone: dev4 2.50, 2021 losing, win ~50%; the flat risk frontier was the vol-scale CAP 2 (cap 4, target 0.37: dev4 4.29, DD 21.1, no losing year; research/diagnostics/book_vs_bot). Walk-forward genetic algorithms over audited components (fitness on years before the test year only, judged against the best existing seed on the unseen year; most recent year scored once for the finalist): v306 BOT (agent tables refitted on three rung sets, artifacts/research/engine_real/v306_gene_tables.parquet, one engine run ~5 s; fold 1 with one training year overfit: 8.7 -> 3.7 %/month, DD 31), v307 MANUAL (20 genes; fold 2 transfers: unseen 2023 5.3-5.8 %/month at DD ~20.6 vs best seed 3.24, win 46-52%), v308 MANUAL + leverage / governor (engine hook gov, default-neutral) / short multiplier / break-even level, v309 MANUAL + trader management genes for the win rate. Kaggle CPU kernels run the searches on the same engine via kpack (research/parallel/rounds/parallel-20260906-r2/kpack).

LEADER 2026-10-01 (v302-v305, OpenCode as research assistant): flush-breadth features trade DD for the weak year (real, seed-independent); second dip stream closed; DD anatomy: book concentration + dip flushes, no cheap mechanical lever; wider dip ladder (2.0-sigma rung) is the biggest unexploited return source (dev4 7.8, DD 20.3) whose DD does not shrink with budget / book target - next: dissect the 2021 episode. G2 remains the deployed recommended pipeline (5y 6.27, last 5.35, DD 17.1, bar-open form). Backend now backfills missed cycles; only the five best pipelines run.

LEADER 2026-09-30 (v296-v301, new user goal DD ~15 / 6-7%/month / win ~60%, stepwise): J1 (size + take-profit dip agents) beats S1; moving risk from the book to the learned sleeve reaches DD 15 only at ~5%/month; book partial take-profits lower the win rate; the 77-coin experience raises the mean but not the weak year; a larger model overfits. The stepwise return-first rule (from v301) selects G2 = J1 agents + dip budget 0.26: 5y 6.318, most recent year 5.486, DD 17.52 (bar-open form 6.272 / 5.349 / 17.09), better than CS on every metric -> deployment after the v301 audit. All-trade win rate ~66% (book ~51%, dip rungs ~70%).

LEADER 2026-09-30 (v292-v295 + CS DEPLOYED, user: focus on the RL agent): the RL failures were a DATA problem. With exact counterfactual dip-rung outcomes from a standalone replica and a survivorship-free 35-coin experience pool (U2020 alts, training only), the learned take-profit agent improves with data (2.50 -> 2.85 -> 2.93 worst dev year) and the learned SIZE agent (v295 S1) beats the rule pipeline CB on every metric: 5y 6.084 vs 5.725, most recent year 5.326 vs 5.167, DD 17.50 vs 18.39, worst dev year 3.384 vs 3.005; audit PASS; more robust than CB in the stress report; keeps its edge when sized late or once at placement. Deployed as paper pipeline CS (recommended), sized at the bar open (5y 5.987, last 5.266, DD 17.20).

LEADER 2026-09-30 (v290-v291, user: full authority, find more data): v290 screened six information sets as 20% satellites on CB (Korean premium, DVOL, US macro, Fear & Greed, CFTC COT, and a NEW per-coin Coinbase premium from freshly fetched SOL-USD / XRP-USD candles) - none passes the dev-only acceptance (worst dev year and DD vs CB), so nothing was scored on the most recent year; v291 consensus sizing is neutral (the six model sets agree 94.5% of the time). Binance keeps no liquidation archive and bookDepth starts 2023-01. CB remains the recommended pipeline.

LEADER 2026-09-30 (v288-v289 + P1 decision): v287 audit PASS but P1 is NOT at least as robust as CB (p1_robustness: DD<=20 in 9 vs 11 stress rows, cost stress 23.2 vs 20.8, dev4 lower in all 15 rows) and v288 (path label in the options+TV member) did not reproduce the gain -> P1 not deployed, CB stays recommended. Breakthrough attempts: 12h dip engine (v289: touch stops turn the no-stop edge negative in 2022/2023; wide stops restore it but the stream is ~+8%/yr at DD ~8% per 1% risk and dilutes CB) and CB drawdown anatomy (no single cause) -> no step change available from the current information; options that change the ceiling are user decisions (DD limit, new live-only data).

LEADER 2026-09-30 (v286-v287, model diversity): v286 upgraded the Coinbase member D with TradingView (E1) and order-level flow (E2): dev win rate up (51.8%) but worst dev year 2.91 / 2.99 < CB 3.005 and dev DD 18.65 -> rejected; D helps because it is DIFFERENT, not because it is strong. Selection protocol fix from v286 on: the DD filter uses the first four years only (max yearly 1m DD 2021-2024; the old full-path DD included the most recent year; identical in every recent version). v287 trains the O1 member on a PATH label (first touch of +-vol42*sqrt(h) from the next open, stop-first, else clipped return; same window / embargo): book-weight corr with A 0.87. P1 = 0.8 CB + 0.2 path member: worst dev year 3.054 (> CB 3.005), dev DD 18.05, dev4 5.683 (< 5.864) -> preferred by the robust criterion; final 5y 5.586, most recent year 5.200, DD 18.05, hidden win 56.2% (gate pass). P2 (path label replaces A) 2.70 / DD 19.5. Audit + P1-vs-CB robustness pending (v287_audit); live PA member frozen (scripts/v287_path_advisor.py, cutoff 2026-09-11) and logged as v287_PA in the fast shadow since 2026-09-30 00:00 bar.

LEADER 2026-09-30 (v281-v285, user: use the exchange data to the maximum; full-action RL): data leaderboard (dev) - no exchange data group is stable across years; v281 all-exchange member (DD 27), v283 NNLS stacking (C gets weight ~0), v284 spot-spliced flow history (worse) rejected; v282 full-action PPO trader (direction, size / leverage, reversal, moving SL / TP; 10 seeds) far below the rule. v285: the Coinbase-premium member D (Coinbase spot exchange data; 'good alone' in the v154 era, dropped in v206 at DD 20+) added with 20% to the C4 books raises the weakest dev year (3.005 vs 2.951) at DD 18.39 and passes the whole gate on its one-time final score (5y 5.725, most recent year 5.167, no losing year). Blind audit and robustness report running before any deployment.

LEADER 2026-09-29 (v268-v279 + C4): the close-stop family was explored to the end - book close stops (v268) and wider / larger / hourly variants (v274-v276) break DD; the RL optimal-stopping agent (v271 / v272) and fill-time speed sizing (v279: best dev rows, unseen year 3.90) do not transfer. The 4-sigma close stop M1 (v269: dev4 6.03, worst dev year 2.95, DD 18.27, 5y 5.75, most recent year 4.65) is at least as robust as O1 in the stress report (8/13 rows DD <= 20 vs 7; bootstrap P(loss year) 0.9%) and is now the recommended paper pipeline C4. The unseen-year target (>= 5%/month) is still not met; next steps need the user (liquidation data key or a small live test).

LEADER 2026-09-29 (v267 + deployment): audits v262-v266 PASS. The B1 robustness report shows higher returns in every stress row but a thinner DD margin (cost stress 22.8 vs 20.75); a stress-robust selection (v267) found no design - not even the deployed O1 - that keeps DD <= 20 under the AGENTS cost-stress row, so O1 stays the recommended pipeline. v266 B1 (dip stops on 5m closes + 8-sigma native backstop; under the gate cost model dev4 6.13, worst dev year 3.257, DD 19.70, 5y 5.795, most recent year 4.464) runs from today as the fifth PAPER pipeline C5 for prospective evidence.

LEADER 2026-09-29 (v263-v266): meta-labeling neutral (v263); a dip-ladder circuit breaker neutral (v264: the 2024-08-05 losses came from rungs already filled, all stopped at one liquidation-wick low). Candle-CLOSE stops for the dip rungs fix that: v265 S2 (5m close) dev4 6.178 / DD 19.29 / stops 196 -> 100; the executable form v266 B1 (5m-close stop watched by the bot + 8-sigma native backstop) dev4 6.13, worst dev year 3.257, DD 19.70, 5y 5.795, most recent year 4.464 - the first rule change in many rounds that improves every selection metric AND the unseen year. Blind audit (v263-v266) and a B1 robustness report (cost stress, latency, bot outage) are running before any deployment.

LEADER 2026-09-29 (v261-v262): direct-reinforcement foundation member (differentiable net Sharpe, 5 seeds) has IC ~0-0.07 and dilutes O1 (dev4 5.50 / 5.58); Binance SPOT order-level whale flow (full 2017+ archive, kept as a derived store) raises DD above 20 in both forms (dev4 5.32 / 5.46). O1 + sleeve budget 0.18 remains the deployed pipeline; v260 / v261 audits PASS.

LEADER 2026-09-29 (v260): PPO risk manager trained on block-bootstrapped paths and judged on the median of five seeds - median dev4 4.47, most recent year median 3.13, DD 17.45: the robust learned policy only de-risks, so DD and return fall together; not adopted. v258/v259 blind audit PASS (bit-exact PPO retrain, no leakage). BTC hedge of alt dip fills (dev diagnostic) removes 70-85% of the edge.

LEADER 2026-09-29 (v258-v259, sequential RL): v258 disciplined PPO in a faithful G2 pyramiding simulator (monthly book PnL corr 0.985 with the engine) - cutting only losers realises reversible drawdowns (win 43-49%, DD 20.6-26.7). v259 PPO daily risk manager: the registered seed passed the whole gate (5y 5.114, most recent year 5.309, DD 17.45), but four other seeds of the same method give the most recent year 2.3-3.6 and dev4 4.5-5.0 (median 3.48 < O1 4.08): seed luck, rejected and not deployed. From now on stochastic learners must report >= 5 seeds.

LEADER 2026-09-29 (v255-v257 + OpenCode studies): whale-burst reversal event study (dev only) 0/108 stable rows, worse than random entries -> closed; v255 dip ladder from minute 5/10 neutral; v256 RL entry-execution bandit neutral; v257 sequential PPO trader: pure PPO raises the trade win rate to 56.5% but cuts trends (dev4 3.9, DD 21.1), PPO with a rule prior reproduces the rule. O1 B18 robustness: no losing year in any stress row, DD fragile (cost stress 20.75, 30-min latency 21.1); bootstrap P(loss year) 1.4%, P(DD>20) 6.8%.

LEADER 2026-09-29 (v252-v254, complete-data focus; user: OKX data is incomplete -> optional, v253 OKX flow registered but deferred): the Binance aggTrades order-level archive was re-processed once into a kept 1m store (data/raw/aggflow_20260929_orders_1m, 4h totals identical to the audited O1 table). v252 intrabar whale flow (last-hour whale pressure, absorption of down-minutes, 30k-100k tier, one-minute bursts) in the O1 A members: dev4 5.63-5.66 below O1 B18 5.777 -> rejected. v254 adaptive dip-ladder spacing by the current 1m realized volatility: dev4 1.9-3.7, DD 24-40 (bids move close to the price and buy ordinary pullbacks) -> rejected; the slow 60-day sigma ladder stays. OpenCode runs a dev-only whale-burst reversal event study (research/diagnostics/whale_burst) as a candidate for an independent return stream.

LEADER 2026-09-29 (v248-v251, RL / trader actions on the dip sleeve of O1 budget 0.18 = current best, dev4 5.777, 5y 5.436, most recent year 4.082): v248 learned dip-EXIT agent (take-profit multiple chosen at the fill, exact counterfactuals, audit PASS) dev4 6.05 but DD 20.7 and most recent year 3.85; v249 learned ladder DEPTH window (six-rung ladder, shallow / standard / deep per coin and bar): the free agent breaks DD (22.6), the strict one almost never deviates (= reference); v250 per-rung size weights: heavier NEAR bids (P3) dev4 5.914 / worst 2.968 / DD 19.0 / 5y 5.525 but the most recent year 3.98 -> no transfer; v251 strategy-level vol targeting (new engine hook strat_vt, causal expanding median): all variants much worse (the dev diagnostic was confounded by the 20% DD governor). Dev-only diagnostics (research/diagnostics/o1_dd_episodes, slide_ladder): the binding 2023 DD is one bar (2024-08-05, sleeve -12.3%); fills on the 5th coin of a market-wide flush have the most stops (6.7%) but a positive mean; bids against the 24h high (slow slides) do not revert intrabar (incremental fills ~0 / negative). Pattern confirmed again: sleeve / management layers lift the dev mean but not the unseen year; only new foundation information transferred so far. O1 + budget 0.18 stays deployed.

LEADER 2026-09-28 (v231-v236, quality data): TradingView indicators (v231/v233) and whale-vs-retail taker flow from Binance aggTrades (v236) are the first foundation gains in a long time. Best: v236 W2 (T3 + whale flow in the A members) dev4 5.774, worst dev year 2.491, DD 19.51, 5y 5.442, most recent year 4.123 (scored once) - the gate still fails on the most recent year. Exact 1m premium / predicted funding and Fear & Greed dilute; daily/weekly indicators and RL / bandit trade management (v232, v235) do not transfer. T3 runs as a second paper pipeline next to D2 (prospective log now inside the backend cycle).

LEADER 2026-09-28 (v227-v230): causal coin bandit for dip bids (v227, DD > 20), deeper limit offsets (v228, noise), an hourly dip ladder in trade mode (v229, DD 42%) and a new Korean (Upbit kimchi) premium member (v230, alone dev4 3.69, dilutes) are all rejected; v227-v229 blind audits PASS bit-exact. Dev-only drawdown decomposition: the dip sleeve earns most of the return and causes the worst drawdown (2023-04..06), but its losses are not serially dependent. D2 remains the deployed pipeline (dev4 5.26, worst year 2.18, DD 19.1, trade win 51%; most recent year 3.82 scored once).

LEADER 2026-09-28 (v221-v226, foundation for the trade mode): exit hysteresis (v221) and sub-account bot ensembles (v222) ~equal
to D2; the foundation components were rebuilt from the audited pipelines (sums exact): slower (v223) or faster (v224) mixes than
0.25 long-only / 0.25 multi-horizon / 0.50 flow are worse (local optimum); no long-only + book x0.9 (v225 T2) has the best worst
year (2.47%/mo, DD 19.95, win 52%) but dev4 4.97 < D2 5.26; member D / monthly schedule (v226) worse. Dev-only diagnostics
(not registered): open-interest flush at dip fills Spearman ~0; holding timed-out dip bids one more bar -0.40% vs -0.51% with fatter
tails; rip-selling shorts lose in every book regime. D2 remains the deployed executable pipeline.

LEADER 2026-09-28 (v212-v220, user goal: RL trader on the pipeline, executable orders): trade-mode agent hook (rule policy
reproduces v212 S3 exactly). Rules: S3 (one limit add/reduce) dev4 4.83 DD 20.7; E1 (+limit exit on signal loss) 4.22 DD 19.3;
v216 G2 grid trader (limit adjustments at most once a day, band max(3%,40%)) 4.84 / worst 1.65 / DD 18.0. RL: v214 fitted-Q /
Monte Carlo per-action boosted trees 3.3-3.8; v215 sparse-exploration one-step improvement with cross-fitting 3.2-3.6 (value
estimates favour early exits on fat-tailed trend payoffs); v217 evolution-strategy policy search 4.0-4.6 (in-sample gains do not
transfer across years). v218 D2 = G2 + dip-sleeve budget 0.15 / rung x1.75: dev4 5.26, worst 2.18, DD 19.1, final 5y 4.97,
last year 3.82 = BEST EXECUTABLE (deployed: scripts/forward_trade.py FREEZE 2026-09-28 08:00 UTC, web trade plan). v219
sleeve budget 0.18-0.21 breaches DD; v220 learned dip-bid filter hurts (bid outcomes not predictable at placement).

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
