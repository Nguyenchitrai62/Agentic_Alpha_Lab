
> Leader note (2026-10-06): the account-realistic carry add for G2 at f = 0.25 is +0.224 pp/month (5.410 -> 5.634, max yearly DD 16.91 -> 16.75, full-path 16.82 -> 16.66; carry profits compound in the account and the BOT sizes on total equity) [oc_carrycompound]; oc_carryfric's +0.12 (year-start sizing) is conservative and oc_carrycombo's +0.003 is a lower bound (carry gains kept outside the BOT equity).
# Executive summary (EN) — 2026-10-06 (consolidated)
Scope: BOT = book + dip ladder (needs bot); MANUAL = book-only human [FINAL_REPORT_VI].

## 1. Goal and validation protocol
- Mandatory goal (user 2026-09-27): >= 5%/month compounded net, DD <= 20%, majors only BTC/ETH/SOL/BNB/XRP Binance USD-M perps [AGENTS.md].
- Walk-forward replay: pretend "now" is the anchor, freeze everything, run every candle of the next year; most recent year (2025-09-24..2026-09-23) is "one year ago -> now"; 5 anchors 2021-2025 repeat it [AGENTS.md].
- All 5y are measured reset 1/4 capital per anchor, 4-clock mix, gate costs maker 0.02% / taker 0.055%, adverse long funding 0.01%/8h short zero [FINAL_REPORT_VI].
- Selection ONLY on first 4 years (anchors 2021-2024); most recent year scored ONCE for the frozen finalist, never for choosing [AGENTS.md].
- Gate: (a) 5y geometric mean >= 5%/month, (b) most recent year alone >= 5%/month, (c) no losing year; DD <= 20% full-path (max 4h-close and 1m-marked) [AGENTS.md].
- Robust rule (from v204): among DD <= 20% and no losing year in first 4y, prefer 4y mean >= 5%/month if any, pick highest worst-year, ties -> higher mean [AGENTS.md].
- Every trade like real: limit entry, SL market taker 0.055% + TP limit maker 0.02% on every position; unfilled limit expires (no market fallback); stop-first if both hit in one 1m bar [AGENTS.md].
- ZERO LEAKAGE: feature at t uses only data at close t; labels/normalisation/calibration/thresholds/model/params only before anchor minus embargo >= horizon [AGENTS.md].

## 2. Deployed system: G2 + quarterly carry f=0.25 in one Bybit UTA
- BOT G2: R2B1D17BF + dip gross cap 2.0x, flags `--corr-size --dip-mult 1.7 --bear-book --dip-gross-cap 2.0`, plan `trade_plan_v376.json` [FINAL_REPORT_VI].
- Account: Bybit cross margin, Hedge Mode, 5x all 5 coins; carry short quarterly leg 10x (spot-hedged), f=0.25 in the SAME UTA; beyond f=0.25 split capital [FINAL_REPORT_VI].
- Paper equity 5000 (recommended real >= 5000, best ~10000); entries PostOnly maker-only, TP/reduce GTC reduce-only; `risk_guard` ON at testnet/live (per-coin 2.5x / dip 2.0x / total 4x / single 1x), OFF at paper to stay engine-faithful [FINAL_REPORT_VI].
- G2 base (v421 NO / v422 yes, identical numbers): 5.41 %/month, worst 2.588, yearly maxDD 16.91, full-path official 16.82 (chained 16.91) [oc_frontier; oc_kpi_g2; oc_frontiercarry].
- Old deploy D17BF (v411): 5.425 (rounded 5.43, recent 5.06) / yearly DD 18.33 / full official 16.90 (chained 18.33) [oc_frontier; oc_kpi; oc_signedfunding].
- Yearly G2+D17BF reset [oc_kpi]: 2021: 2.83/DD 12.42; 2022: 3.51/16.23; 2023: 4.67/18.33 (D17BF) and mix G2 2023 6.045/DD 15.81; 2024: 11.27/8.26; 2025: 5.06/12.81 [oc_kpi; oc_phasedisp].
- Continuous D17BF: 4h-close DD 15.34, 1m-marked 16.90, gate 16.90, 5y net +2534% (26.3x) [oc_kpi].
- G2 KPI [oc_kpi_g2]: 26.4x after 5y, win all 65.3-65.5% (book 51.5%, dip rung 68.6-68.7%, n G2=5064/21513/26577), no losing year; 41% months >= +5%, ~70.5-72% months non-losing [oc_kpi_g2].
- G2+carry f=0.25 one UTA, LOWER BOUND (oc_carrycombo keeps carry P&L as non-compounding cash outside the BOT equity path, so yearly rates are diluted) [oc_carrycombo]: G2 5.410/2.588/16.91/16.82 (close 16.05) -> +carry 5.413/2.647/16.78/full-marked 16.34 (close 15.60); f=0.50: 5.418/2.705/16.65/15.86 [oc_carrycombo].
- Same combo year-start rebalance (conservative additive estimate; the account-realistic compounded estimate is oc_carrycompound 5.634): f=0.25: 5.533/2.736/16.78; f=0.50: 5.654/2.881/16.64 [oc_carryfric; OWNER_SUMMARY_VI].
- Yearly G2+carry f=0.25 roll-only (R/DD): 2021 2.647/10.79; 2022 3.283/16.78; 2023 6.168/15.72; 2024 10.559/8.08; 2025 4.593/12.57 [oc_carrycombo].
- Carry sleeve alone (BTC/ETH quarterlies, ENTER iff annualised basis >= 4%/yr, hold to delivery, fee drag 0.275% allocated): 33 entered of 50 seen, 33/33 net positive (min +0.18% allocated) [oc_cashcarry].
- Carry allocated yearly sums: 2021 0.0470; 2022 0.0528; 2023 0.2960; 2024 0.1219; 2025 0.0058 [oc_cashcarry].
- Carry 5y stacked +13.09% (f=0.25) = +0.218%/mo arithmetic (+0.213% geometric); f=0.50 +26.17% (+0.436/+0.416); most recent year ~+0.01%/mo [oc_cashcarry].
- One-UTA margin (43,805 hours) [oc_utamargin]: f=0.25 free min 22.49%, IM max 77.51%, 0 blocked, 0 MM breach, spot max 95.8%, worst-hour -10% gap -28.85% no liq — CLEAR; f=0.50 free min 1.85%, 1 hour blocked 2025-09-25 18:00, spot 179.9% — NOT clear [oc_utamargin; oc_utamargin2].

## 3. Honest numbers: frictions, clock luck, crash
- Frictions keep DD<=20 every row [FINAL_REPORT_VI]: base gate 5.43/DD 18.33/16.9 [oc_signedfunding]; 15' delay D17BF 5.24, G2 5.21/16.91 [DEPLOYMENT_PLAN_VI]; 50% stop slip (S4) D17BF 5.11/DD 20.0 (G2 4.90/17.31) [oc_stopslip]; real Bybit prices D17BF 4.97/19.9 (G2 4.88/18.11) [DEPLOYMENT_PLAN_VI]; 30' delay D17BF 4.68 (G2 4.58/17.32) [DEPLOYMENT_PLAN_VI]; cost stress (maker 0.0004/taker 0.0007+5bps) 4.58/<=20 (G2 4.57/17.45) [DEPLOYMENT_PLAN_VI].
- G2+carry f=0.25 under frictions (year-start) [oc_carryfric]: base 5.533; S1 4.696; S2 5.339; S3 4.717; S4 5.033; S5 5.016 — holds >=5.0 at base/S2/S4/S5, FAILS S1 and S3 even at f=0.50 [oc_carryfric].
- Clock luck [oc_clockluck]: 4 deployed dip clocks mean 7.72 vs 24-offset mean 7.12 (gap -0.59) -> random-clock expectation ~5.24 not 5.41 (adjusted yearly 2.593/3.233/5.453/10.691/4.401); keep 5.41 with ~0.17pp luck note, proxy method [oc_clockluck; OWNER_SUMMARY_VI].
- Seed luck negligible: 5 G2 seeds 5.343-5.430 (mean 5.387, deployed 5.410 rank 2/5), DD 16.54-17.03, no losing year — minus ~0.02pp [oc_seedengine].
- Crash/outage: instant -10% all 5 coins worst minute no-cap -58%, cap 2x 33.5% (3x: 39%), median/p99 unchanged [DEPLOYMENT_PLAN_VI; oc_gapstress].
- Real stop slip 1699 stops median -4.6 Binance/-1.6 Bybit (S4 ~18-19bps conservative at median, fair in 2021-type vol, too small for crash tail p90 +146/+197, p99 +495/+738) [oc_stopslip].
- COVID 03/2020 mix ~-16.1%, worst single clock -21.8% (over 20%, so single clocks banned); cap 2x never triggered in crash (peak gross <=1.03x) but kept for calm-air gaps [oc_crash2020].
- Routine outage cheap (weekly-2h 2.4%/monthly-6h 1.7%/quarterly-24h 0.9% of dip P&L) but losing the flush hour costs ~9%; rule: cancel waiting dip bids before planned maintenance [oc_outage].

## 4. Achieved vs not, and why
- BOT base PASS: G2 5.41 (luck-adjusted ~5.24, still above 5), DD 16.91/16.82 <=20, win all 65.3-65.5% >55-60, no losing year (W=2.588 G2) [oc_frontier; oc_kpi_g2; oc_clockluck].
- Bybit-price row G2 4.88 / D17BF 4.97 still DD<20 [DEPLOYMENT_PLAN_VI]; stretch win >60 PASS (all-trade 65.5%) [oc_kpi].
- DD <15 and 8%/mo NOT: frontier max only ~5.9 at DD>17.5 (G2K20 5.874/17.79, D20B11 5.894/21.21 FAIL); only stretch-DD candidate D13BF 4.97/yearly 14.98/full 14.86 misses return by 0.03pp and exceeds 15 under every friction [oc_frontier; oc_d13robust].
- MANUAL floor NOT: best honest M5_human 3.73 (dev4 3.66, recent 3.99), DD 17.9/17.8, book 64.8% (n=3744), W=0.85, missing ~1.3pp [oc_manualcap; oc_manualnight].
- MANUAL+carry best only 3.993 (equity-level 3.765), still missing ~1.0-1.2pp [oc_manualcarry].
- Why 8% unreachable: mechanical saturation — edge/unit notional flat in kd (0.0029->0.0028), B1 cuts ~35% notional, 2x cap trims tail nearly free (-1.42 DD for -0.015 R); extra size trades into DD (V2 +0.29 R for +5.75 DD) [oc_saturation].
- Edge not decaying (slope +0.067 CI [-0.158;+0.160]; second half 6.61 > first 5.59; latest 6m 7.38), so the ceiling is structural, not weak edge [oc_edgedecay].

## 5. Six methodology lessons
1. Book ideas go STRAIGHT to the 4-phase engine: 3/3 vectorised screens FAIL full engine (EXP +0.088 but 2021 -0.341; CME +0.014 but full DD +0.21pp; USDT -0.242) [oc_expiry4p; oc_cmegap4p; oc_usdt4p].
2. Dip screens need a placebo gate: full PROMISING legs + dSum5y >= +0.273 (pooled p95, ~3.5% of base 7.718; FPR 6.7%->0.7%) [oc_placebo_dip].
3. Exposure-matched control for tilts: constant-mult control + 500 block-shuffles; USDT ALPHA (gain +0.049, pct 99.4) still engine NO [oc_premexpo; oc_placebo].
4. Use 4-phase mean only: single clocks spread 3.10-6.92, DD to 43.55; mix locks clock luck [v376; oc_frontier; oc_phasedisp].
5. Check member sign balance: blend 0.8/0.2 interior but local steps flip sign by year (mean step 0.0134) — keep, never reselect [oc_blendsens].
6. Label post-hoc: post-hoc frontier moves never deploy; folds must transfer (WF-select 31 variants 6.03 vs fixed 6.08 — keep fixed D17BF+G2) [oc_wfselect; v419-v426].

## 6. Prospective evidence status
- Paper since 2026-10-05 (not yet 8 weeks, earliest ~2026-12-01): 5 `paper*` dirs at PAPER_DAY1 snapshot (~03:28 UTC), 7 at report time (added `paper_d17bfg2c` G2+carry 0.25 started 2026-10-06 07:19 UTC, BTC-25DEC26 basis ~5.31%, equity 5000, plus `paper_carry` ledger) [FINAL_REPORT_VI].
- Day one 2026-10-06: each bot equity ~4998.7-4999.6/return -0.03..-0.01%/maxDD 0.01-0.09%/fills 0 dip + 3-6 book, all book fills at price, 0 exits, every piece with stop+TP, unprotected/qty_mismatch none; all bots ~0.2-1.1 days old ("too early") [FINAL_REPORT_VI; DEPLOYMENT_PLAN_VI].
- Carry paper 2026-10-06 06:05Z f=0.5: BTC entered basis +5.42%, ETH skipped (<4%), MtM -0.15% too early [PROSPECTIVE_20261006].
- Carry parity 143/144 agree with the frozen rule (only genuine violation ETH retry-in at 3.80% <4% already fixed in bot/carry.py); exact basis within 0.2pp/yr only 56/144 (88 mid-vs-last illiquidity, not a rule bug) [oc_carryparity].
- Plan parity 0 mismatch every checked field (4 phases s0-s3 + merged `trade_plan_v376`) [oc_planparity].
- Go-live only after >=8 weeks paper + mandatory testnet, when ALL 4 hold: (a) paper >= p20 bootstrap; (b) paper DD <=15%; (c) bot-vs-plan <=1.5pp/mo (14 days to judge); (d) no cycle_error >1h, no stop-less position [DEPLOYMENT_PLAN_VI].

## 7. Open risks
- Testnet: code-review findings F1-F7 + N1-N4 were FIXED (commit 359004f, bot_reviewfix; 124 bot tests green); carry-enabled testnet is now allowed after preflight PASS; live only after a clean 7-day testnet [docs/opencode/CODEREVIEW_BOT_20261006.md; docs/BOT_EXECUTION.md].
- Frontend already deployed the paper-carry panel calling `GET /api/carry`, but the old local backend lacks the route — restart the local backend ONCE (`backend/carry_view.py` reads `paper_carry/state.json`, audit SAFE TO PUSH) [OWNER_SUMMARY_VI].
- Old dip cap in the bot was TIGHTER than the engine; engine-faithful fix done on paper (C_on 3.20%/261 fills vs uncapped 3.58%/271, old cap 1.12%/209) but until merged run WITHOUT cap or accept lower [bot_capfix].
- Capital must withstand 25% DD: bootstrap P(DD>20%) ~11%, P(>25%) ~2.1% [oc_mcdd].

## 8. Where to look
| Topic | Start here |
|---|---|
| Numbers above (canonical) | docs/FINAL_REPORT_VI.md; docs/OWNER_SUMMARY_VI.md; docs/DEPLOYMENT_PLAN_VI.md |
| Closed vs open directions, 6 lessons | docs/CLOSED_DIRECTIONS.md |
| Go-live gates, stops, paper/testnet/live path | docs/DEPLOYMENT_PLAN_VI.md; docs/BOT_RUNBOOK_VI.md; docs/QUICKSTART_VI.md |
| Bot code review (F1-F7, fixed in 359004f) | docs/opencode/CODEREVIEW_BOT_20261006.md |
| Carry rule, margin, parity, audit | oc_cashcarry; oc_carrycombo; oc_utamargin/oc_utamargin2; oc_carryparity; carry_audit/COMPARISON.md |
| Frictions, clock luck, crash, saturation, decay | oc_carryfric; oc_clockluck; oc_stopslip; oc_gapstress; oc_crash2020; oc_outage; oc_saturation; oc_edgedecay |
| Paper runners and daily ops | PAPER_DAY1_20261006; PROSPECTIVE_20261006; scripts/daily_status.py + bot_health.py + paper_report.py + prospective_scorecard.py |
