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

- 2026-10-06 oc_carryborrow: carry f = 0.5 with USDT borrow for the extra spot (10 / 15 %/yr APR) LOSES vs f = 0.25 (base 5.569 / 5.424 vs 5.634; S1 4.696 / 4.550 vs 4.780; DD +0.2-0.35 pp). Keep f = 0.25. research/tournament/oc_carryborrow/REPORT.md
