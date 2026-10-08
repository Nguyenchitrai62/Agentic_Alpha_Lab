# Closed directions map (for future agents, 2026-10-06)

Scope: BOT = book+dip ladder (G2 `R2B1D17BFG2` 5.41%/mo, DD 16.91/16.82); MANUAL = book-only human (best ~3.7).
All numbers walk-forward 5y, reset 1/4 capital per anchor, gate costs (maker 0.02%/taker 0.055%,
adverse long funding 0.01%/8h). All 5y are research data now; clean proof is prospective paper only.
Sources: `docs/FINAL_REPORT_VI.md`, `.claude/skills/alpha-lab-leader/research-map.md`,
`docs/RESEARCH_INDEX.md` (regen 2026-10-06, 326 rows), `docs/opencode/IDEAS2_20261006.md`,
`docs/opencode/IDEAS3_20261006.md`, `docs/opencode/FACTCHECK_CLOSED_20261006.md`. Do not re-run CLOSED without new data/harness change.

## 6 methodology lessons (mandatory)

1. Vectorised book screens fail the engine 3/3 (`oc_expiry4p`,`oc_cmegap4p`,`oc_usdt4p` NO) — book ideas go straight to 4-phase engine.
2. Dip screens need placebo gate: full PROMISING legs + dSum5y >= +0.273 (`oc_placebo_dip`; pooled p95).
3. Exposure-matched control for tilts (`oc_premexpo`, `oc_placebo`): constant-mult control + 500 block-shuffles; USDT alpha pct 99.4 yet engine NO.
4. 4-phase mean only (`v376`,`oc_frontier`): single clock spreads 3.10-6.92%/mo, DD up to 43.55; mix locks clock luck.
5. Always check member sign balance: blends interior but sign flips by year (`oc_blendsens` 0.8/0.2 interior, steps flip sign).
6. Post-hoc combinations must be labelled (`v419-v426`,`oc_expirycb`): post-hoc frontier moves never deploy; folds must transfer.

## Still OPEN (leader-corrected 2026-10-06 evening; everything else below is closed)

- DEPLOYED: G2 (R2B1D17BF + --dip-gross-cap 2.0) + quarterly cash-and-carry f = 0.25 in one Bybit UTA (carry short 10x). Evidence now
  comes only from prospective paper: `paper_d17bfg2` (G2) and `paper_d17bfg2c` (G2 + carry, started 2026-10-06), plus `paper`,
  `paper_d17bf`, `paper_d13bf`, `paper_g2k20`, the carry ledger `paper_carry`; go-live needs >= 8 weeks + the 4 gates.
- Running when this was written: Kaggle G2 joint-jitter robustness job (account 2, `ops_jitterjob`), `oc_calendar` (near/far
  quarterly spread), `oc_tpfill` (TP same-minute realism), `oc_carrycorr` (carry diversification), bot ops (maint window, soak,
  carry qty).
- Data maturing: liquidation / top-of-book collector (since 2026-10-04) -> walk-forward features earliest 2027-01-04 (`oc_liqcheck`).
- Hypothesis only (no rule): `oc_grindsignal` breadth = 1.0 as an over-extension gate.
- CLOSED today (do not repeat): book models C1 (v428) and C2 (v427) rejected; `oc_bookcoinbrake` tested in the engine as v426 G2BRK
  (5.30 vs 5.41, on the frontier, not adopted); carry variants FAR / top-up / calendar-linear-vs-inverse / weekly; discount sniper;
  MANUAL 2-coin and MANUAL + carry; expiry-day dip; mark-trigger stops; 2h bid TTL; depth-tilted sizing; re-arm; fill-relative TTL;
  stop timeframe; seasonal depth; USDT premium (book: engine NO; dip: NO); CME gap; expiry book; 8 clocks.
- Rejected by rules (not testable as specified): stop-limit stops (stops must be market), maker re-peg (no chasing), cross-venue
  routing (one account), funding-settlement flat (gate funding is flat).
- 2026-10-07 update: DEPLOYED unchanged — G2 (R2B1D17BF + --dip-gross-cap 2.0) + quarterly cash-and-carry f = 0.25 in one Bybit UTA stays; nothing newly deployed, nothing removed.
- 2026-10-07 running: `oc_kronoshidden` (Kronos dip tilt, post-release year is the verdict), Deribit strike-level fetch (`oc_deribitstrike_BTC/ETH` + backfill), `bot_soakinv` (paper invariance soak), straddle paper ledger (`scripts/straddle_paper.py`, first possible entry Fri 2026-10-09 08:05 UTC), keepalive tasks (`AlphaLabRunnersKeepAlive` + backend watchdog).
- 2026-10-07 closed (do not repeat): `oc_relflush`, `oc_tailhedge`, `oc_ripcont`, `oc_manualsplit`, `oc_stablegate`, `oc_putwrite`, `oc_vrpgate`, VRP straddle family (`oc_vrpstraddle` + `audit_vrpstraddle` PASS-WITH-NOTES + `oc_vrprobust` + `oc_vrpconsistent` + `oc_vrpstrangle`, all NOT DEPLOYED) — see §11.

## 1. Dip ladder sizing / exits / timing / filters

- `v399/B1` | size x1/(1+n) corr-aware | KEPT (manifest rejected on folds, component kept downstream) | DD 25.05->13.88, R 4.82->4.55, base of all later | 2026-10-05
- `v411/D17BF` | dips x1.7 + bear-book | KEPT deploy | 5.425/DD18.33/16.90, win all 65.4% | 2026-10-05
- `v421/G2` | dip gross cap 2.0x | KEPT deploy (manifest rejected on folds, component kept downstream as safety overlay) | same R 5.41, DD -1.4pp, gap -10% 58%->33.5% | 2026-10-05
- `v400/R2B1_130` | re-risk x1.3 on B1 | KEPT step | first base pass 5.17/DD17.06 | 2026-10-05
- `v406/D16` | risk book->dips | KEPT step | 5.137/DD17.33/16.37, first full-DD pass | 2026-10-05
- `v410/bear-book` | longs x0.5 when BTC<1200bar mean | KEPT | D18BF 5.564/DD19.2, weak year up | 2026-10-05
- `oc_dipexit` | 4 alternative TP exits | CLOSED | all fail; TP 1.0sg stands | 2026-10-05
- `oc_tpdecay` | decay TP 1.0->0.5sg | CLOSED | sum 3/5, DD 1/5; win up but sum +1% only | 2026-10-06
- `oc_bybittp` | venue TP asymmetry | DIAGNOSTIC | divergent TPs 84% become timeouts; no fix | 2026-10-06
- `oc_tpbyn` | TP1.5 iff n>=2 | CLOSED | gains 2023-25 only, fails 4/5 rule | 2026-10-06
- `oc_diptilt` | tilt x1.2/x0.8 bull/bear | CLOSED | return 4/5 but DD 1/5 | 2026-10-06
- `oc_beartp` | bear-bar fast TP 0.5sg | CLOSED | DD 4/5 but sum 0/5 | 2026-10-06
- `oc_deeptp` | deep-rung fast TP | CLOSED | 1/5 both legs; keep TP1.0 | 2026-10-05
- `oc_dipbe` | break-even protection | CLOSED | keep >=97% sum 0/5, DD 3/5 | 2026-10-06
- `oc_holdext`/`oc_condhold` | hold timeout +4h / in-profit-only | CLOSED | 1/5 and 3/5+1/5; exit next open stands | 2026-10-05/06
- `oc_fillttl` | fill-relative exits T120/T240 | CLOSED | 3/2/2 best; 4h-clock exit stands | 2026-10-06
- `oc_earlystart` | enter before bar close | CLOSED (screen PROMISING; fragile, 2023 -0.68 with DD doubled, paper-first) | 4/5+4/5 but 2023 -0.68, paper needed first | 2026-10-05
- `oc_rungspace` | wider rung spacing | CLOSED | DD 5/5 but sum 1/5; keep R2 spacing | 2026-10-06
- `oc_rungcap` | cap 3 fills/coin/bar | CLOSED | keep >=97% 0/5; cut rungs win 72-83% | 2026-10-06
- `oc_b1wide` | half-weight alt flush detector | CLOSED | sum 3/5, DD 0/5 | 2026-10-06
- `oc_b1soft` | soft correlation count | CLOSED | beats B1 1/5; hard F=2.5 stands | 2026-10-05
- `oc_btclead` | BTC-lead alt deepening | CLOSED | sum 0/5 (10.33 vs 15.14), DD 1/5 | 2026-10-06
- `oc_b1deeper` | correlation-aware dip price | CLOSED | DD 5/5 but sum 1/5 | 2026-10-05
- `oc_b1btc` | BTC-inclusive flushes | CLOSED | beats B1 3/5, DD 2/5 | 2026-10-05
- `oc_trendladder` | depth by BTC trend | CLOSED | sum 3/5, DD 2/5; fixed R2 stands | 2026-10-06
- `oc_lowvolrung` | gated 2.0 rung low-vol | CLOSED | sum 3/5, DD 0/5 | 2026-10-06
- `oc_breadthdip` | dip x0.8 when breadth=1 | CLOSED | DD 5/5 but sum 1/5; full-size stands | 2026-10-06
- `oc_cooldown` | 24h post-stop cooldown | CLOSED (screen PROMISING; cascade-fuse-only, essentially 2022 FTX) | 4/5 DD but only 2022 real; cascade fuse only | 2026-10-05
- `oc_rearm` | re-arm rung same bar | CLOSED | adds thin losses 2/5y, DD up 5/5 | 2026-10-06
- `oc_velocity` | 3-sigma velocity guard | CLOSED | sum 3/5, DD 3/5; deletes winners | 2026-10-05
- `oc_adaptsig` | vol-adaptive sigma | CLOSED | DD 4/5, efficiency 3/5; sigma360 stands | 2026-10-05
- `oc_ewmasig` | EWMA sigma hl60 | CLOSED | sum 1/5, DD 2/5 | 2026-10-06
- `oc_seasondepth` | hour-of-week sigma scaling | CLOSED | sum 1/5, DD 1/5 | 2026-10-06
- `v401/v402` | +2.0sg rung / earlier detect | CLOSED | DD up / worse | 2026-10-05
- `v407` | dips x2.0 | CLOSED | 5.78 but DD 20.95 breach | 2026-10-05
- `oc_dvol` | DVOL level/premium dip filter | DIAGNOSTIC (screen PROMISING; small sub-bps non-monotonic context) | 5/5 IC but small; see `oc_dvolshort` | 2026-10-05
- `oc_dvolshort` | DVOL short-gate x0.5 | PROMISING screen | DD 4/5, P&L not lower; engine check pending | 2026-10-05
- `oc_idea2` | per-coin close-stop XRP5.5/rest4sg | PROMISING screen | 4/5 + LOO 5/5, tails 4/5 | 2026-10-05
- `oc_idea2wf`/`oc_coinwf` | WF per-coin stops/weights | CLOSED | sums transfer, tails 1/5 and 3/5 | 2026-10-05
- `oc_agentskip` | skip if both HGB halves <-0.002 | CLOSED | sum 2/5, DD 4/5; 2023-25 skips winners | 2026-10-06
- `oc_filltime` | late fills (f>=209) worse | DIAGNOSTIC | trails 10-39bps 4/5y, win lower 5/5 | 2026-10-06

## 2. Book tilts and filters

- `v410/bear-book` | longs x0.5 BTC bear | KEPT | weak-year gain, DD mixed; in deploy | 2026-10-05
- `oc_bookcorr` | scale x clip(1.5-rho) | CLOSED #43 | DD 5/5 but retention>=90% 1/5 (permanent delev) | 2026-10-06
- `oc_coinbear` | per-coin bear extension | CLOSED #44 | DD 3/5, grind -0.0504->-0.0506 unchanged | 2026-10-06
- `oc_longcap` | total long cap 0.6 | CLOSED #46 | retention 0/5 (0.848-0.948), binds 9.1% only | 2026-10-06
- `oc_cadence` | 8h/12h slow cadence | CLOSED #47 | P&L 2/5, DD 1/5; stale drag >> fee save | 2026-10-06
- `oc_bookbrake` | brake on worst week | CLOSED | DD 4/5 but <=1.1pp, P&L -2..-9pp 4/5 | 2026-10-05
- `oc_bookdipnet` | dip-timeout book brake | CLOSED | strict never fires by design; lenient cuts combo | 2026-10-05
- `oc_bullbook`/`oc_bullshort` | bull long boost / bull short halve | CLOSED | return 5/5 but DD worse / mirror loses 4-5/5 | 2026-10-05
- `oc_bearshort` | bear short x1.25 | CLOSED | P&L 3/5, DD worse 4/5 | 2026-10-06
- `oc_bookcoinbrake` | per-coin DD brake S30 | CLOSED (screen PROMISING; superseded by v426 G2BRK frontier, not adopted) | DD 4/5, P&L 4/5, grind -30% | 2026-10-06
- `oc_bookholdcap` | 42-bar same-sign cap | CLOSED #65 | P&L 2/5, DD 2/5, cost +45% | 2026-10-06
- `oc_bookoffset` | vol-scaled limit offset | CLOSED (screen PROMISING; trade-mode already sigma-scaled, no engine run) | 5/5 but trade-mode already sigma-scaled | 2026-10-06
- `oc_bookcoinwf` | positive-history coin gate | CLOSED (screen PROMISING; vacuous, gate never excludes) | 5/5 but gate never excludes | 2026-10-06
- `oc_bookexit` | +1.0 ATR bank | CLOSED | win up 4/5 (+2021 tie) but P&L -18..-62pp | 2026-10-06
- `oc_bookthresh` | |w|<q25 -> 0 | CLOSED | P&L up 1/5 only | 2026-10-06
- `oc_bookweekend` | weekend-flat book | CLOSED | P&L 0/5, DD 1/5 | 2026-10-06
- `oc_bookevent`/`oc_fomcbook` | halve on macro/FOMC windows | CLOSED | bookevent DD 3/5 + ret 3/5 (windows +4/5), fomc DD 4/5 + ret 2/5; windows P&L positive | 2026-10-06
- `oc_bookfunding` | x0.75 longs if 7d funding>p80 | CLOSED #56 | 3/5 both; 5y -8.8%, hot funding marks strength | 2026-10-06
- `oc_cbpremium`/`oc_usdtprem` | Coinbase/USDT premium tilt | CLOSED #60 | P&L 5/5 and 4/5 but DD 2/5; variance only | 2026-10-06
- `oc_skewbook`/`oc_skewbook2` | skew high-minus-low / long gate | CLOSED #59 | sign 3/2 flip; gated P&L 1/5 | 2026-10-05/06
- `oc_basisbook` | basis-collapse long x0.5 | CLOSED #61 | 4/5+3/5; 2023 fails both | 2026-10-06
- `oc_breadthbook` | longs x0.75 if breadth=1 | CLOSED #63 | DD 5/5 but P&L 2/5 (-6.7% 5y) | 2026-10-06
- `oc_dvolbook` | DVOL level short-leg filter | PROMISING screen | 5/5 sign, 4/5 LOYO; small | 2026-10-05
- `oc_dombook`/`oc_ethbtc` | dominance tilt | CLOSED | return 5/5 but DD worse 2/5; fragile +0.02bps | 2026-10-05
- `oc_expirybook` | halve book 48h pre-expiry | SCREEN PROMISING #62 | DD 4/5 P&L 4/5 BUT engine `oc_expiry4p` NO | 2026-10-06
- `oc_expirycb` | expiry + premium combo | CLOSED post-hoc | P&L 4/5 but DD 1/5; tilt eats expiry DD | 2026-10-06
- `oc_cmegap` | CME-gap long tilt | SCREEN PROMISING (screen PROMISING; engine `oc_cmegap4p` NO) | 4/5 P&L + DD 5/5 BUT engine `oc_cmegap4p` NO | 2026-10-06

## 3. Book models (members, C1/C2)

- `v285/D2/CB` | 0.8 CB + 0.2 Coinbase-premium D | KEPT base | first gate pass 5y 5.725/last 5.167 | 2026-09-30
- `v316/PT` | pooled 77-coin tree member | DIAGNOSTIC | IC 3/4 dev but MANUAL pullback only | 2026-10-02
- `v324/v326` | efficiency-ratio / 77-coin GRU | CLOSED | IC>0 yearly but book worse; GRU << tree | 2026-10-03
- `v337` | options-informed member | CLOSED | MANUAL 2.73, BOT DD 22.8; folds keep base | 2026-10-03
- `oc_bookmodel_impl` | C1/C2 implementation only | CLOSED impl done | 11 tests pass; audit F1 fixed via allowlist, reaudit PASS | 2026-10-06
- `v427/C2` | rank-calibrated HGB+Platt | CLOSED rejected | fixed run worse than deployed book 3/4y with a losing year; C1/C2 direction rejected | 2026-10-06
- `v319/PP/PF` | path-label / flow members | CLOSED | good IC but worsen book (2.48/2.31 vs 3.01) | 2026-10-02
- `v336` | top-10 alt book breadth | CLOSED | alts 0.73 vs majors 1.80; majors-only confirmed | 2026-10-03
- `v398/X11` | 11-coin dip sleeve | CLOSED | 4.39/DD31.6 vs R2 4.82/25.1; correlated weak alts | 2026-10-05

## 4. Sleeves and structural sources

- `oc_cashcarry` | quarterly spot+short hold to delivery | KEPT add-on | +0.21/mo f=0.25, DD ~0; 57% from 2023; headline +0.21/+0.13pp (5.533) is year-start conservative; expectation is oc_carrycompound 5.634/16.75/16.66 | 2026-10-06
- `oc_xsrev` | 1d cross-sectional reversal sleeve | CLOSED | loses 5/5 (-2.5..-5.4/mo), DD 5/5 worse | 2026-10-06
- `oc_dailyladder` | daily dip ladder | CLOSED | earns 4/5 corr 0.26 but DD worse 4/5 | 2026-10-05
- `oc_rips` | regime rip-sell ladder | CLOSED | every rule 5y negative | 2026-10-05
- `oc_postflush` | post-flush recovery drift | CLOSED | mean negative 3/5, 2-10 events/yr <10 floor | 2026-10-06
- `oc_tsmom*` | 30d TSMOM overlay 0.10/0.25x | CLOSED | return +5/5 but DD worse 5/5 (corr add-on, not diversifier) | 2026-10-06
- `oc_idea9` | DD-buy rule | CLOSED (screen PROMISING; DD-bar only, costs return/Sharpe 5/5, do not adopt) | 4/5 DD but costs return/Sharpe 5/5 | 2026-10-05
- `oc_newinfo` | Wikipedia attention + CME gap | CLOSED | two fragile hints, logging only | 2026-10-05

## 5. Execution (fills, stops, TTL, venue)

- `oc_stopslip` | 1699 stops slip study | DIAGNOSTIC | S4 conservative median; tail p99 +495/+738bps justifies cap | 2026-10-06
- `oc_gapstress` | instant -10% gap stress | DIAGNOSTIC | no-cap -58%, cap2x 33.5%; runbook cap | 2026-10-05
- `oc_venuegap`/`oc_bnbvenue` | venue attribution | DIAGNOSTIC | drag in dip leg ~4% rung P&L; BNB 10x spread | 2026-10-06
- `oc_bookvenue` | S5 venue decomposition | DIAGNOSTIC | drag NOT in book execution | 2026-10-06
- `bot_capfix` | engine-faithful gross cap | KEPT fix | 209->261 fills, +1.12%->+3.20% vs 3.58% uncapped | 2026-10-06
- `bot_parity` | bot vs engine rules | DIAGNOSTIC | YES implements rules | 2026-10-05
- `oc_vipfees` | VIP1/VIP2 repricing | DIAGNOSTIC | +0.11/+0.16/mo but volume unreachable; keep VIP0 | 2026-10-06
- `oc_premfill` | perp-vs-spot at fill | CLOSED | IC vs LOYO disagree; no stable sign | 2026-10-06
- `oc_premexpo`/`oc_placebo*` | exposure control + placebo | METHOD | USDT alpha pct99.4 yet engine NO; dip gate +0.273 | 2026-10-06

## 6. Risk overlays and frontier

- `oc_frontier` | 80-row return-DD frontier | KEPT map | no free DD; D17BF interior; stretch only 4.97/DD14.98 | 2026-10-05
- `v409/D13/D15` | allocation to DD | CLOSED frontier-only | DD down return down | 2026-10-05
- `v420` flush-mult / `v423` drop-deep / `v424` D13BF | frontier moves | CLOSED frontier | F20K17 5.04/16.00; X45 5.12/15.92; D13BF 4.97/14.98 | 2026-10-05
- `v425` cap on conservative / `v426` per-coin brake | frontier | CLOSED | cap binds only large kd; G2BRK 5.30/16.02 | 2026-10-06
- `oc_wfselect` | walk-forward robust select | CLOSED | fixed D17BF+G2 6.03 vs 6.08; keep fixed | 2026-10-05
- `oc_phaserebal` | monthly/weekly rebalance | CLOSED | return -0.15/-0.18pp, DD up (2023) | 2026-10-06
- `oc_corrbudget`/`oc_idiocap` | corr scaling / idio caps | CLOSED | -40% sum / worst-day 0/5, maxDD 1/5 | 2026-10-05
- `oc_longcap` already in §2; `v404/v405` governors | CLOSED | DD down return down | 2026-10-05

## 7. Clocks / phases

- `v376/4P` | 4 clocks x1/4 capital | KEPT harness | locks clock luck; all selection on this | 2026-10-04
- `oc_phasedisp` | single-clock dispersion | DIAGNOSTIC | singles 3.10-6.92, DD to 43.55; never run single | 2026-10-06
- `oc_clockanat` | phase-3 2023 anatomy | DIAGNOSTIC | async phase DD; cap G2 binds | 2026-10-06
- `v387/8P` | 8 clocks | CLOSED | 4.58 vs 4P 5.24; dilutes luck further, lower R | 2026-10-04
- `oc_rolling17` | 49 rolling 12m windows | DIAGNOSTIC | median 4.89, 49% >=5%, 100% DD<20, none losing | 2026-10-05

## 8. MANUAL product

- `M5_human` | 15-min/night-skip schedule | KEPT best honest | 3.73/DD17.8 4-phase-mix (single-clock mean 24.5), win 64.8%; -0.6pp human cost | 2026-10-06
- `oc_manualbf` | MANUAL + bear-book | DIAGNOSTIC | 3.6-3.7/DD21.6; still under base | 2026-10-05
- `oc_manual2` | top-2 dips | CLOSED | 3.06/DD19.5 fails base | 2026-10-05
- `oc_manual3` | static corr proxy | CLOSED | 0/5 years; dynamic rule itself cuts 2/5 only | 2026-10-05
- `oc_manualcap` | order caps G15/G10 | CLOSED pure-cap | 3.01/14.9, 2.62/13.5; need entry edge first | 2026-10-06
- `oc_manualshallow` | shallow rungs | CLOSED | no row passes base; best 3.73 | 2026-10-05
- `oc_manualtsmom` | +TSMOM 0.25x overlay | CLOSED | 3.90 (+0.17) but DD worse 5/5 (19.33) | 2026-10-06
- `v335/daily` | daily MANUAL cadence | CLOSED | 1.17-2.09 (D00:60 1.165 .. D12:5 2.091) vs 4h 3.01; book needs 4h | 2026-10-03

## 9. Data sources tried (all walk-forward; do not re-add as members without new evidence)

- Whale perp flow W2/O1 KEPT; spot flow, market-wide flow, Bybit cross-venue, OKX (deferred incomplete), Bitfinex (11% pool), order-book depth sizing, TV indicators in A/B KEPT, microstructure blend (DD27/34), Coinbase premium D KEPT, DVOL/macro/COT/F&G/Korea/options-flow/Coinbase SOL-XRP dilute or hurt; aggTrades 1m store kept for future flow.
- Diagnostics: `oc_ddanat_g2` grind 2023-04-17..06-15 (~59d, longs -9..-11 + dip -7..-10/phase) DIAGNOSTIC; `oc_contrib` shallow+TP+longs earn, deep+stops carry DD; `oc_depthregime` deep loses every regime; `oc_margin` cross+5x runbook KEPT; `oc_kpi_g2`/`oc_d13robust`/`oc_mcdd`/`oc_underwater`/`oc_stresshist`/`oc_recent`/`oc_regimeexp` DIAGNOSTIC (no rule).
- Closed regimes/context: `oc_regime`, `oc_regimetrue`, `oc_fundregime`, `oc_macro`, `oc_expiry`, `oc_weekend`, `oc_eventblk`, `oc_volflush`, `oc_idea3/4/5/6/7/8/10`, `oc_optctx`, `oc_liqlive`/`oc_liq` infant — all CLOSED or DIAGNOSTIC-only.

## 10. Carry sleeve family (late-day 2026-10-06; base `oc_cashcarry` in §4 stays the rule)

- `oc_carryparity` | frozen carry prospective parity | DIAGNOSTIC | 144/144 contract; 1 stale-basis bug | 2026-10-06
- `oc_frontiercarry` | carry f0.25 on 80 frontier rows | REPORTING | +0.13pp, 0 stretch; G2+carry 5.533/16.78; headline +0.21/+0.13pp (5.533) is year-start conservative; expectation is oc_carrycompound 5.634/16.75/16.66 | 2026-10-06
- `oc_carryfar` | FAR 6-mo carry tenor | CLOSED (leader: not adopted; FAR ~= base per capital-time) | FAR +0.425geom but 2x capital-time ~= base | 2026-10-06
- `oc_carrytopup` | delivery-week carry top-up f0.125 | CLOSED | 5y -0.14% Bin/-0.10% Byb, 0/5y pos | 2026-10-06
- `oc_carryd13` | D13BF + frozen carry f0.25/0.50 | KEPT map | f0.25 5.104/DD14.85; f0.50 5.234/14.71 | 2026-10-06
- `oc_carrycombo` | BOT/MANUAL + locked carry f0.25/0.50 | REPORTING | G2 +0.00-0.01R/-0.13DD; MAN ~3.75 still <5; headline +0.21/+0.13pp (5.533) is year-start conservative; expectation is oc_carrycompound 5.634/16.75/16.66 | 2026-10-06
- `oc_carryfric` | carry under frictions S1-S5 | REPORTING | D13 base 5.104/14.85 only; G2 fails S1/S3 (conservative year-start); compounding [oc_carryfric2] G2+carry f=0.25: base 5.634, S1 4.780, S2 5.438, S3 4.806, S4 5.125, S5 5.111, no losing year; D13BF+carry base 5.198/14.82 | 2026-10-06
- `oc_linvinv` | same-expiry linear-vs-inverse >=3pp/yr f0.125 | CLOSED | 0 entered, max 2.55<3pp | 2026-10-06
- `oc_manualcarry` | honest MANUAL + frozen carry | CLOSED | best 3.993 <5; return never passes | 2026-10-06
- `oc_utamargin` | one UTA G2+carry f0.25/0.50 | KEPT f0.25 | f0.25 safe; f0.50 split-only | 2026-10-06
- `oc_utamargin2` | carry-short leverage 5/10/20x | DIAGNOSTIC | 10/20x IM-safe but f0.50 haircut-fail | 2026-10-06
- `carry_audit` | blind carry replication (COMPARISON.md only, no REPORT.md) | DIAGNOSTIC (FAIL numeric) | 20/25 basis + 25/25 ret miss; causality/fees/overlay PASS | 2026-10-06
- `oc_carryborrow` | carry f=0.5 with USDT borrow for the extra spot (10/15 %/yr APR) | CLOSED | base 5.569/5.424 vs 5.634; S1 4.696/4.550 vs 4.780; DD +0.2-0.35pp; keep f=0.25 | 2026-10-06
- `oc_carrymore` | same quarterly carry rule on BNB/SOL/XRP via Binance COIN-M (POST-HOC) | PARKED (not deployed) | +0.145 %/mo over BTC+ETH (G2 + carry all majors 5.771 vs 5.626, no new DD); peak 2.0x equity spot needs borrow; Binance account needed (Bybit lists BTC/ETH quarterlies only); funded size ~f 0.125 keeps ~+0.07 | 2026-10-06
- `oc_idea4_carrymax` | carry only the higher-basis coin (M1/M2) | CLOSED | dev -0.13, 5y -0.10 %/mo vs both coins, DD unchanged | 2026-10-07
- `oc_idea6_d13carry` | D13BF + concentrated carry f 0.50 (POST-HOC) | CLOSED | base 5.115/DD 14.71 but fails frictions and needs split capital; 8 %/mo unreachable (~2.9pp short) | 2026-10-07
- `oc_usdccarry` | Bybit USDC linear dated futures as the carry leg | CLOSED | no better than inverse (basis within +-0.6 pp/yr where comparable); gaps 2021-22 and 2025-26, none trading now; keep inverse quarterlies | 2026-10-07
- `oc_i2_tapecancel` | cancel dip bids on adverse tape (aggTrades) | CLOSED | C1 0/4, C2 1/4 dev years; dSum -0.40 / -0.31 vs gate +0.273; no engine run | 2026-10-07
- `oc_i2_spreadveto` | veto dip bids on wide-spread / thin-depth bars | CLOSED | fails the placebo gate (S2 -0.28 dev4 vs +0.273); no engine run | 2026-10-07
- `oc_i2_dvolveto` | veto dip bids on DVOL spikes (change) | CLOSED | removes winning dips: dev4 0/4, dSum5y -1.508 vs gate +0.273; no engine run | 2026-10-07
- `oc_i2_oiguard` | skip dip bids while open interest unwinds | CLOSED | fails the dip placebo gate (+0.273) on dev years; no engine run | 2026-10-07
- `oc_idea1_kellyrung` | fractional-Kelly dip rung sizing under budget | CLOSED | best K2 dev4 5.54 / 5y 5.35 but full-path DD 21.79 > 20, recent year 4.64; worse than G2 (+carry) on return and DD | 2026-10-07
- `oc_idea2_dipstop` | fixed per-coin dip stops on G2 (4-phase engine) | CLOSED | +0.005 %/mo vs G2, folds 0/3, slip stress erases it | 2026-10-07
- `oc_idea5_manualrest` | MANUAL brackets resting to the 4h close (H1) / doubled dips (H2) | CLOSED | H1 +0.29 vs 60-min baseline but -0.07 vs running M5_human; H2 DD 21.3/25.2 > 20; MANUAL still ~1.3 pp short of 5 %/mo | 2026-10-07
- `oc_idea3_carrytier` | carry f by basis tier (POST-HOC) | CLOSED | T1 +0.07 dev4 but needs 1.5x equity spot (borrow); T2 (cap 0.25) -0.02; keep flat f 0.25 | 2026-10-07

## 11. Late-day dip / book screens (2026-10-06)

- `oc_tsmomcombo` | TSMOM sleeve on frontier rows (post-hoc) | CLOSED | +R but DD worse 48/50; no official stretch (D13BF@0.10 grid DD14.49, official 15.42) | 2026-10-06
- `oc_tsmomvar` | 5-coin + 90d-long-only TSMOM variants | CLOSED | DIV 0/5 both | 2026-10-06
- `oc_tsmom_official` | TSMOM on official metric | CLOSED | no stretch; D13BF@0.10 DD15.42>15 | 2026-10-06
- `oc_depthtilt` | depth-tilted sizing k/2.5 renorm sum5.0 (post-hoc) | CLOSED | 3/5+5/5+4/5 dSum -0.066<+0.273 | 2026-10-06
- `oc_bidttl` | 2-hour dip-bid TTL 16..135 | CLOSED | 0/5, dSum -1.339 | 2026-10-06
- `oc_stoptf` | stop timeframe S15/S1 vs close5 | CLOSED | S15 4/5+2/5, S1 2/5+5/5 | 2026-10-06
- `oc_expirydip` | expiry-day extra 5sg rung | CLOSED | 5/5+5/5 but dSum +0.0164<+0.273 | 2026-10-06
- `oc_usdtdip` | USDT-premium dip-size tilt | CLOSED | dSum +0.047<+0.273 gate | 2026-10-06
- `oc_discsniper` | spot-perp discount sniper z<-2 | CLOSED | 0/5, 5y -0.529, p13.3 | 2026-10-06
- `oc_marktrig` | mark-trigger stops close5/backstop | CLOSED | sum 4/5 but tails 2/5 | 2026-10-06
- `oc_b1shape` | corr-aware sizing shapes 1/(1+n) | CLOSED | keep S1; 5498 fills | 2026-10-06
- `oc_c2ic` | C2-fix XS info test | CLOSED | cand 2/4y, pooled corr 0.41, NO | 2026-10-06
- `oc_qbasis` | quarterly-basis z terciles | CLOSED | book Hi-Lo wrong way 0/5 | 2026-10-06
- `oc_kellydip` | analytical Kelly/DD sizing | DIAGNOSTIC | Kelly f* 0.5-6.5; budget-scale needed | 2026-10-06
- `kelly` | distributional Kelly/mean-var rung sizing | PROMISING screen | V2 +4.720, Sharpe up | 2026-10-06
- `oc_idea1` | late-fill fast-TP 0.5sg | CLOSED | D 1/5, LOO 0/5 | 2026-10-06
- `oc_idea10` | 1h-confirmation dip filter | CLOSED | 2/5, LOYO 0/5 | 2026-10-06
- `oc_idea4` | funding-surprise dip filter | CLOSED | sign 5/5 but tail 3/5, ret 0/5 | 2026-10-06
- `oc_idea5` | premium-gated book flips | CLOSED | 25 fires, dDD 1/5 | 2026-10-06
- `oc_idea6` | basis-momentum dip throttle | CLOSED | gain 2/5 tail 1/5 | 2026-10-06
- `oc_idea7` | VRP-regime budget dial | CLOSED | gain 4/5 tail 2/5 | 2026-10-06
- `oc_idea8` | dominance-momentum dip throttle | CLOSED | gain 4/5 tail 3/5 | 2026-10-06
- `oc_bookvol` | book vol-target variants | CLOSED | all FAIL Sharpe bar | 2026-10-06
- `oc_usdtshort` | USDT short-leg tilt | CLOSED | P&L 5/5 p99.6 but DD 3/5 | 2026-10-06
- `oc_rlbear` | V2-lite bear-flag dip retrain | CLOSED | sum 3/5 DD 2/5 | 2026-10-06
- `oc_agentens` | 5-seed ensemble vs deployed seed | CLOSED | ENS>=S0 2/5 | 2026-10-06
- `oc_manual2coin` | MANUAL SOL+XRP-only brackets (IDEAS2#8) | CLOSED | 3.24/17.1 and 3.39/24.3 vs M5 3.73/17.8 | 2026-10-06
- `crashrisk` | market-state crash-risk dial | CLOSED | Step4 FAIL, DD -0.4pp max | 2026-10-06

## 12. Late-day diagnostics / methods / ops (2026-10-06)

- `oc_oos12d` | 12d OOS dip-only 2026-09-24..10-06 | DIAGNOSTIC | 14 exits win85.7%, in-band, no gate claim | 2026-10-06
- `oc_quietmonth` | quiet-start diagnostic | DIAGNOSTIC | low 4.87/norm 7.55/high 3.64 next-mo | 2026-10-06
- `oc_spreadcost` | half-spread taker overlay from live topbook | DIAGNOSTIC | -0.28 haircut, DD ~same | 2026-10-06
- `oc_planparity` | live-plan parity | DIAGNOSTIC | PARITY 0 mismatches | 2026-10-06
- `oc_outage` | outage overlay weekly2h/monthly6h/quarterly24h/advers10h | DIAGNOSTIC | routine 1-2.5% cost; flush-outage tail only | 2026-10-06
- `oc_crash2020` | G2 dip-only replay COVID/2021 windows | DIAGNOSTIC | COVID -16.1% mix/-21.8% phase; cap inert | 2026-10-06
- `oc_crashfreq` | one-bar dip crashes >=3% | DIAGNOSTIC | 82 bars; -15% once 2024-01-03 | 2026-10-06
- `oc_ddanat17` | s=0 DD anatomy | DIAGNOSTIC | 9.9-18.5 DD; dip 70-72% in 2/5 | 2026-10-06
- `oc_ddanat4p` | 4-phase gate-DD anatomy | DIAGNOSTIC | gate=2024-01-03 async cascade | 2026-10-06
- `oc_bookic` | book loss-carrier anatomy | DIAGNOSTIC | 5y +2.2787, no losing year gross | 2026-10-06
- `oc_ladderfill` | fill timing + edge share | DIAGNOSTIC | n21389 win0.687 +17.76bps | 2026-10-06
- `oc_seedengine` | honest-expectation seed replay G2 | DIAGNOSTIC | 5y 5.343-5.430, no losing year any seed | 2026-10-06
- `oc_collectors` | liq+topbook collector health | DIAGNOSTIC | healthy 9h, 0 gaps, 326k rows | 2026-10-06
- `oc_kpi_d13` | D13 user-goal KPI + G2 neighbour | DIAGNOSTIC | D13 19.5x, DD14.86, win all 0.657 | 2026-10-06
- `oc_clockluck` | hourly vs half-hour clock luck | DIAGNOSTIC | hourly 6.92/4.83/5.59/3.10; half 5.37/4.64/3.19/4.01 | 2026-10-06
- `oc_edgedecay` | G2 edge-decay diagnostic | DIAGNOSTIC | slope +0.07 CI incl 0; no decay | 2026-10-06
- `oc_phase8` | 8-clock 30-min screen G2 | CLOSED | 8-mix 4.96/17.32 vs 4-mix 5.41/16.82 | 2026-10-06
- `oc_plateau` | plateau around D17BF | DIAGNOSTIC | ref 5.425/18.33/16.90; F30 DD22.1 breach | 2026-10-06
- `oc_plateau2` | plateau around G2 TP/stop/cap | DIAGNOSTIC | ref 5.410/16.91/16.82; within 0.3R/1.5DD | 2026-10-06
- `oc_saturation` | dip-size saturation anatomy | DIAGNOSTIC | D20 5.894/21.21 G2K20 5.874/17.79 saturate | 2026-10-06
- `oc_capscale` | G2 capital scaling A2000-25000 | DIAGNOSTIC | min 5000 USDT; R/DD A-const 5.41/16.82 | 2026-10-06
- `oc_papercmp` | paper bots vs plan_v376 parity | DIAGNOSTIC | bot -0.08pp, 2 entries | 2026-10-06
- `oc_lots` | Bybit lot/min-notional feasibility | DIAGNOSTIC | >=99% only at A20000 | 2026-10-06
- `oc_topbook` | live top-of-book loader (no outcomes) | DIAGNOSTIC | patchy but loadable, 9910 1m rows | 2026-10-06
- `oc_deepcheck` | TRUE vs FIFO deep-rung reconciliation | METHOD | deep TRUE +38.2 mix% | 2026-10-06
- `oc_signedfunding` | signed funding side row + NaN fix | METHOD | gate exact; side row only | 2026-10-06
- `bot_bookgap` | book gap + exit-count fix | KEPT fix | plan-divergence; dust fixed | 2026-10-06
- `bot_parity_adopt` | --adopt-fresh book-gap test | CLOSED | book 19/83, gap -0.0352; adopt +1 only | 2026-10-06
- `ops_liveparity` | live paper-bot parity vs Binance 1m | DIAGNOSTIC | eq ~4999.8, 0 dip/3-5 book fills | 2026-10-06
- `ops_enginespeed` | engine_user speed + engine_fast proof | DIAGNOSTIC | 1.88x/1.57x bit-exact | 2026-10-06
- `ops_kaggleengine` | generic Kaggle CPU engine bundle | DIAGNOSTIC | 6/6 pass, G2 5.41/16.91/16.82 | 2026-10-06
- `r2_4p_robust5` | R2-4P friction robustness S1-S5 (no PLAN) | DIAGNOSTIC | base 4.820/DD25.05/23.08; S1/S4/S5 breach | 2026-10-06
- `kronos` | Kronos zero-shot forecasts | DIAGNOSTIC (leak) | BOOK IC neg; DIP V1 +2.52 (leak caveat) | 2026-10-06

<!-- consistfix 2026-10-06: §4 oc_cashcarry + §10 oc_frontiercarry/oc_carrycombo appended headline +0.21/+0.13pp (5.533) is year-start conservative; expectation oc_carrycompound 5.634/16.75/16.66 (no number change); §10 oc_carryfric kept conservative numbers, added oc_carryfric2 compounded (G2+carry f=0.25 base 5.634, S1 4.780, S2 5.438, S3 4.806, S4 5.125, S5 5.111, no losing year; D13BF+carry base 5.198/14.82). Sources re-checked: oc_carryfric2 REPORT, oc_carrycompound REPORT (5.634), oc_carryfric REPORT (5.533). -->

<!-- docs_closedtidy 2026-10-07: moved 6 appended bullets into §10 table, numbers verified verbatim against REPORT.md (no fixes): oc_carryborrow (REPORT base 5.569/5.424 vs 5.634, S1 4.696/4.550 vs 4.780, DD 16.93/17.10 vs 16.75 = +0.18/+0.35pp), oc_carrymore (REPORT 5.771 vs 5.626, +0.145 extra, peak 2.0x spot, ~+0.07 = half extra at f0.125), oc_idea4_carrymax (REPORT dev -0.126, 5y -0.103, DD identical), oc_idea6_d13carry (REPORT 5.115/14.71, 8-5.115=2.885 ~=2.9 short), oc_usdccarry (REPORT basis diff -0.0060..+0.0032 = +-0.6pp/yr, gaps + zero Trading), oc_idea3_carrytier (REPORT dev4 +0.071/-0.020, peak spot 1.50x). -->

## 11. 2026-10-07 wave

- `oc_relflush` | size the flush overshoot (R1 x1.5/x0.75, R3 smooth tilt) | CLOSED | R1 2/5 dSum -0.109 (7.610 vs 7.718); R3 2/5 -0.152 (7.566 vs 7.718); control R2 4/5 +0.291 but DD fails 4/5 (full DD 3.13->3.92) [research/tournament/oc_relflush/REPORT.md] | 2026-10-07
- `oc_tailhedge` | monthly 15-25% OTM BTC puts always-on (h=1/2, m=0.15/0.25) on G2/G2K20 | CLOSED | best row G2K20+H(m0.25,h1.0) dev4 4.855 vs G2 5.601, DD 20.63/24.46 vs 16.91/16.82; last year 3.381/17.89 vs G2 4.648/12.90 [research/tournament/oc_tailhedge/REPORT.md] | 2026-10-07
- `oc_ripcont` | buy-the-first-pullback-after-a-rip long sleeve C1 k=2.0 / C2 k=3.0 | CLOSED | C1 sum -0.5692 DD 0.031; C2 (chosen) sum +0.1762 DD 0.011; recent C2 n=248 mean +2.41bps sum +0.0597, below +5bps [research/tournament/oc_ripcont/REPORT.md] | 2026-10-07
- `oc_manualsplit` | MANUAL split-TP brackets H1 (0.75/1.5) / H2 (0.5/1.0) vs M5_human | CLOSED | M5 R5 3.728; H1 3.489/fullDD 19.80; H2 (pick) 3.508/fullDD 17.24, book win .6497; gap to floor 1.492pp [research/tournament/oc_manualsplit/REPORT.md] | 2026-10-07
- `oc_stablegate` | stablecoin net-creation impulse: book gate G1/G2S + dip dial D1/D2 | CLOSED | book G1 dev4 5.537 vs G2 5.601 vs CTRL 5.699; G2S 5.555 worst 2.403; dip D1 dSum +0.058, D2 +0.450 but DD ok only 3/5 [research/tournament/oc_stablegate/REPORT.md] | 2026-10-07
- `oc_putwrite` | weekly cash-secured put-write BTC+ETH P1 z1.0 / P2 z1.5 / P3 z2.0 / P4 spread | CLOSED | P1 0.414 (1 losing yr); P2 -0.174; P3 -0.156 (fallback pick); P4 -2.054; P3 recent -0.115/DD1.57; G2+put f0.25 5.371 (-0.039) [research/tournament/oc_putwrite/REPORT.md] | 2026-10-07
- `oc_vrpgate` | ex-ante vol-premium gate (POST-HOC) on r=0.87 weekly straddle | CLOSED | overlay dev4 G2 5.601/2.588/16.91; +R087 5.740/3.578/17.22 (winner); +G1 5.643/3.115/17.92; +G2gate 5.722/3.129/16.91; recent R087 4.946/15.20 vs G2 4.648/12.90 [research/tournament/oc_vrpgate/REPORT.md] | 2026-10-07
- `oc_vrp_family` | weekly short-vol sleeve family (straddle/strangle/robust repricing) | CLOSED family, NOT DEPLOYED | headline +1pp was DVOL pricing bias (traded 7d ATM IV ~0.87x DVOL); consistent repricing: standalone loses, overlay +0.14pp at r0.87, -0.35 at r0.80; only remaining evidence = prospective Bybit paper ledger `scripts/straddle_paper.py` [family REPORTs + docs/opencode/STRADDLEPAPER_20261007.md] | 2026-10-07
- `oc_vrpstraddle` | delta-hedged short ATM straddles V1 hedged / V2 naked / V3 4w | CLOSED (NOT DEPLOYED) | V2 dev4 3.441/worst -0.165/DD25.82; overlay f0.25 5y 6.408/DD16.10; recent V2 4.232/19.57; otmiv 6.522/1.508/25.71 (DD disease kept) [research/tournament/oc_vrpstraddle/REPORT.md] | 2026-10-07
- `audit_vrpstraddle` | blind replication of V2 + overlay f=0.25 | PASS-WITH-NOTES | overlay exact (full-path DD 16.01/15.20/16.01); standalone R gaps 0.15-0.18pp 3/4y, DD -1.64 in 2022; causes = :59/:00 convention + SL 1.0x/1.05x; no look-ahead, no accounting hole [research/tournament/audit_vrpstraddle/COMPARISON.md] | 2026-10-07
- `oc_vrprobust` | pricing break-even k sweep + traded 7d ATM IV/DVOL (leader note; worker stopped after tmp/A,B,C,C4,D.json) | CLOSED (NOT DEPLOYED) | k0.97 overlay dev4 6.566/4.365/16.10 recent 5.780/13.70; k0.88 5.919/3.783/16.76; k0.80 5.337/2.934/17.48; traded IV/DVOL n61 mean 0.868 median 0.862 p10 0.786 p90 0.941 [research/tournament/oc_vrprobust/REPORT.md] | 2026-10-07
- `oc_vrpconsistent` | consistent repricing r=1.0/0.87/0.80 | CLOSED (NOT DEPLOYED) | R087 overlay f=0.25 dev4 5.740/worst 3.578/DD17.22 (+0.139 vs G2); R080 5.249 (-0.352, over the 0.3 bar); winner stays R100; recent R087 4.946/15.20 vs G2 4.648/12.90 [research/tournament/oc_vrpconsistent/REPORT.md] | 2026-10-07
- `oc_vrpstrangle` | short OTM strangle on traded OTM IV Z1 z0.5 / Z2 z1.0 | CLOSED (NOT DEPLOYED) | Z1 3.373/DD22.21 (DD breach); Z2 (chosen) 0.632/DD14.01; recent Z2 1.017/3.43; G2+Z2 f0.25 5y 5.601/DD16.50 [research/tournament/oc_vrpstrangle/REPORT.md] | 2026-10-07
- `oc_presample` | G2 dip-sleeve replay on 2017-2020 pre-sample (spot 1m) | DIAGNOSTIC / KEPT (sleeve stays, no weight change) | no losing year on 4-phase mean; 2018 2.50 %/mo DD 8.4; 2019 0.48/DD11.3; Y2017 10.71/5.04; Y2020p 0.27/17.52 (s1 COVID DD 24.5) [research/tournament/oc_presample/REPORT.md] | 2026-10-07
- `oc_paperpower` | paper-evidence power (10d/30d block bootstrap, 5000 paths) | DIAGNOSTIC | 8w weak (zero-edge PASS 38.3%, -1%/mo 32.0%); 12w 30.8%/25.0%; 26w 13.7%/8.1% (recommended); 52w 2.5%/1.0% [research/tournament/oc_paperpower/REPORT.md] | 2026-10-07
- `data_hlfunding` | Hyperliquid funding history + HL-vs-Binance descriptives | PARKED (2023-05+ only) | overlap corr BTC 0.65 ETH 0.61 SOL 0.67 BNB 0.61 XRP 0.65; screen on overlap + paper only, never dev4 [research/tournament/data_hlfunding/REPORT.md] | 2026-10-07
- `oc_ideascan3` | new-data + new-idea scan B1-B10 (no backtests run) | KEPT scan | ranked B1>B3>B8>B4>B2>B10>B7>B6>B5>B9; B1 screen + B3 engine first [docs/opencode/IDEAS_20261007c.md] | 2026-10-07
- `ops_bybitoptions` | Bybit options executability (public GETs + help docs) | DIAGNOSTIC | bot FEASIBLE (Pro/UTA-Cross, hourly buy-back loop); human POSSIBLE but WEAK; cross BTC ~0.30% ETH ~1.40%; fees maker 0.02% taker 0.03% [docs/opencode/BYBIT_OPTIONS_20261007.md] | 2026-10-07
- `bot_exitcancel_fix` | market-exit same-cycle cancel bug (since 1c0469a) fixed in cb14cb7 | KEPT fix | WITH fix exits complete in <=2 cycles, 0 bare pieces; WITHOUT 3 pieces BARE indefinitely; 10 regression tests pass [docs/opencode/BOT_EXITSOAK_20261007.md] | 2026-10-07
- `ops_paperfix` | exit-bug + outage paper distortion 2026-10-06 20:10..10-07 07:35 | DIAGNOSTIC | gaps paper -7.89 (-0.16%), d17bf -15.06 (-0.30%), d13bf -11.54 (-0.23%), d17bfg2 -15.06 (-0.30%), g2k20 -17.57 (-0.35%), d17bfg2c -14.05 (-0.28%), g2k20c -14.45 (-0.29%); window excluded from main scorecard [docs/opencode/PAPERFIX_20261007.md] | 2026-10-07
- `ops_scorecardfix` | scorecard correction window + 2 carry runners | KEPT | window 2026-10-06T20:10..2026-10-07T07:35 UTC; new bot_paper_d17bfg2c (expect 5.634/16.75), bot_paper_g2k20c (expect 6.097/17.64); corrected paper -0.037, d17bfg2 -0.027, g2k20c -0.469 [docs/opencode/SCORECARDFIX_20261007.md] | 2026-10-07
- `ops_keepalive` | keepalive scheduled tasks (owner-run) | KEPT | `AlphaLabRunnersKeepAlive` every N min (`restart_all -Only bots` + `-Only carry`) + backend watchdog; ExecutionTimeLimit = 0 [docs/opencode/KEEPALIVE_20261007.md] | 2026-10-07
- `ops_oosweek2` | OOS week 2 forward evidence | DIAGNOSTIC | window 09-30..10-06 +1.995% DD 0.766% win 90.0% (10 exits) pct 72.7; Binance fetch 404, no new window; paper d17bfg2 +0.637% pct 69.8 [docs/opencode/OOS_WEEK2_20261007.md] | 2026-10-07
- `oc_kronoshidden` | Kronos dip tilt on post-release year (dev = upper bound, recent year = verdict) | RUNNING | PLAN pre-registered 2026-10-07; Kronos-small S=64, variants REF/K1/K2/CTRL [research/tournament/oc_kronoshidden/PLAN.md] | 2026-10-07
- `ops_deribitstrike` | Deribit strike-level fetch (weekly-entry pricing) | RUNNING | BTC samples 2021-06/2023-03/2025-06 corr 0.9998/0.9997/0.9992 [research/tournament/oc_deribitstrike_BTC/REPORT.md] | 2026-10-07
- `bot_soakinv` | paper invariance soak | RUNNING | probes under research/diagnostics/bot_soakinv/tmp/ | 2026-10-07
- `oc_vrpstrike` FULL (all months 2021-01..2026-09, real Deribit traded strike IV) | weekly naked ATM straddle priced from traded IV | CLOSED (definitive) | standalone dev4 mean -0.99 %/mo, 3 losing years, DD 35.9; IV - RV negative every year; overlay on G2 f 0.25 dev4 5.41 vs 5.60 (-0.19 pp), DD 18.19 vs 16.91 | 2026-10-07
- `oc_kronosmanual` / `oc_kronosbookvol` | Kronos ex-ante corr proxy for MANUAL dips / Kronos forecast-vol book scaling | CLOSED | MANUAL R5 3.44/3.40 vs 3.73; book vol clean year 4.56 vs G2 4.65 and trailing control 4.60, 5y DD 18.67 | 2026-10-07
- `oc_kronoshidden` K2 | Kronos-small dip tilt x1.25/x0.75 on -low1 outer quintiles | PROSPECTIVE LOG ONLY | post-release year 4.80 vs G2 4.65 / control 4.65, DD 12.10 vs 12.90; dev worst year 2.47 < 2.59; scripts/kronos_shadow.py logs features hourly | 2026-10-07
- `oc_presample2` | dip design choices replayed on never-used Binance spot 2017-10..2020-08 (one knob per row) | DIAGNOSTIC (generalisation PASS) | B1 corr sizing halves DD in all 4 legs (no-B1 has the only losing year, 2020 -0.88 / worst-phase DD 42.9); KD13<G2<KD20 monotone in return AND DD; cap inert; TP1.5 more return but more DD (frontier); touch stop beats close5 only in COVID 2020 | 2026-10-07
- `oc_gex` | dealer-gamma (GEX) LEVEL proxy from Deribit strike-level taker flow vs dip-rung outcomes | CLOSED | right sign 2/4 dev years, GEXn vs next-24h realised vol positive (wrong sign), no expiry effect; tilt not scored per plan | 2026-10-07
- `oc_gexchange` | 24 h change of the dealer-gamma proxy vs dip rungs | CLOSED | hypothesised sign 2/4 dev years; GEX closed (level and change) | 2026-10-07
- `oc_ivterm` | 7d ATM IV / DVOL term structure (inversion = acute stress) vs dips and book | CLOSED | high TS worse dips 3/4 years but 2022 flips; book IC < 0.11, no stable sign | 2026-10-07
- `oc_optflow` | informed option flow (short-dated OTM taker / block, strike-level) vs book returns and dips | CLOSED | pooled IC <= 0.009, signs flip; no candidate | 2026-10-07
- `oc_hlspread` | Hyperliquid-minus-Binance funding disagreement book throttle (2023+ only) | CLOSED | +0.40/+0.28 2023/24 with more DD, -0.07 on the year scored once; IC ~0 | 2026-10-07
- `oc_liqfirst` | liquidation / top-of-book collector audit | DIAGNOSTIC | coverage 63 % since 10-04 (5 backend gaps); research-grade earliest ~2027-01-07 with no further gaps | 2026-10-07
- `oc_paperparity2` / `oc_oosweek3` | paper vs research after the bot fixes; OOS week 3 | DIAGNOSTIC | parity 0 mismatches (quiet window - rerun with more fills); G2 OOS 7 d +1.62 % pct 65.7 | 2026-10-07
- `oc_presamplebook` | TV-indicator-only 7-day pooled HGB member, walk-forward 2019-2025 incl. never-used spot 2019-2020 | DIAGNOSTIC (negative) | out-of-sample IC ~0 in all 7 years (train IC 0.26-0.46: overfit); G2's book return is NOT explained by this signal family -> attribution running (oc_bookattrib) | 2026-10-07
- `oc_bookattrib` | attribution of the deployed G2 book: beta vs timing, block-shuffle placebo, book-only engine | DIAGNOSTIC (reassuring) | timing positive all 5 years incl. bear years (2021 +3.25, 2022 +1.82 %/mo gross), placebo pct 96.8-100, market beta 0.05-0.14; book-only net 2.53 %/mo (2021 0.59), DD 18.96 > G2 16.82 (dip sleeve diversifies); bear filter net-negative outside 2021 (not acted on: would be tuning) | 2026-10-07
- `oc_memberdrop` | G2 without the whale-flow member / without the Coinbase-premium member / flow feed frozen 72 h x10 per year | DIAGNOSTIC (runbook) | members redundant: dev4 +0.01 / +0.02 pp, no losing year, full-path DD +0.5; 3-day flow outage cost ~0 (+-25 bps per episode, sign flips) -> a stale feed is not a stop-trading event | 2026-10-07
- `oc_nativeclock` | own fresh book signals for clocks 1-3 (they trade a 1-3 h stale forward-filled book) | CLOSED (not worth the rebuild) | not executable (per-anchor models not persisted), but oc_bookattrib per-phase TIMING is equal across phases (phase 0 vs 1-3 within +-0.2 pp, no consistent sign) -> staleness costs ~nothing; phase-0 engine advantage is dip/clock luck | 2026-10-07
- `oc_altdipb1` | G2 dip ladder with B1 on DOGE/ADA/TRX (research only) | CLOSED (frontier) | ALT8 dip sum +25 % 5/5 years but DD worse 5/5; ALT3 corr 0.57 with the majors sleeve = more correlated exposure | 2026-10-07
- `oc_coinattrib` | per-coin attribution of book timing and dips | DIAGNOSTIC | no coin carries most years, but spikes: XRP 52-55 % of book timing in 2022/2024, SOL 63 % / XRP 71 % of dips in 2021/2022; carrier rotates -> keep all 5 coins | 2026-10-07
- `oc_staleness` | book member skill vs model age (frozen at 2021/2022/2023 cuts vs yearly retrain, 24 months) | DIAGNOSTIC (ops) | no monotonic decay; skill is regime-driven (same quarter same sign for old and new models); fresh - stale IC +0.013 (A) / +0.002 (D), noise level -> yearly retraining is sufficient for live | 2026-10-07
- `oc_presampleflow` | SPOT-built whale-flow / Coinbase-premium member families, 7-day label, 2019-2025 incl. pre-sample | DIAGNOSTIC (inconclusive for the deployed book) | OOS IC ~0 in 20/21 variant-years incl. 2021-2024 (train IC 0.26-0.56) -> the spot/7-day rebuild lacks skill, while the deployed perp-flow book shows timing (oc_bookattrib); horizon/dimension check running (oc_bookichorizon) | 2026-10-07
- `oc_lit_fhlh` | first-half-hour -> rest-of-day momentum book gate (lit. H3) | CLOSED | M1 passed dev4 (+0.17, mostly exposure; +0.02 vs control) but most recent year 3.89 vs G2 4.65 | 2026-10-07
- `oc_lit_xs` A1 | Amihud illiquidity cross-sectional book tilt x(1+0.25z) (lit. H4) | CONDITIONAL / NOT DEPLOYED on Bybit (blind audit PASS exact; jitter 4/4, placebo pct 93, beats static coin tilt +0.64, frictions S1-S4 > 0; BUT S5 Bybit prices: gain -0.005 and full-path DD 21.32 > 20 - it overweights BNB/XRP, illiquid on Bybit) | dev4 5.844/W 2.798/DD 16.81 vs G2 5.601/2.588/16.91, +0.18 vs exposure control, 4/4 dev years; most recent year once 4.750/DD 11.14 vs 4.648/12.90; 1 of ~20 variants screened that day (multiple-testing caveat) | 2026-10-07
- `oc_lit_position` | OI-level throttle (H6) / BTC MVRV-z cycle gate (H8) | H6 CLOSED; H8 M1 NOT ADOPTED as a signal - oc_mvrvmech: isolated the gate HURTS the book (book-only 2.461 < 2.531); its engine gain is a governor interaction (smaller book -> phase governor avoids a shutdown, e.g. phase 3 early 2024); blind audit PASS (vintage caveat). Was robust: 4/4 jitters > G2, all frictions > G2, gain over 2 episodes E2 2023 + E4 2024, LOEO still > G2; never fires in the most recent year) - mechanism check + blind audit running | M1 dev4 6.192 / DD 16.26 vs 5.601 / 16.91, beats control; A1+M1 post-hoc 6.238/2.798/16.08 | 2026-10-07
- `data_binanceopt` | Binance options IV for BNB/SOL/XRP | CLOSED | only 5 months of 2023 for BNB/XRP, nothing for SOL; Binance BTC/ETH BVOL ~ Deribit DVOL (corr 0.99) | 2026-10-07
- `oc_k2placebo` | timing placebo for the Kronos K2 dip tilt | DIAGNOSTIC (supports K2) | post-release year normalised gain significant: timing pct 97.2, block pct 98.7 (2021 no skill); K2 paper runner being built (bot_k2flag) | 2026-10-07
- `ops_carrygap` | why G2+carry paper runners lagged their twins | FIXED (bot/paper.py 63d65bd) | paper exchange never marked the dated carry short (no resting order -> no kline -> valued 0); after the fix d17bfg2c equity ~5,039 vs twin ~5,030 | 2026-10-07
- `oc_lit_calendar` | turn-of-month (H1), overnight session (H2), halving clock (H7) book gates | CLOSED | dev4 picks were mostly exposure cuts (V1 +0.02 vs control); V1 most recent year 4.304 vs G2 4.648 / control 4.374 | 2026-10-07
- `oc_governor` | per-phase drawdown governor vs looser bands / pooled-account governor | CLOSED (frontier) | live also uses per-phase governors (matches research); only phase 3 ever hits g=0 (2024-03, 165 bars); GV1/GV2 (0.25/0.30 zero) dev4 6.11/6.16 at DD 19.1-19.3; GV3 pooled 6.107/W 2.830/DD 17.89, recent 4.824 (+0.18), 5y 5.849/full 17.50 = same frontier point as G2K20 (5.87/17.79) -> a risk dial, not a frontier move | 2026-10-07
- `oc_ablation` | leave-one-layer-out of G2's risk layers (4-phase account) | DIAGNOSTIC (design confirmed) | B1 (off: maxDD 23.65), close5 (touch: -0.38 / +1.7 DD), cap (off: -10% gap loss 32.9 -> 60.9 %), governor (off: DD 20.04) all earn their keep; vol target = return/DD dial (off +0.86 dev4 but worse bad years 2.39 < 2.59 and +1.0 DD); bear x0.5 filter ~0 everywhere (simplification candidate, needs its own pre-registration) | 2026-10-07
- `oc_amihudbybit` | venue-consistent Amihud tilt (Bybit volumes) scored on Bybit prices (post-hoc) | CLOSED | AB1_S5 dev4 5.039 vs G2_S5 4.994 (+0.045) but full-path DD 22.48 > 20; Amihud family closed for the Bybit account | 2026-10-07
- `oc_bookichorizon` | horizon / dimension of the deployed book's skill (cached member predictions) | DIAGNOSTIC (checked by oc_horizonfix: corrected forward yardstick changes the deployed book's h=1 IC by only -0.001..-0.004 -> conclusion stands) | skill lives at h = 1..18 four-hour bars in the TIME-SERIES dimension: pooled IC +0.02..+0.04, 4/4 dev years for all six members (A/Aq/B/Bq/D/Dq), recent year +0.036 (h=1); 7-day h=42 flips in 2022; XS 2-3x smaller -> the 7-day pre-sample rebuilds measured the wrong horizon (re-score running: oc_presampleshort) | 2026-10-08
- `oc_bybitgap` | decomposition of G2's Bybit-price gap (dev4 5.601 -> 4.994, 5y 5.410 -> 4.883, full DD 16.82 -> 18.09) | DIAGNOSTIC | book execution ~identical (fills +2/+14, prices <1 bp); gap rides the dip ladder (-25/-57 fills, -34/-59 TPs, more stops) amplified by deployment sizing; diffuse across coins (BNB basis -3.6 bp but +39 % mix P&L); no venue fix pre-registered (XRP routing, BNB exclusion, TP shave all refuted by existing numbers) -> budget ~-0.5 pp/month for Bybit live | 2026-10-08
- `oc_k2bybit` | Kronos K2 dip tilt under frictions S1-S5 incl. Bybit prices | LEAD (strongest new signal; blind audit audit_k2 PASS-WITH-NOTES, exact; paper runner paper_d17bfg2k2 live; robust criterion still prefers G2 on the 2021 worst year -> prospective paper decides) | K2 - REF > 0 in all 6 frictions: dev4 +0.08..+0.27, clean year +0.10..+0.20, 5y +0.09..+0.26; full-path DD lower in every row (S5 17.41 vs 18.09); only weakness 2021 (Kronos no skill that year, worst dev year 2.469 < 2.588) | 2026-10-08
- `oc_presampleshort` | re-score of stored pre-sample member predictions at h = 1..42 | CLOSED (LEAK CONFIRMED by oc_horizonfix: corrected h=1 TV IC -0.027..+0.008, the +0.13..+0.18 was 100 % bar-t leak in the yardstick; FLOW/PREMIUM/BLEND ~0 either way) | TV-only IC +0.13..+0.18 at h=1 in ALL 7 years decaying to 0 at h=42 = signature of a contemporaneous-return leak; FLOW / PREMIUM / BLEND ~0 | 2026-10-08
- `oc_k2carry` | account-realistic G2 / K2 with carry on Binance and Bybit prices | DIAGNOSTIC (planning) | Bybit S5 5y: G2+carry 5.111 / full DD 17.93; K2+carry 5.199 / 17.26 (K2 upper bound on dev); Binance: 5.634 / 16.66 and 5.801 / 15.93 | 2026-10-08
- `oc_k2manual` | Kronos K2 multiplier on the MANUAL bracket dip rungs (a human scales sizes at the bar open), M5_human reproduced bit-exact | CLOSED | KM_K2 5y 3.840 vs M5_human 3.728 (+0.112 of the 1.272 gap), dev4 +0.147 but worst dev year 0.661 < 0.847 (2021), post-release year 3.968 vs 3.994 (no gain); timing over CTRL +0.249 real but too small; MANUAL still lacks entry edge | 2026-10-08
- `oc_horizonfix` | contemporaneous-return leak check of the IC yardstick open[t+h]/open[t] (oc_presampleshort, oc_bookichorizon) | DIAGNOSTIC (resolved) | rows at T are known at T's close, so the old target held bar T's own move; corrected y from open[T+1]: presample TV h=1 IC +0.13..+0.18 -> -0.03..+0.01 (pure leak), FLOW's weak h=1 trace also vanishes; deployed book IC unchanged (h=1 dev +0.017..+0.018, recent +0.033); synthetic test proves old IC 0.9998 vs corrected -0.002 for a same-bar feature; strategies/engine unaffected (they trade from o[T+1]) | 2026-10-08
- `oc_kronosfeat` | which Kronos-small features carry dip / book information (descriptive; dev = upper bound, post-release year = clean, nothing selected) | DIAGNOSTIC | dip replica exact (7.718); clean year: low1 vs rung outcome pooled Spearman +0.043 NS (K2's engine gain rests on the quintile tails: clean-year low1 Q4 - Q0 rung mean +0.0023 in K2's direction, but the same tail spread is -0.0061 / -0.0037 in Y1 / Y2 and +0.0033 / +0.0023 in Y0 / Y3 -> unstable sign across years; k2seeds / paper decide), vol1/vol6/rng1 +0.14..+0.16 SIG but their top quintile has the WORST mean and stop rate 7-8 % (not a long-dip filter); book directional IC all 20 cells NS (|ic| <= 0.03) while |move| IC stays strong (vol1 0.18): Kronos forecasts volatility, not sign; G2 weights already lean against er/low1 | 2026-10-08
- `oc_k2parity` | does the live Kronos feed (scripts/kronos_shadow.py) reproduce the research K2 features? | PASS | backfill 2026-09-01..23 joined 2745 rows: bars and sigma bit-identical, low1 Spearman 0.982, k2_mult differs on 4.55 % of rows vs 10.0 % between two research seeds (MC noise, no code difference); paper_d17bfg2k2 tests the researched signal | 2026-10-08
- `oc_chronos` | Chronos-Bolt-small (second foundation model, non-crypto pretraining) as a dip-size tilt, rule identical to K2 (C2) | LEAD (leader reading: C2 is the pre-registered dev4 ROBUST pick; worker's "reject" compared with K2 on the clean year, which the protocol forbids) | dev4 mean 5.739 / WORST 2.711 / DD 15.48 vs REF 5.601 / 2.588 / 16.91 (robust pick C2 > K2 2.469 > C2K2 2.452); post-release year once: C2 4.754 (+0.106) full DD 15.42 vs REF 4.648 / 16.82 (K2 4.801, C2K2 4.776); 5y geometric 5.54 vs 5.41; timing placebo pct 90/88/100/100 and 99.2 clean; Chronos-Kronos risk Spearman 0.22 (different signals); next: Bybit frictions, blind audit, pretraining-corpus check, live shadow + paper runner | 2026-10-08
- `oc_toto` | Datadog Toto (third foundation model, observability pretraining = nearly clean dev) as a dip-size tilt, rule identical to K2 (T3) | DIAGNOSTIC (supports the "foundation-model risk tilt" family; T3 itself not picked) | dev4 T3 mean 5.557 / WORST 2.486 / DD 15.65 vs REF 5.601 / 2.588 / 16.91 -> REF keeps the robust pick (worker excluded REF from its pick); post-release year once: T3 4.811 (+0.163) full DD 15.57, T3K2 4.829; 5y T3 5.407 vs REF 5.410 (K2 5.577); timing placebo 37 / 0.5 (2022, wrong way) / 100 / 100 / 100 clean; Toto-Kronos risk Spearman 0.29. All three FMs (K2, C2, T3): significant timing 2023-2026, none in 2021-2022 -> regime-dependent; the shared content may be plain volatility timing (oc_voltilt control) | 2026-10-08
- `oc_shortmember` | whale-flow book member A/Aq retrained on short labels h=6 / h=18 | CLOSED | builder check exact, G2 exact; AS18 = dev4 robust pick (W 2.704 vs 2.588, mean 5.556 vs 5.601, DD 18.02) but post-release year 4.628 < 4.648, 5y 5.37 < 5.41, full DD 18.05; AS6 W 2.237; short labels did not sharpen short-horizon IC; book win unchanged ~0.5 | 2026-10-08
- `oc_c2bybit` | Chronos C2 dip tilt under frictions S1-S5 incl. Bybit prices | LEAD CONFIRMED (most robust improvement so far; blind audit audit_c2 running; live feed bot_c2shadow being built) | all REF rows reproduce v421_audit to the digit; 5y C2 - REF: base +0.132, S1 +0.108, S2 +0.157, S3 +0.129, S4 +0.217, S5 (Bybit prices) +0.232 = 5.115 vs 4.883, full-path DD 16.50 vs 18.09; C2 full-path DD below REF under every friction; dev4 gap positive in all 6, post-release year (diagnostic re-score) +0.088..+0.115 in all 6; beats K2 on S4/S5 (K2 S5 5y +0.089, full DD 17.41); win rate unchanged (sizing only) | 2026-10-08
- `audit_c2` | blind audit of Chronos C2 + pretraining-contamination check | PASS-WITH-NOTES (exact) | fits re-derived blind are bit-identical, REF and C2 engine rows identical (dev4 5.739 / W 2.711 / DD 15.48; clean 4.754; 5y 5.542; full DD 15.42); 200 truncated ch_q10 recomputations max diff 4.2e-05; Chronos-Bolt training corpus (autogluon/chronos_datasets) has NO crypto series (only TradFi FX / pre-2016 M4 finance) -> dev 2021-2024 nearly clean; only note an unused helper | 2026-10-08
- `bot_c2shadow` | live prospective Chronos C2 feed (scripts/chronos_shadow.py, model pinned at revision 772f3d25) + paper runner d17bfg2ch | LIVE 2026-10-07 23:11 UTC | parity vs research 2026-09-01..23: bars exact, sigma 4e-16, ch_q max 1.3e-4, anchor-2025 multipliers 2745/2745 equal; anchor-2026 fit dir +1 q20 1.0766 q80 2.5956; runner reads c2 via the k2_mult column copy (no bot change); restart_all.ps1 now restarts the K2 / C2 runners and both shadow loops | 2026-10-08
- `oc_timesfm` | Google TimesFM 2.5 (fourth foundation model) as a dip-size tilt, rule identical to K2 | DIAGNOSTIC (family evidence; not picked) | dev4 mean 5.571 / WORST 2.473 / DD 15.69 vs REF 5.601 / 2.588 -> REF keeps the robust pick; post-release year once 4.746 (+0.098), full DD 15.65; 5y 5.406 vs 5.410; placebo 79 / 20 / 100 / 100 / 98.9 clean. Family read (K2, C2, Toto, TimesFM): all four lift the clean year (+0.10..+0.16) and lower full-path DD, all four time 2023-2026 but not 2021-2022; only C2 also lifts the 2021 worst year -> C2's dev pick is 1 of 4 models, treat its 2021 edge with caution; oc_voltilt decides whether plain vol timing explains the family | 2026-10-08
- `oc_voltilt` | plain volatility timing with the identical dip-size tilt rule (RV6 realised vol, GARCH(1,1)) - control for the foundation-model family | CLOSED (as a tilt) / KEY DIAGNOSTIC | fully clean dev4: V_RV6 mean 5.637 / WORST 2.271, V_GARCH 5.622 / 2.398 vs REF 5.601 / 2.588 -> REF keeps the robust pick; post-release year once: V_RV6 4.811, V_GARCH 4.932 (+0.284, higher than every FM tilt), full DD 15.55 / 17.12; 5y 5.471 / 5.484; timing placebo 2.4 / 14.5 / 97 / 100 / 100 (RV6) = the SAME signature as K2 / C2 / Toto / TimesFM; vol risk vs FM risk Spearman 0.31-0.59, V_RV6 multiplier == C2 on 52-62 % of rows. LEADER READ: the whole "bigger dip rungs when forecast downside vol is high" family is regime-dependent vol timing (helps 2023-2026, hurts or nothing in 2021-2022); C2 is 1 of 6 tilts that kept the 2021 worst year (its 2021 timing pct 90, not significant) -> treat C2's dev pick as possibly lucky under multiplicity; only prospective paper (d17bfg2k2, d17bfg2ch) can tell whether the regime persists | 2026-10-08
- `oc_k2seeds` | Kronos K2 clean-year gain across 5 sampling seeds (program rule >= 5 seeds) | DIAGNOSTIC (seed-stable) | all gates exact; clean-year R 4.782..4.825 for seeds {1234, 1, 2, 3, 4} (all > REF 4.648, gain +0.13..+0.18), timing pct 95.9..98.9, block 97.8..99.3; ~7 % of bars change multiplier per seed but R span only 0.043; dev years identical by construction. Seed noise is not the issue - regime dependence is (oc_voltilt) | 2026-10-08
- `oc_c2carry` | account-realistic profile G2 / K2 / C2, each +- quarterly carry f 0.25, on Binance and Bybit prices | DIAGNOSTIC (owner expectation) | all f=0 rows reproduce to the digit; Bybit 5y: G2+carry 5.111 / full DD 17.93, K2+carry 5.199 / 17.26, C2+carry 5.342 / 16.35; recent year on Bybit with carry 4.493 / 4.602 / 4.607 (none >= 5); bootstrap on Bybit with carry: median 5.23 / 5.33 / 5.42 %/mo, P(DD > 20 % in a year) 11.2 / 9.9 / 10.6 %, P(losing year) 0.75 / 0.60 / 0.70 %. Caveat: tilts' edge is regime-dependent (oc_voltilt) | 2026-10-08
- `oc_tiltgate` | parameter-free "follow last year" gate for the vol dip tilts (ON in year Y iff the tilt's replica effect over the prior 12 months > 0) | CLOSED | 2021 OFF (no 2020 fit: 948 < 1000 harness rows); prior-year effects -2.7e-4 / -1.8e-4 / -0.8e-4 / +0.7e-4 per fill (RV6) -> ON only 2025; GARCH ON only 2024 (+2.5e-5) and OFF 2025 (-4e-6): decisions flip on dust-thin margins; dev4 G_GARCH 5.612 vs REF 5.601 (one ON year), clean year G_GARCH 4.648 (OFF), G_RV6 4.811; 5y 5.418 / 5.442; nothing reaches 5 %; the vol-tilt family is closed (3 variants used) | 2026-10-08
- `oc_presampletilt` | V_RV6 / V_GARCH / C2 dip tilts (frozen anchor-2021 rules) on the PRE-SAMPLE spot replica 2017-2020 (unseen by Chronos / GARCH) | DIAGNOSTIC (important) | 9,731 pre-sample fills; gain > 0 over all 9 years: C2 7/9 (2017, 2018, 2019, 2022-2025; loses 2020p COVID -0.159 and 2021 -0.018), V_GARCH 6/9, V_RV6 4/9; timing >= 95: 5-6/9; common failure = crash legs (COVID 2020, 2021-2022 for the vol tilts) where bigger rungs in high vol catch the crash, not the rebound. Read: the family is broadly positive outside crash regimes, C2 the most consistent -> oc_beargate tests the crash/bear conditioning | 2026-10-08
- `oc_dip1h` | 1h-grid dip sleeve (G2 ladder 2.5-5.0 sigma1h, TP 1 sigma, stop 4 sigma, market exit at next 1h open) next to G2 | CLOSED | 20,870 rungs; standalone H05 0.53 %/mo dev4 (2022 losing), H025 0.27; win 64 % but 8 % stops erase ~50 TPs each; combined G2+H025 dev4 5.45 / DD 19.3, G2+H05 DD 21.6 -> G2 alone is the robust pick; daily corr +0.25 with G2 (losses in the same sell-offs) | 2026-10-08
- `oc_beargate` | dip tilts only when G2's own frozen bear filter (BTC < SMA1200 4h bars) is off: C2_B, GARCH_B | CLOSED | bear share 73 % (2021), 41 %, 22 %, 14 %, 81 % (clean year!) -> "bear" is not the crash regime where tilts fail; dev4 C2_B mean 5.749 / W 2.597, GARCH_B 5.687 / 2.589 vs REF 5.601 / 2.588 (razor-thin pick C2_B); clean year once C2_B 4.699 (+0.051, timing pct 64.8 - gating destroys C2's clean-year timing), GARCH_B 4.815; 5y 5.538 / 5.512; ungated C2 stays better on the clean year; tilt-family conditioning closed | 2026-10-08
- `oc_paperrecon` | live paper runner (paper_d17bfg2, 2026-10-05 17:52 .. 10-08 01:16 UTC) vs research engine replay on public Bybit 1m | DIAGNOSTIC (paper trustworthy for entries / protection; exits broken by the resend livelock) | 1043 entry episodes: 34 filled on both sides (33 same bar and price, 1 venue kline reprint), zero one-sided; 9 TPs and 4 book exits match; fee / funding accounting exact (replay-A diff 0.0000); the only mismatch = 20 dip time exits that the runner sent 420 times 03:00-07:31 and cancelled each ~25 ms later (diff step snapshotted `have` before the send) + the 03:24-07:01 runner outage -> filled at 07:32, +9.23 USDT (+0.18 %) better than the engine by luck (rally). bot_exitstuck fixes the livelock; until then paper exit timing is not evidence | 2026-10-08
- `oc_c2frontier` | does C2 shift the BOT return / DD frontier (D13BF, G2, G2K20 with and without C2)? | DIAGNOSTIC (frontier shifts on Binance, not enough on Bybit) | D13BF reproduces v424 exactly; Binance 5y / full DD: D13BF 4.971 / 14.86 -> +C2 5.222 / 14.91 (new DD<15 corner, max yearly DD 15.62), G2 5.410 / 16.82 -> +C2 5.542 / 15.42, G2K20 5.874 / 17.69 -> +C2 5.983 / 16.24 (dev4 mean 6.275, WORST 2.982 = highest of all rows; clean year 4.826); Bybit S5: D13BF 4.482 / 15.95 -> +C2 4.795 / 15.61 (clean year -0.021) -> no row reaches 5y >= 5 with DD < 15 on Bybit | 2026-10-08
- `oc_crashgate` | IDEAS5 #1: C2 dip tilt only when trailing-30d BTC drawdown depth < 15 % (V1) / 10 % (V2) | CLOSED at the replica gate | dSum5y +0.062 / +0.150 < +0.273; V2 recovers 2021 timing (97.7) but loses the clean year (-0.012, timing 73); gate binds on 40-65 % of bars (median depth 13 %); no engine run per rule. The tilt-family conditioning attempts (tiltgate, beargate, crashgate) are all closed | 2026-10-08
- `oc_vpinveto` | IDEAS5 #2: VPIN-50 toxicity veto (V1 book longs x0.5 when z > 2; V2 + skip new dip bids) | CLOSED | G2 exact; gate fires on 0.3-14 % of bars per year; dev4 V1 5.464 / W 2.598 / DD 17.20, V2 5.586 / 2.595 / 16.11 vs REF 5.601 / 2.588 / 16.91; V2 dip leg fails the replica gate (dSum5y -0.150); V1 (razor-thin pick) clean year 4.749 (+0.101) but 5y 5.320 < 5.410, full DD 17.13 > 16.82 | 2026-10-08
- `oc_manualveto` | IDEAS5 #8: MANUAL volatility veto of new bracket placement (V1 sigma360 > p80 of 90d; V2 V1 or BTC 24h range > 2x 30d median) | CLOSED | M5_human exact; vetoes skip 20-47 % of placements and lose return every dev year: V1 dev4 1.982 (2022 losing, full DD 20.51), V2 2.403 / W 1.043 (pick), clean year V2 2.764 vs M5 3.994 (-1.23) -> the veto skips winners, MANUAL gap widens to ~2.5 pp | 2026-10-08
- `oc_c2manual` | Chronos C2 multiplier on the MANUAL bracket dip rungs (human scales sizes at the bar open) | CLOSED | M5_human exact; KM_C2 5y 3.885 vs 3.728 (+0.157 of the 1.272 gap), dev4 +0.179, worst dev year 0.705 < 0.847, clean year 4.061 vs 3.994 (+0.067); beats KM_K2 on every headline; timing over CTRL +0.339 real but small; MANUAL still lacks entry edge | 2026-10-08
- `oc_downshare` | IDEAS5 #3: downside-share dip tilt (D1 trailing-6d downside-RV share; D2 HAR-RS 0.6/0.4 blend), K2-style quintile rule | D1 = DEV4 ROBUST PICK, not adopted (clean year -0.057); D2 CLOSED | fully clean dev (no pretraining): D1 replica gate PASS (dSum5y +0.653, 4/5) -> engine dev4 5.776 / WORST 2.921 / DD 16.09 vs REF 5.601 / 2.588 / 16.91 (largest worst-year gain so far); post-release year once 4.591 vs 4.648, 5y 5.538, full DD 15.98; D2 fails the gate (-0.425). LEADER CAVEAT: D1's per-anchor training rho is ~0 (+0.013, -0.020, -0.005, +0.001, +0.003; anchor-2026 +0.003) and the fitted direction FLIPS (+, -, -, +, +) -> the dev4 gain is most likely sign luck on a null signal; no D1 paper runner (scripts/d1_shadow.py built and parity-exact but not started) | 2026-10-08
- `oc_spillgate` | IDEAS5 #4: cross-asset vol-spillover book gate (S1 5-coin corr level > p90; S2 24h corr change > p95; book x0.5) + exposure-matched controls | CLOSED | G2 exact; dev4 S1 5.345 / DD 17.35, S2 5.522 / 16.82 vs REF 5.601 / 16.91; both trail their constant-trim controls (5.832 / 5.707): spike bars are above-average book bars; clean year S2 4.341 (-0.307), 5y 5.285 | 2026-10-08
- `oc_fmbookic` | do Chronos / Toto / TimesFM median forecasts carry BOOK direction? (descriptive) | CLOSED | clean-year pooled median IC +0.01 / -0.00 / +0.02 at h=1, all ns at h=1/2/6/18, per-coin 29/30 ns; dev spread positives vanish on the clean year; spreads (q90-q10) carry vol (+0.16..+0.23 vs |y|) every year; Chronos median correlates +0.28 with the book weights but has no forward IC -> foundation models forecast volatility, not direction (same as Kronos) | 2026-10-08
- `oc_oishort` | IDEAS5 #6: OI-rise / price-fall short-cover gate (book shorts x0.5 when 24h OI z > 2 / > 1.5 and 24h return < -2 sigma) | CLOSED | G2 exact; 135 / 216 gated bars in dev4 (2021 non-BTC norms empty -> never gated); dev4 5.572 / W 2.588 / DD 16.83-16.86 vs REF 5.601 / 2.588 / 16.91 -> REF keeps the pick; clean year not scored for the variants | 2026-10-08
- `oc_lsratio` | IDEAS5 #7: top-trader long/short-ratio contrarian book gate (L1 longs x0.5 when ratio > p90; L2 symmetric p90 / p10) | CLOSED | G2 exact; 2022 gate off for all coins (exchange-wide count-ratio gap) and 2021 off for non-BTC (disclosed); dev4 L1 5.831 / W 2.553, L2 5.877 / W 2.529 vs REF 5.601 / 2.588 -> mean +0.23 / +0.28 but worst year lower -> REF keeps the robust pick (dev-mean gains do not transfer, v189-v197 lesson) | 2026-10-08
- `oc_cascadedelay` | IDEAS5 #10: halve the dip budget for 7 / 3 days after a > 4 sigma 4h move | CLOSED at the replica gate (decisively) | dSum5y -2.946 / -2.018, sum-half 0/5: the cooled fills (52-72 %) carry the sleeve's profit - post-cascade dips are the BEST dips (timing 0.1 in 2024 = worse than random halving) | 2026-10-08
- `oc_rungquality` | IDEAS5 #9: skip dip rungs whose (coin, depth) cell had stop-given-fill > p80 (F1) / + chronic non-fillers (F2) | CLOSED at the replica gate | dSum5y -0.466 / -0.699, sum-half 2/5 / 1/5: skipped fills are winners in every active year (win 65-81 %); stops (~4 %) are too rare for any cell veto to pay for the lost exposure (same as oc_rungcap / oc_rungspace) | 2026-10-08
- `oc_fundclock` | IDEAS5 #5: flatten book longs x0.5 around settlements whose predicted funding (60m premium TWAP 1h before) > trailing-90d p90 (W1 + dip cancel; W2 book only) | CLOSED (dev4 pick W2 did not transfer) | G2 exact; dev4 W1 5.732, W2 6.162 / W 2.590 / DD 15.19 vs REF 5.601 / 2.588 / 16.91 (pick W2); clean year once W2 4.488 (-0.160); 5y 5.825; flag rate drifts 3 / 24 / 47 / 25 / 2 % per year (frozen p90 non-stationary, like oc_bookfunding) -> another dev-mean gain that did not transfer | 2026-10-08
- `audit_d1` | blind audit of the D1 downside-share tilt | PASS-WITH-NOTES (exact) | features 5e-12, fits incl. the flipping directions (+, -, -, +, +) bit-identical, engine rows identical (dev4 5.776 / W 2.921, clean 4.591, 5y 5.538, full DD 15.98); implementation is correct - the caveat is statistical (training rho ~0), not a bug | 2026-10-08
- `oc_d1bybit` | D1 downside-share tilt under frictions S1-S5 incl. Bybit prices | CLOSED (with the rho~0 caveat) | REF rows reproduce v421_audit exactly; D1 - REF dev4 +0.081..+0.222 and 5y +0.057..+0.163 under every friction, but the post-release year is negative under every friction (-0.021..-0.073); D1 vs C2 multipliers Spearman |rho| <= 0.20 (different signals); C2 keeps a positive post-release gap under every friction, D1 loses everywhere -> no D1 runner | 2026-10-08
- `oc_d1c2` | pre-registered ensembles of the D1 and C2 dip multipliers (AVG mean; AGREE only when both agree) | CLOSED | multipliers nearly independent (Spearman 0.03, agreement 33-54 %); dev4 AVG 5.744 / W 2.820 / DD 15.77 (pick), AGREE 5.685 / 2.753 / 16.21 vs REF 5.601 / 2.588 / 16.91; post-release year (labelled, both legs had seen it) AVG 4.696, AGREE 4.740 vs C2 alone 4.754; 5y AVG 5.533 vs C2 5.542 -> no gain over C2 alone; D1's null training signal makes the ensemble no better evidence | 2026-10-08
- `oc_cascadeboost` | dip budget x1.5 for 7 (B7) / 3 (B3) days after a > 4 sigma 4h move (the inverse of oc_cascadedelay) | LEAD (CONTAMINATED: idea formed after the delay replica saw all 5 years) - under verification (oc_cboostctrl exposure controls, oc_cboostpre unseen 2017-2020, oc_cboostbybit frictions, audit_cboost) | replica gate PASS (B7 +2.95, B3 +2.02, 5/5); engine dev4 B7 6.74 / WORST 2.96 / DD 17.92, B3 6.33 / 2.60 / 18.05 vs REF 5.60 / 2.59 / 16.91 -> pick B7; 5y 6.36; post-release year 4.88 (labelled); worst 1m-marked episode (2023-04-17 .. 06-14) 17.75 % | 2026-10-08
- `oc_cboostpre` | B7 / B3 cascade boost on the UNSEEN pre-sample replica 2017-2020 | DIAGNOSTIC (partial support) | 915 cascade fires; B7 normalised gain +0.046 / +0.078 / +0.111 / -0.069 (2017, 2018, 2019, 2020p COVID), B3 +0.026 / +0.049 / +0.298 / -0.137; timing >= 95 in 2/4 (B7), 3/4 (B3); boosted stop rate +0.6 pp pooled but +1.5 / +3.3 pp in the COVID leg -> the boost levers crash legs, helps in 3 of 4 unseen years | 2026-10-08
- `oc_makerexit` | IDEAS6 #1: maker-only timeout exit for dip time exits | CLOSED at the replica gate | dSum5y -1.40 / -1.34, loses every year: 91 % maker fills save 4.5 bps but the 8 % unfilled remainders sell 60 min deeper into dumping tape (adverse selection) | 2026-10-08
- `oc_partialtp` | IDEAS6 #2: sell half early at 0.5 / 0.75 sigma, runner to the 1 sigma TP | CLOSED at the replica gate | dSum5y -1.86 / -0.86, 0/5 years: win rate up (70 -> 74 %) but mean bps down (17.9 -> 13.0 / 15.7) | 2026-10-08
- `oc_netting` | IDEAS6 #3: book / dip and cross-clock inventory netting | CLOSED | N1 cuts 39 % of dip rungs (skipped short-book dips still carry post-cascade profit): dev4 5.419 / W 2.830 / DD 16.56 vs 5.601 / 2.588 / 16.91; clean year 4.641; 5y 5.263; N2 == N1 under proportional fees | 2026-10-08
- `oc_tapepeg` | IDEAS6 #4: rung = min(sigma price, trailing-60m 1m low - 1 tick) | CLOSED at the replica gate | peg binds on 0.22 % of rungs; dSum5y +0.067 / +0.069 < +0.273 | 2026-10-08
- `oc_fundhold` | IDEAS6 #5: extend dip time exits +8h when funding is low | CLOSED at the replica gate | dSum5y -0.688 / -0.381, LOO 0/5 | 2026-10-08
- `oc_clockweights` | IDEAS6 #6: yearly capital weights across the 4 clocks (V1 inverse DD, V2 trailing Sharpe) | CLOSED (tiny) | dev4 V2 5.77 / W 2.588 / DD 16.63 (pick, worst tied); clean year 4.677 vs 4.648 (+0.03); 5y 5.55; equity overlay only (no engine confirm) | 2026-10-08
- `oc_booktwo` | IDEAS6 #7: two-rung book entry ladder (10 + 25 bps) | CLOSED | dev4 V2 5.456 / 2.534 / 17.50, V1 5.378 vs REF 5.601; 5y 5.268, full DD 17.41 | 2026-10-08
- `oc_recycle` | IDEAS6 #8: recycle TP-freed capital into the next rung of the same window | CLOSED at the replica gate | dSum5y -0.024 / -0.007; recycled fills win 70 % but lose money (small TPs vs -4 / -8 sigma tails) | 2026-10-08
- `oc_cboostmanual` | cascade boost on the MANUAL bracket rungs (x1.5 for 7 / 3 days after a cascade bar, human schedule) | CLOSED | M5_human exact; KM_B7 5y 3.817 (+0.09 of the 1.27 gap) but worst dev year 0.342 vs 0.847, dev DD 20.04, full-path DD 22.99 (KM_B3 24.47) -> no eligible pick; without the BOT's corr-aware sizing and gross cap the boost levers crash legs | 2026-10-08
- `oc_bybitfill` | venue-aware offsets on Bybit prices: TP 3 bps lower (TPm3), rungs 3 bps shallower + TPm3 (RUNp3) | CLOSED | more TP / rung fills (+29..+98 per year) but lower quality: 5y 4.834 / 4.868 vs REF_S5 4.883; recovery share of the Bybit gap negative (-6.9 / -9.3 %) | 2026-10-08
- `oc_cboostbybit` | cascade boost B7 under frictions S1-S5 incl. Bybit prices | LEAD (gap robust, DD breach on Bybit) | all REF rows reproduce v421_audit; B7 - REF 5y: base +0.954 (6.364 / full DD 17.75), S1 +0.634, S2 +0.971, S3 +0.766, S4 +0.886, S5 Bybit +1.023 (5.906 vs 4.883) but full-path DD 20.31 > 20 on S5 (episode 2023-04-17 .. 10-02); dev4 gap +0.79..+1.22 everywhere; post-release year (labelled) +0.009..+0.236 everywhere -> next: B7 on the lower-risk D13BF base (oc_b7frontier) | 2026-10-08
- `audit_cboost` | blind audit of the cascade boost B7 | PASS (exact) | triggers, boost multipliers (53,877 / 53,877) and every engine number identical (dev4 6.738 / W 2.955 / DD 17.92, 5y 6.364, full DD 17.75); feature / window / fit / fill timing PASS incl. truncation; cap 2.0 and G2 limits bind | 2026-10-08
- `oc_b7frontier` | B7 on the D13BF base and G2 + B7, each +- quarterly carry f 0.25, Binance and Bybit prices | DIAGNOSTIC (B7 needs G2's gross cap) | D13BF has no gross cap, so D13BF + B7 breaches DD (dev4 20.54 base / 22.33 Bybit; Bybit + carry 5.349 / full DD 21.21, P(DD>20 %/yr) 27 %); G2 + B7 + carry on Bybit: dev4 6.482 / W 2.391 / DD 18.93, 5y 6.127, full DD 19.72, recent (labelled) 4.719, bootstrap median 6.08 %/mo, P(month >= 5 %) 64.8 %, P(DD > 20 % in a year) 15.7 %, P(losing year) 0.6 % (vs G2 + carry 5.111 / 17.93, P(DD>20) 11.2 %) -> the gross cap is what contains B7's crash exposure | 2026-10-08
- `oc_b7breaker` | IDEAS7 #4: suspend the cascade boost after >= 2 cascades in 14 days (V1) / >= 3 in 21 (V2) | CLOSED | clean pre-sample test: fixes the COVID leg (+0.186 / +0.082) but destroys 2018-2019 (sum vs B7 -0.360 / -0.447; clustered cascades are where the boost earns); boosted stop flag +1.3 / +1.6 pp; 2021-2026 replica -2.16 dev4 units vs B7 -> keep plain B7 | 2026-10-08
- `oc_b7first` | IDEAS7 #3: boost only after the FIRST cascade (no prior cascade in 14 / 7 days), no stacking or extension | CLOSED | clean pre-sample sum vs B7 -0.39 / -0.64 (helps 2/4, 1/4 years vs B7 3/4); boosted stop rate +1.4 / +2.0 pp; 2021-2026 dev4 also below B7 -> the profit lives in the stacked windows | 2026-10-08
- `oc_b7c2` | cascade boost B7 stacked with the Chronos tilt C2 (product; product capped at 1.5) | DIAGNOSTIC (B7 keeps the Binance dev4 pick; B7C2 is the Bybit-deployable form) | dev4 Binance: B7 6.738 / W 2.955 / DD 17.92, B7C2 6.652 / 2.922 / 17.05, cap 6.501 / 2.874 / 17.04 -> pick B7; Bybit S5: B7 5y 5.906 / full DD 20.31 (breach), B7C2 5.685 / 17.43 (dev4 5.944 / W 2.253 / DD 17.56; worst year above B7's 2.200 and REF's 2.129), cap 5.596 / 17.41; post-release (labelled) B7C2 4.99 base / 4.657 Bybit -> C2 removes ~2.9 pp of B7's Bybit full-path DD for -0.22 %/mo | 2026-10-08
- `oc_b7deep` | IDEAS7 #2: boost only deep rungs (>= 3.5 / 4.0 sigma) inside B7 windows | CLOSED | clean pre-sample sum vs B7 -0.212 / -0.271 (beats B7 1/4, 0/4 years); deep boosted stops +2.6 / +4.1 pp (COVID +6 / +10 pp); 2021-2026 dev4 below B7 | 2026-10-08
- `oc_b7taper` | IDEAS7 #1: tapered boost inside the 7-day window (V1 step, V2 exponential) | CLOSED | clean pre-sample: V1 beats flat B7 by +0.129 (3/4 years), V2 ties (+0.001), both worse in the COVID leg; engine dev4 V1 6.560 / W 2.724, V2 6.288 / 2.720 vs B7 6.738 / 2.955 -> keep flat B7 | 2026-10-08
- `bot_exitstuck` | time-exit market orders re-sent for hours without filling (soak) / 27 times (paper) | FIXED (bot/run.py) | cause: have() was polled after the exits loop and the cb14cb7 filter kept only the newest exit link, so each 2-minute re-send cancelled its predecessor before the paper / mock fill bar (livelock); fix: poll have() before the exits loop, wait (op exit_wait) while the exit link rests, never cancel or re-send a resting market exit; flush soak 3532 -> 0 violations, calm soak 0, all bot / ops tests pass; GO for testnet on the code side | 2026-10-08
- `bot_b7shadow` | live cascade-boost feeds (B7, B7 x C2) via the existing --k2-tilt flag | BUILT | scripts/cascade_shadow.py; parity 2740 / 2740 vs the frozen research boost multipliers; gross cap and every limit apply after the k2 scaling (bot/run.py:651-666, 1816-1824; mirror.py:696-701, 759-819) | 2026-10-08
- `oc_b7btceth` | IDEAS7 #5: cascade boost only on BTC + ETH (V1) / BTC only (V2) | CLOSED | clean pre-sample sum vs B7 -0.181 / -0.308 (the dropped alt-coin boosted fills were profitable too); 2021-2026 replica also below B7 -> keep the all-majors B7 | 2026-10-08
- `oc_b7patient` | IDEAS7 #6: patient exits for boosted fills (V1 TP 1.0 -> 1.5 sigma; V2 timeout +1 bar) | CLOSED (replica-engine divergence) | clean pre-sample replica beats B7 (V1 +1.285, V2 +0.545) but the engine refutes V1: dev4 6.449 / WORST 1.284 / full DD 23.14 vs B7 6.738 / 2.955 / 17.75 (longer holds tie up capital under the gross cap and deepen DD); V2 engine not runnable (timeout hard-coded in backend/history_tm.simulate) -> keep B7; lesson: dip-exit ideas must be engine-confirmed | 2026-10-08
- `oc_cboostctrl` | is B7 timing or exposure? engine controls: CTRL_C constant dip-budget multiplier = B7's realised yearly mean (1.26 / 1.34 / 1.36 / 1.30), CTRL_R 20 random-window seeds | KEY DIAGNOSTIC: B7 IS MOSTLY EXPOSURE | dev4 REF 5.601 / W 2.588 / DD 16.91; CTRL_C 6.441 / 2.940 / 18.33; CTRL_R mean 6.359 (p5 6.16 / p95 6.49), DD 18.07; B7 6.738 / 2.955 / 17.92 -> exposure explains 74 % (vs CTRL_C) / 67 % (vs CTRL_R) of the dev4 gain, timing ~0.3 %/mo; B7 above the random p95 in 1/4 dev years only; cascade windows are active ~60 % of the time (any of 5 coins x 4 clocks) -> B7 is essentially ~1.3x dip leverage with mild timing, i.e. a move along the known BOT frontier (G2K20 etc.) plus ~0.3 pp | 2026-10-08
- `oc_b7c2pre` | B7 x C2 stack on the clean pre-sample replica 2017-2020 | DIAGNOSTIC | stack gain vs no tilt +0.063 / +0.076 / +0.138 / -0.225 (2017, 2018, 2019, 2020p COVID); vs B7 alone +0.017 / -0.002 / +0.027 / -0.155; capped variant similar (COVID -0.165); C2 does not cushion the crash leg on unseen years (boosted COVID stops +1.75 vs +1.55 pp) -> B7xC2's lower Bybit DD in 2021-2026 is not confirmed pre-sample; both stay paper-only | 2026-10-08
- `oc_b7thresh` | robustness surface of the cascade boost (trigger 3.5 / 4.0 / 4.5 sigma x window 3 / 5 / 7 / 10 days), report only | DIAGNOSTIC (broad plateau) | 2021-2026 replica dSum positive in all 12 cells (+1.70..+3.14; B7 not the argmax); clean pre-sample best k4.5 / W10 (helps 4/4 incl. COVID +0.109), B7 3/4; engine corners dev4 6.28-6.90 (B7 6.74), 5y 6.00-6.42, full DD 17.38-18.52 -> B7 sits inside a broad helpful plateau (consistent with "mostly exposure", oc_cboostctrl); no retuning | 2026-10-08
- `oc_bookband` | book turnover / fee drag and a no-trade band on target changes (NB10 / NB25 of the coin's trailing-90d mean |target|) | CLOSED | small re-targets are 69-76 % of re-targets but 27-34 % of turnover, their marginal net flips sign by year (no stable bleed); dev4 NB10 5.447 / W 2.617, NB25 5.440 vs REF 5.601 / 2.588 (pick NB10 on W); clean year NB10 4.679 vs 4.648; 5y 5.293 vs 5.410; fees saved only 0.0066 over 5y -> book turnover is not a cost problem | 2026-10-08
- `oc_levfrontier` | deployable frontier on BYBIT prices + quarterly carry f 0.25: dip-mult {1.7, 2.0} x overlay {none, C2, B7, B7xC2} | DIAGNOSTIC (owner decision table) | 5y / full DD / worst dev year / recent year (labelled) / bootstrap median, P(DD>20 %/yr): G2 5.111 / 17.93 / 2.321 / 4.493 / 5.23, 11 %; G2+C2 5.342 / 16.35 / 2.405 / 4.607 / 5.42, 11 %; G2+B7 6.127 / 19.72 / 2.391 / 4.719 / 6.08, 16 %; G2+B7xC2 5.910 / 17.28 / 2.445 / 4.707 / 5.87, 16 %; G2K20 5.567 / 19.02 / 2.529 / 4.544 / 5.58, 15 %; G2K20+C2 5.593 / 17.78 / 2.539 / 4.619 / 5.66, 14 % (robust pick on Bybit dev4: highest worst year); G2K20+B7 6.345 / 23.72 (DD breach); G2K20+B7xC2 6.144 / 18.48 / 2.145 / 4.787 / 5.85, 22 %. No row reaches >= 5 %/month in the most recent year on Bybit | 2026-10-08
- `oc_btcresid` | IDEAS8 #1: BTC-residual idiosyncratic book (trade coin returns net of a frozen per-anchor BTC beta) | CLOSED (decisively) | dev4 V1 -0.18 %/mo (3 losing years, DD 43.84), V2 +0.25 (DD 42.39) vs REF 5.60, exposure controls 5.46 / 5.65 track REF -> the BTC-beta leg carries the book's P&L; take-profits collapse (7 vs 35-37) | 2026-10-08
- `oc_kronosbase` | Kronos-base (102M) zero-shot K2-rule dip tilt, inference on Kaggle (account 1, private dataset + 5 private GPU kernels) | CLOSED (family evidence) | verify50 reproduction PASS; base vs small low1 Spearman 0.855; fits all +1; dev4 KB2 5.834 / W 2.524, KBK2 5.803 / 2.519 vs REF 5.601 / 2.588 (REF keeps the robust pick on the worst year); post-release year once KB2 4.826 (+0.025 over K2), 5y 5.632, timing pct 99.2 - same vol-timing family, bigger model adds ~nothing | 2026-10-08
- `oc_clockagree` | IDEAS8 #5: book size by cross-clock sign agreement | CLOSED | dev4 V1 5.578 / W 2.591 vs REF 5.601 / 2.588 and exposure control 5.608; clean year 4.622 vs 4.648; V1 == V2 on every cell (the 3-of-4 case never occurs with ffilled weights) | 2026-10-08
- `oc_decayexit` | IDEAS8 #6: book exit when |w| decays below 0.3 / 0.5 of the entry weight (winners ride to the flip) | CLOSED | dev4 V1 5.583, V2 5.607 / W 2.592 / DD 17.04 (razor pick) vs REF 5.601 / 2.588 / 16.91; clean year V2 4.728 (+0.080); 5y 5.431 vs 5.410; both trail the constant exposure control (5.751) on mean; the rule rarely binds beyond G2's signal-gone close | 2026-10-08
- `oc_horizondecay` | IDEAS8 #4: book from a decay-weighted blend of member horizons h = 1, 2, 6, 18 (1/h, 1/sqrt h) | CLOSED | dev4 ~4.5-4.6 vs REF 5.6, 2022 DD > 22 (breach), ~1.3 pp below the exposure-matched control -> the trained h=42 label stays | 2026-10-08
- `oc_memberagree` | IDEAS8 #3: book size by member sign agreement (x1.0 if >= 5 of 6 agree, else smaller) | CLOSED | dev4 V1 5.686 / W 2.609 (pick), V2 5.897 / 2.551 vs REF 5.601 / 2.588; exposure controls beat both (C_V1 5.716, C08 5.861) -> the gain is exposure, not confidence timing; clean year V1 4.566 < 4.648 | 2026-10-08
- `oc_volvolbrake` | IDEAS8 #8: book x0.5 when the 30d vol-of-vol of BTC RV6 > p90 / p85 | CLOSED | dev4 V1 5.435, V2 5.471 vs REF 5.601; constant exposure controls 5.830 / 5.821 beat both (gated fragile bars are above-average book bars); clean year identical to REF (gate off) | 2026-10-08
- `oc_convttl` | IDEAS8 #7: book entry orders rest 2 bars when |w| is above the pre-anchor median (p75) | CLOSED | dev4 V1 5.615 / W 2.588 vs REF 5.601; clean year 4.678 vs 4.648; fills essentially unchanged; again the constant exposure controls beat both (C_V1 5.834, C_V2 6.042) -> see oc_booktrim | 2026-10-08
- `oc_booktrim` | uniform book trim x0.8 / x0.6 (constants fixed in advance) to free gross-cap room for dips | CLOSED | return falls monotonically: dev4 BT08 5.243 / W 2.548, BT06 4.805 vs REF 5.601 (Bybit 4.556 / 4.192 vs 4.994), DD only -0.6 / -1.1; dips gain no fills (-17 of ~17k: rung count is set by the risk budget and the cap binds in every phase anyway) -> the book is not over-sized; the "constant control beats G2" pattern in other studies was an artefact of their realised scale | 2026-10-08
