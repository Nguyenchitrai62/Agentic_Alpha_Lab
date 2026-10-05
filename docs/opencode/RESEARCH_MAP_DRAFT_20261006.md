# Research map DRAFT 2026-10-06 (v390-v424 + 2026-10-05 OpenCode screen wave; for leader merge, not the map)

Last draft: 2026-10-06. Sources: .claude/skills/alpha-lab-leader/research-map.md (to v390), CONTINUOUS_RESEARCH.md 2026-10-04..06 top paragraphs, research/tournament/oc_frontier/REPORT.md (80 rows v399-v423, reset 5y metric). All five walk-forward years are research data; findings need prospective validation.

## Current state
- BOT deployment pick = v411 R2B1D17BF (dips x1.7 corr-size + bear-book): 5y 5.425 %/mo, worst 2.83, max yearly DD 18.33, full-path 16.90, win 65.5%; frictions all DD <= 20 (lat15 5.24, stop-slip 5.11/DD20.0, Bybit 4.97/19.9, lat30 4.68, stress 4.58). Runbook: D17BF + --dip-gross-cap 2.0 (engine hook sleeve_gross_cap; oc_gapstress: -10% all-coin gap 58% -> 33.5% equity; oc_kpi dip notional to ~6.4x without cap). Paper bots: R2-4P, d17bf, d17bfg2, g2k20.
- FRONTIER (oc_frontier, yearly DD): R2B1 4.55/13.88 - D13 4.957/15.00 - X45 5.118/15.92 - G2F20K20 5.346/16.20 - G2 5.41/16.91 - G15K20 5.731/16.96 - G2K20 5.874/17.79 - D20B11 5.894/21.21. Full-path: D15B08 4.626/14.94 - F20K17 5.042/15.47 - X45 5.118/15.81 - G2F20K20 5.346/16.02 - S5 5.416/16.62 - S6 5.565/16.71 - G15K20 5.731/16.76 - G2K20 5.874/17.69 - D20B11 5.894/19.10. Deploy pick on NEITHER (dominated yearly by G2K20, full-path by S6). Stretch DD<15 + >=5%/mo only at edge: v424 D13BF 4.97/yearly 14.98/full 14.86.
- MANUAL best honest ~3.6-3.7 %/mo, DD > 20: manualbf (MANUAL + bear-book, human 15-min/night-skipped schedule) 3.6-3.7/DD21.6 worst-phase 33->25; oc_manual2 top-2 dips 3.06/DD19.5 fails base; human costs ~0.6pp; ~80% capital for DD<20 (~2.8%/mo). MANUAL floor still open.

## v390-v424 tried / result / verdict
- v390 ex-ante covariance book sizing (R2-4P): 4.82/4.87 vs 5.24, DD not lower -> rejected.
- v391 tournament sizes on R2-4P: R2K 5.85/3.03/25.2, R2C 5.58/2.33/23.1, R2T 4.84/1.69/24.3 vs 5.24/1.96/23.1; fold3 lost by 0.0014 -> no transfer, rejected.
- v392 kelly x0.9/x0.8: 5.59/24.3, 5.25/25.5 -> scaling moves size into wrong episodes, rejected.
- v393 MANUAL M5 + size tables: M5K 3.82/27.8, M5C 3.98/27.4 vs M5 4.09/24.4 -> M5 kept.
- v394 sizes + 6-sigma close-stop: R2CS6_4P 5.147/2.13/19.39 (first honest >=5 + DD<=20), R2KS6 5.15/2.94/22.2; folds prefer R2K -> no transfer (robust pick R2CS6).
- v395 GATE scored ONCE recent year: R2CS6_4P 3.48/DD25.15 (R2-4P 3.90/18.8) -> 5y 4.81 FAIL (a)/(b)/DD; dip-size gains do not transfer (as v279/v280/v189-197).
- v396 risk-to-book: folds keep R2 -> rejected.
- v397 book shape (EMA/long-only): 3.62/4.46 vs 4.82 -> rejected (shorts hedge, smoothing delays).
- v398 11-coin dip sleeve: X11 4.39/1.07/31.6, X11N 4.09/losing/40.1 vs R2 4.82/1.96/25.1 -> majors-only confirmed, rejected.
- v399 corr-aware B1 (n=other majors >=2.5sg at f-1): B1 1/(1+n) 4.55/13.88, B2 4.62/17.71 vs R2 4.82/25.05 -> DD breakthrough, return down.
- v400 risk back on B1: R2B1_130 5.171/1.40/17.06 (recent 5.43), _150 5.46/18.92, B2_130 5.52/23.13 -> R2B1_130 first base pass, selected.
- v401 +2.0sg rung: DD up -> rejected. v402 earlier 2.0sg flush detect: worse -> rejected. v403 book loss control (tighten/SL3): worse -> rejected. v404 tighter gov 0.18/0.10 + 0.25/0.15: 4.47-4.78/full 18.7 -> DD down return down, rejected. v405 gov+more risk: worse -> rejected.
- v406 book->dips: D16 5.137/2.01/17.33/16.37, D18B08 5.042/2.49/18.70/17.22 -> first incl full-path DD, base PASS.
- v407 dips x2.0: 5.779/2.52/20.95, D20B11 5.894/2.40/21.21 -> return up DD breach, rejected.
- v408 D18 5.452/2.37/19.14/17.57 -> best BOT row then, candidate.
- v409 alloc frontier to stretch DD: D13 4.957/15.00/16.36, D15B08 4.626/15.99/14.94, D16B06 4.325/16.38/15.21 -> DD down return down, kept as frontier only.
- v410 bear-book (longs x0.5 BTC<1200-bar mean): D16BF 5.236/2.73/17.4/16.2, D18BF 5.564/3.01/19.2/17.6 (audit+robust PASS; Bybit 5.09/DD20.8) -> gain, DD mixed.
- v411 R2B1D17BF (x1.7 + bear-book) 5.425/2.83/18.33/16.90 win65.5, frictions all DD<=20 -> DEPLOYMENT PICK (paper artifacts/bot/paper_d17bf).
- v412 short gate: gain only 2023 -> rejected. v413 hourly+B1 DD30-38 (4th hourly failure) -> rejected. v414 DVOL size tilt: more return more DD -> rejected.
- v415 close-stop 5/6sg: S5 5.416/18.37, S6 5.565/18.37 vs 5.425/18.33 -> no DD gain, folds keep D17BF, rejected (run-before-register deviation disclosed).
- v416 BTC-dominance tilt: 5.194/20.45/18.37 -> rejected.
- v417 cascade (24h cooldown / XRP5.5, post-hoc): C 5.416/3.44/18.45, X 5.574/18.37, CX 5.504/18.55, no fold transfer -> rejected.
- v418 DVOL short gate: 5.547/18.35/recent 4.50 -> rejected.
- v419 breaker/budget (post-hoc labelled): BRK05 5.36/18.32, BRK08 5.401/18.33, BUD13 5.392/18.33 -> neutral, closed.
- v420 flush x mult: F20K17 5.042/2.52/16.00/15.47, F15K20 4.993/16.17, F15K23 5.281/16.97, F20K20 5.30/18.41 -> frontier moves only.
- v421 gross cap G (notional<=Gx): G2 5.410/16.91 (same return DD-1.4), G3 5.291/18.33 -> safety pick (3 rows audit NO; twin in v422 audited).
- v422 cap+size: G2K20 5.874/2.83/17.79/17.69 (best R; fold fails recent), G15K20 5.731/16.96, G2F20K20 5.346/16.20 -> no deploy (post-hoc + fold fail).
- v423 drop deep rungs: X45 5.118/15.92/15.81, X5 5.311/16.87, X45G2 5.015/16.11 -> DD down return down, frontier (audit PASS).
- v424 stretch combo D13BF 4.97/14.98/14.86 -> frontier edge, below base.

## Closed screen directions (2026-10-05 wave, one line each)
- oc_rips: regime-conditional rip-sell ladder -> every rule 5y negative, LOYO unstable (-3.7 vs dips +11.7) -> asymmetric edge, closed for good.
- oc_regime: slow regimes of dip edge -> signs flip >=2/5y -> no gate, closed.
- oc_newinfo: Wikipedia attention / CME gaps -> two fragile hints for logging only, not tradable -> closed.
- oc_optctx: Deribit skew/put-flow/Coinbase premium context -> NOT PROMISING, closed.
- oc_idea3 pre-bar RV skip / oc_idea10 1h confirmation / oc_volflush capitulation volume -> no transfer, closed.
- oc_idea7 VRP budget dial (2022 inversion) / oc_idea4 funding surprise (tail 3/5) / oc_idea5 premium-flip veto / oc_idea8 dominance-momentum throttle (tail 3/5) -> closed.
- oc_manual2 MANUAL top-2 dips 3.06/19.5 -> fails base, closed.
- oc_idea2wf walk-forward per-coin stops / oc_coinwf coin WF weights / oc_cooldown stop cooldown -> sums up, tails worse, closed.
- oc_velocity velocity guard / oc_b1soft soft B1 / oc_adaptsig adaptive sigma / oc_deeptp deep-rung fast TP -> no gain on frontier, closed.
- oc_bullbook bull-book boost / oc_rlbear RL bear-feature agents (V0 exact) / oc_dailyladder daily ladder / gross-cap-alone selection -> along frontier or neutral, closed.
- oc_idea6 basis momentum / oc_beartp bear-bar fast TP / oc_bookbrake book brake / oc_bookdipnet book-dip overlap / oc_b1btc B1-BTC / oc_b1deeper deeper price (DD down 5/5 sum down 4/5) / oc_weekend weekend / oc_eventblk macro blackout / MANUAL static corr proxy (0/5) -> closed.
- Tournament dip size/TP models (kelly V2/context V2/tp V2 lose newest regime; tp=+TP1.5 which lost v391R2T) -> direction CLOSED; v395 lesson: dev dip-sizing gains need paper-log proof before any dev-selected change.

## Open queue
- Prospective paper evidence first: R2-4P / d17bf / d17bfg2 / g2k20 bots + scripts/bot_health.py, paper_report.py, paper_compare.py; rolling-12m (49: median 4.89, none losing, all DD<20) is in-sample.
- Liquidation/top-book data: backend/liquidations.py (Bybit liqs + Binance forceOrder + top-book) collecting since 2026-10-04 -> features only after 4-12 weeks; oc_liq stream healthy but too short; oc_topbook/oc_venuegap pending.
- Bot-vs-engine parity fixes: bot_beartrim committed; plan-staleness fix (4h plan dropped after 2h -> bids cancelled mid-bar; restarted 14:25 UTC); sleeve_gross_cap + --dip-gross-cap wired; Bybit-price/latency/stop-slip frictions in runbook; oc_dvolshort (short-leg only, 5/5) screen running.

## Lessons
- Frontier: B1 threshold / mult / gross cap / deep-rung drop / bear-book all trade return for DD (oc_frontier); no free DD; overlays (D13BF edge 4.97) cost return.
- Attribution: additive rung/sleeve sums mislead (oc_contrib/oc_plateau); only the 4-phase reset-metric engine_user run decides (metric correction: continuous 1/4 mix let lucky phase-0 43x dominate).
- Ops: background tasks default 30min -> workers get 2h timeout, paper bots under nohup; backend IS the plan source (stall froze plans 12:03 UTC; restarted LOCALLY 127.0.0.1 no tunnel); monitor plans, not just bots.
