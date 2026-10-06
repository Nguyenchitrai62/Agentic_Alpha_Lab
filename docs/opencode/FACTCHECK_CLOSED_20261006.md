# FACTCHECK docs/CLOSED_DIRECTIONS.md (2026-10-06, worker audit_closeddirs)

Method (read-only; no git writes, no target edits): parsed all 115 backtick items in `docs/CLOSED_DIRECTIONS.md` (179 lines); for each resolved folder (`oc_*` -> `research/tournament/<n>/` else `research/diagnostics/<n>/`; `v*` -> `research/parallel/rounds/parallel-20260906-r2/<vnum>/`; `bot_*`/`M5_*`/`manual_*` -> diagnostics alias) and opened `REPORT.md` (first 40 lines) / `COMPARISON.md` / `result_manifest.json` + `results.json` / `PLAN.md` + `docs/opencode/OPENCODE_W_<name>.md`. Listed all `research/tournament/*/REPORT.md` + `research/diagnostics/*/REPORT.md` by mtime, kept date 2026-10-05/2026-10-06, substring-checked against CLOSED_DIRECTIONS.md.
Scope line of target: BOT G2 `R2B1D17BFG2` 5.41%/mo DD 16.91/16.82; MANUAL best ~3.7; gate costs maker 0.02%/taker 0.055% + adverse long funding 0.01%/8h.

## 1. Mismatch table (only rows with (a)/(b)/(c)/(d) flags; all other ~100 items reproduce exactly)

| # | CLOSED line | Folder | (a) verdict closed vs report | (b) numbers | (c) folder | (d) rule vs PLAN/assignment | Disposition |
|---|---|---|---|---|---|---|---|
| 1 | `v399/B1` KEPT | `rounds/v399/` | KEPT component vs manifest `rejected` (final R2B2, folds transfer fail) | OK: R2 4.82/DD25.05 -> R2B1 4.55/DD13.88 exact in `v399_result.json` | exists, no REPORT.md by convention (COMPARISON in `v399_v400_audit/`) | OK x1/(1+n) | wording only: `rejected`=fold-transfer, not deploy-reject |
| 2 | `v421/G2` KEPT deploy | `rounds/v421/` | same nuance: manifest `rejected` (folds pick base), G2 adopted downstream | OK: 5.41/DD16.91/full16.82, dDD -1.42pp ~= -1.4pp, gap 58.3->33.5% is `oc_gapstress` REPORT l.48 | exists, no REPORT.md | OK gross-cap 2.0x | wording only |
| 3 | `v427/C2` OPEN pending (sec3) | `rounds/v427/` | **MISMATCH**: sec3 OPEN pending vs manifest `status:rejected` AND vs Still-OPEN p.29 `C1(v428)/C2(v427) rejected` | N/A (README=eval-prep dev-only matches one-liner) | exists, no `v427_result.json` (README+manifest only) | OK module docstring=prereg | **fix: change sec3 to CLOSED/rejected to match manifest + Still-OPEN** |
| 4 | `oc_bookmodel_impl` OPEN pending, "8 tests pass; audit FAIL F1" | `research/tournament/oc_bookmodel_impl/` | NO verdict (impl only) | **STALE**: REPORT l.89 `11 passed` (8+3 new), l.62-72 F1 fixed via `common_impl.py:279-313` allowlist; `oc_bookmodel_reaudit/COMPARISON.md` PASS; `test_oc_bookmodel_audit.py:164-176` still pins old buggy behaviour by design | exists REPORT YES | PLAN missing by design; spec is `BOOKMODEL_PLAN_20261006.md`+`OPENCODE_W_oc_bookmodel_impl.md`, rule matches | **fix numbers to 11 passed / F1 fixed + reaudit PASS** |
| 5 | `v319/PP/PF` "2.67/2.86 vs 3.01" | `rounds/v319/` | CLOSED vs `rejected` OK | **STALE**: file `X1 2.482 / X2 2.313 / X0 3.011` (`v319_result.json`); direction (worsen) correct | exists, no REPORT.md | OK `v319_pooled_path_flow_members.py` | **fix values to 2.48/2.31** |
| 6 | `v285/D2/CB` "5y 5.725/last 5.167" | `rounds/v285/` | KEPT base vs `audited` (C4 gate_pass False) OK | PARTIAL: 5.725 matches manifest normal.monthly; `last 5.167` not in v285 folder (dev4 2021-24 only) | exists; D2/CB are rows not folders | OK `0.8CB+0.2D` | source the `last` number or drop it |
| 7 | `oc_tsmom*` "D13+0.10 DD15.42" | `research/tournament/oc_tsmom/` | CLOSED vs NOT PROMISING OK | **CONFLATION**: D13+0.10 DD15.42 lives in `oc_tsmomcombo`/`oc_tsmom_official`, not in `oc_tsmom/REPORT.md` | exists | OK 0.10/0.25x | move the D13 number to combo line |
| 8 | `oc_bookcoinbrake` OPEN PROMISING #45 (inside closed map) | `research/tournament/oc_bookcoinbrake/` | PROMISING 4/5+4/5, grind -30% (l.22-23, l.41-42) OK | OK | exists | OK S30 | **internal inconsistency**: tagged OPEN inside closed file; header Still-OPEN says tested as v426 G2BRK (5.30 vs 5.41, frontier, not adopted) i.e. closed-by-supersession; clarify line to `CLOSED superseded by v426` or move to Still-OPEN |
| 9 | `oc_earlystart` CLOSED fragile | `research/tournament/oc_earlystart/` | report PROMISING 4/5+4/5 but fragile (2023 -0.68, DD doubled) | OK 4/5+4/5, 2023 5.725->5.044 | exists | OK | token differs, substance agrees (paper-first); keep CLOSED-fragile wording |
| 10 | `oc_cooldown` CLOSED | `research/tournament/oc_cooldown/` | report PROMISING 4/5 DD + 5/5 retained, "essentially 2022 FTX cascade" | OK ("only 2022 real" = report caveat) | exists | OK 24h post-stop | token differs, substance (cascade-fuse-only) agrees |
| 11 | `oc_dvol` DIAGNOSTIC | `research/tournament/oc_dvol/` | report PROMISING z90 IC 5/5 | OK "small" (sub-bps, non-monotonic) | exists | OK | soft flag: filed as context though screen PROMISING |
| 12 | `oc_bookoffset` CLOSED | `research/tournament/oc_bookoffset/` | report PROMISING-as-assigned 5/5 (LOYO 5/5), closed w/o engine (trade-mode already sigma-scaled) | OK 5/5 | exists | OK | explained in-report; keep CLOSED with reason |
| 13 | `oc_bookcoinwf` CLOSED vacuous | `research/tournament/oc_bookcoinwf/` | report PROMISING-as-assigned 5/5+5/5 but VACUOUS (gate never excludes) | OK | exists | OK | explained by "vacuous" |
| 14 | `oc_idea9` CLOSED | `research/tournament/oc_idea9/` | report PROMISING-by-DD-bar (dDD 4/5) "do not adopt" | OK costs return/Sharpe 5/5 | exists | OK | CLOSED disposition defensible; wording understates report |
| 15 | `oc_bookevent`/`oc_fomcbook` "3/5+4/5 and 2/5+4/5" | both `tournament/` | both NOT PROMISING OK | AMBIGUOUS: fomc half (ret 2/5 + DD 4/5) exact; bookevent half fits only if 4/5 = event-bar P&L positive 4/5 (l.40), retention is 3/5 not 4/5 | exist | OK halve on windows | clarify to "DD 3/5 + ret 3/5 (windows +4/5)" |
| 16 | `oc_bookexit` "win up every year" | `research/tournament/oc_bookexit/` | NOT PROMISING OK | OVERSTATES: report win up 4/5 + 2021 tie; P&L -18..-62pp exact l.45 | exists | OK +1.0 ATR | fix to "win up 4/5 (+tie)" |
| 17 | `oc_cmegap` SCREEN PROMISING "4/5 P&L" | `research/tournament/oc_cmegap/` + `diagnostics/oc_cmegap4p` VERDICT:NO | OK | INCOMPLETE: DD-never-worse 5/5 omitted | exist | OK | add DD 5/5 |
| 18 | `v411/D17BF` "win all 65.5%" | `rounds/v411/` | accepted OK | ROUNDING: audit pooled all-win 0.6538 = 65.4%; R 5.425/DD18.33/full16.9 exact | exists | OK dips x1.7 + BF | rounding only |
| 19 | `oc_corrbudget`/`oc_idiocap` "-40% / worst-day 1/5" | both `tournament/` | both NOT PROMISING OK | MISLABEL: idio REPORT wd 0/5, maxDD-leg 1/5; bullet conflates | exist | OK | fix to "worst-day 0/5, maxDD 1/5" |
| 20 | `M5_human` "3.73/DD17.9 win 64.8%" | NO `tournament/M5_human/`; = `diagnostics/manual_human/` (SUMMARY, no REPORT) + `diagnostics/m5_robustness/` | KEPT-best-honest vs SUMMARY "Nothing was selected" (kept-as-reference) | DD CONVENTION: 3.73/fullDD17.8/win.6482 is `oc_manualcap` reset/mixed row (R5 3.728); single-clock-mean DD of same M5_human is 24.5 (max 33.9); not comparable to 21.6-24.5 DDs two lines below | alias only | no own PLAN/W (covered by manual* Ws) | clarify DD is 4-phase-mix convention |
| 21 | `v335/daily` "1.17-2.09" | `rounds/v335/` | CLOSED vs rejected OK | IMPRECISE endpoints (D00:60 1.165 .. D12:5 2.091; M2:60 2.139 also in range; 5y 2.387 unquoted) | exists | audit-convention path | conclusion unaffected |
| 22 | `oc_phasedisp` DIAGNOSTIC | `research/tournament/oc_phasedisp/` | no verdict keyword (descriptive) | OK singles 3.102-6.923, DD to 43.55 | PLAN missing (descriptive diag) | W exists | label has no verdict line/PLAN to match |
| 23 | `oc_clockanat` DIAGNOSTIC | `research/diagnostics/oc_clockanat/` (not tournament) | no verdict keyword (anatomy) | OK async-phase DD; cap G2 binds | PLAN missing | W exists | location note only |
| 24 | `oc_d13robust` DIAGNOSTIC | `research/diagnostics/oc_d13robust/` | ROBUST.md + results.json, NO REPORT.md | OK | (c) minor: ROBUST not REPORT | W exists | rename-tolerant check needed |
| 25 | `oc_bnbvenue` DIAGNOSTIC | `research/tournament/oc_bnbvenue/` | DIAGNOSTIC OK | OK BNB 9.99x spread | exists | OK | doc bug (not counted as mismatch): `oc_bnbvenue/results.json` cites `research/tournament/oc_bookvenue`, real path is `research/diagnostics/oc_bookvenue` |
| 26 | `oc_rips` (sec4) | `research/tournament/oc_rips/` | VERDICT NO OK | OK every rule 5y negative | PLAN YES but `docs/opencode/OPENCODE_W_oc_rips.md` MISSING | brief is DIP/RIP study file | missing-W alias only |
| 27 | `oc_newinfo` (sec4) | `research/tournament/oc_newinfo/` | mixed (6 NOT_PROMISING + 2 fragile) OK | OK two fragile hints | PLAN YES, no `OPENCODE_W_oc_newinfo.md` | brief is `OPENCODE_NEWINFO_WIKI_CME.md` | alias only |
| 28 | `oc_regime` / `oc_optctx` / `oc_liq` (sec9) | all `tournament/` | CLOSED/DIAG OK | OK | exist | Ws under variant names (`DIP/RIP_REGIME_STUDY`, `OPENCODE_W_OPTCTX.md`, `OPENCODE_W_LIQ.md`), `oc_regime` has no `OPENCODE_W_oc_regime.md` | naming-variant only |
| 29 | `oc_manualbf` DIAGNOSTIC | `research/diagnostics/oc_manualbf/` | NO-row-passes OK | OK 3.6-3.7/DD21.6 | exists | no `OPENCODE_W_oc_manualbf.md`; exists as `OPENCODE_W_MANUALBF.md` | naming-variant only |

(c) Folder-exists rollup: all 115 names resolve (oc_* all have REPORT+PLAN+results.json; v* have result_manifest+vNNN_result.json+run.log, no REPORT.md by convention; D2/CB/PT/PP/PF/X11/C2/B1/D17BF/G2 are rows not folders; M5_human is diagnostics/manual_human alias; `oc_bookvenue`/`oc_clockanat`/`oc_manual*`/`bot_*` live in diagnostics). No truly missing folder. (d) Rule rollup: every one-line rule matches its PLAN.md header (`# <name> PLAN (pre-registered BEFORE any outcome...)`) and its `docs/opencode/OPENCODE_W_*` assignment subject, except the alias-only rows 26-29 above.

## 2. Missing REPORTs (mtime 2026-10-05/2026-10-06, exact `oc_*`/name string absent from CLOSED_DIRECTIONS.md) + ready-to-paste lines

Note: bulk mtime `2026-10-06 14:03:23-26` recurs across ~80 REPORTs (touch/checkout artefact); listed per assignment anyway. Already-present (do NOT add): `oc_carrycorr`, `oc_calendar`, `oc_tpfill`, `oc_liqcheck`, `oc_grindsignal`, `oc_kpi_g2`, `oc_placebo`, `oc_placebo_dip`, `oc_premexpo`, `bot_capfix`, `oc_bookvenue`, `oc_clockanat`, `oc_cmegap4p`, `oc_expiry4p`, `oc_usdt4p`, `ops_jitterjob` (all named in file incl. Still-OPEN prose). Still-OPEN prose words ("FAR/top-up/2h bid TTL/MANUAL 2-coin/MANUAL+carry/expiry-day dip/mark-trigger/depth-tilt") do NOT contain the exact `oc_*` strings, so those folders count MISSING below.

- `oc_oos12d` | 12d OOS dip-only 2026-09-24..10-06 | DIAGNOSTIC | 14 exits win85.7%, in-band, no gate claim | 2026-10-06
- `oc_quietmonth` | quiet-start diagnostic | DIAGNOSTIC | low 4.87/norm 7.55/high 3.64 next-mo | 2026-10-06
- `oc_spreadcost` | half-spread taker overlay from live topbook | DIAGNOSTIC | -0.28 haircut, DD ~same | 2026-10-06
- `oc_planparity` | live-plan parity | DIAGNOSTIC | PARITY 0 mismatches | 2026-10-06
- `oc_carryparity` | frozen carry prospective parity | DIAGNOSTIC | 144/144 contract; 1 stale-basis bug | 2026-10-06
- `oc_frontiercarry` | carry f0.25 on 80 frontier rows | REPORTING | +0.13pp, 0 stretch; G2+carry 5.533/16.78 | 2026-10-06
- `oc_depthtilt` | depth-tilted sizing k/2.5 renorm sum5.0 (post-hoc) | CLOSED | 3/5+5/5+4/5 dSum -0.066<+0.273 | 2026-10-06
- `oc_crash2020` | G2 dip-only replay COVID/2021 windows | DIAGNOSTIC | COVID -16.1% mix/-21.8% phase; cap inert | 2026-10-06
- `oc_outage` | outage overlay weekly2h/monthly6h/quarterly24h/advers10h | DIAGNOSTIC | routine 1-2.5% cost; flush-outage tail only | 2026-10-06
- `carry_audit` | blind carry replication (COMPARISON.md only, no REPORT.md) | DIAGNOSTIC (FAIL numeric) | 20/25 basis + 25/25 ret miss; causality/fees/overlay PASS | 2026-10-06
- `oc_carryfar` | FAR 6-mo carry tenor | CLOSED (keep base) | FAR +0.425geom but 2x capital-time ~=base | 2026-10-06
- `oc_carrytopup` | delivery-week carry top-up f0.125 | CLOSED | 5y -0.14% Bin/-0.10% Byb, 0/5y pos | 2026-10-06
- `oc_carryd13` | D13BF + frozen carry f0.25/0.50 | KEPT map | f0.25 5.104/DD14.85; f0.50 5.234/14.71 | 2026-10-06
- `oc_carrycombo` | BOT/MANUAL + locked carry f0.25/0.50 | REPORTING | G2 +0.00-0.01R/-0.13DD; MAN ~3.75 still <5 | 2026-10-06
- `oc_carryfric` | carry under frictions S1-S5 | REPORTING | D13 base 5.104/14.85 only; G2 fails S1/S3 | 2026-10-06
- `oc_linvinv` | same-expiry linear-vs-inverse >=3pp/yr f0.125 | CLOSED | 0 entered, max 2.55<3pp | 2026-10-06
- `oc_marktrig` | mark-trigger stops close5/backstop | CLOSED | sum 4/5 but tails 2/5 | 2026-10-06
- `oc_discsniper` | spot-perp discount sniper z<-2 | CLOSED | 0/5, 5y -0.529, p13.3 | 2026-10-06
- `oc_expirydip` | expiry-day extra 5sg rung | CLOSED | 5/5+5/5 but dSum +0.0164<+0.273 | 2026-10-06
- `oc_manualcarry` | honest MANUAL + frozen carry | CLOSED | best 3.993 <5; return never passes | 2026-10-06
- `oc_manual2coin` | MANUAL SOL+XRP-only brackets (IDEAS2#8) | CLOSED | 3.24/17.1 and 3.39/24.3 vs M5 3.73/17.8 | 2026-10-06
- `oc_capscale` | G2 capital scaling A2000-25000 | DIAGNOSTIC | min 5000 USDT; R/DD A-const 5.41/16.82 | 2026-10-06
- `oc_clockluck` | hourly vs half-hour clock luck | DIAGNOSTIC | hourly 6.92/4.83/5.59/3.10; half 5.37/4.64/3.19/4.01 | 2026-10-06
- `oc_edgedecay` | G2 edge-decay diagnostic | DIAGNOSTIC | slope +0.07 CI incl 0; no decay | 2026-10-06
- `oc_phase8` | 8-clock 30-min screen G2 | CLOSED | 8-mix 4.96/17.32 vs 4-mix 5.41/16.82 | 2026-10-06
- `oc_plateau2` | plateau around G2 TP/stop/cap | DIAGNOSTIC | ref 5.410/16.91/16.82; within 0.3R/1.5DD | 2026-10-06
- `oc_saturation` | dip-size saturation anatomy | DIAGNOSTIC | D20 5.894/21.21 G2K20 5.874/17.79 saturate | 2026-10-06
- `oc_seedengine` | honest-expectation seed replay G2 | DIAGNOSTIC | 5y 5.343-5.430, no losing year any seed | 2026-10-06
- `oc_collectors` | liq+topbook collector health | DIAGNOSTIC | healthy 9h, 0 gaps, 326k rows | 2026-10-06
- `oc_kpi_d13` | D13 user-goal KPI + G2 neighbour | DIAGNOSTIC | D13 19.5x, DD14.86, win all 0.657 | 2026-10-06
- `bot_parity_adopt` | --adopt-fresh book-gap test | CLOSED | book 19/83, gap -0.0352; adopt +1 only | 2026-10-06
- `oc_bidttl` | 2-hour dip-bid TTL 16..135 | CLOSED | 0/5, dSum -1.339 | 2026-10-06
- `oc_stoptf` | stop timeframe S15/S1 vs close5 | CLOSED | S15 4/5+2/5, S1 2/5+5/5 | 2026-10-06
- `oc_usdtdip` | USDT-premium dip-size tilt | CLOSED | dSum +0.047<+0.273 gate | 2026-10-06
- `oc_c2ic` | C2-fix XS info test | CLOSED | cand 2/4y, pooled corr 0.41, NO | 2026-10-06
- `oc_tsmomcombo` | TSMOM sleeve on frontier rows (post-hoc) | CLOSED | +R but DD worse 48/50; no official stretch | 2026-10-06
- `oc_tsmomvar` | 5-coin + 90d-long-only TSMOM variants | CLOSED | DIV 0/5 both | 2026-10-06
- `oc_tsmom_official` | TSMOM on official metric | CLOSED | no stretch; D13BF@0.10 DD15.42>15 | 2026-10-06
- `oc_utamargin` | one UTA G2+carry f0.25/0.50 | KEPT f0.25 | f0.25 safe; f0.50 split-only | 2026-10-06
- `oc_utamargin2` | carry-short leverage 5/10/20x | DIAGNOSTIC | 10/20x IM-safe but f0.50 haircut-fail | 2026-10-06
- `oc_qbasis` | quarterly-basis z terciles | CLOSED | book Hi-Lo wrong way 0/5 | 2026-10-06
- `oc_kellydip` | analytical Kelly/DD sizing | DIAGNOSTIC | Kelly f* 0.5-6.5; budget-scale needed | 2026-10-06
- `oc_ladderfill` | fill timing + edge share | DIAGNOSTIC | n21389 win0.687 +17.76bps | 2026-10-06
- `oc_rlbear` | V2-lite bear-flag dip retrain | CLOSED | sum 3/5 DD 2/5 | 2026-10-06
- `oc_usdtshort` | USDT short-leg tilt | CLOSED | P&L 5/5 p99.6 but DD 3/5 | 2026-10-06
- `oc_bookvol` | book vol-target variants | CLOSED | all FAIL Sharpe bar | 2026-10-06
- `oc_agentens` | 5-seed ensemble vs deployed seed | CLOSED | ENS>=S0 2/5 | 2026-10-06
- `oc_idea1` | late-fill fast-TP 0.5sg | CLOSED | D 1/5, LOO 0/5 | 2026-10-06
- `oc_idea10` | 1h-confirmation dip filter | CLOSED | 2/5, LOYO 0/5 | 2026-10-06
- `oc_idea4` | funding-surprise dip filter | CLOSED | sign 5/5 but tail 3/5, ret 0/5 | 2026-10-06
- `oc_idea5` | premium-gated book flips | CLOSED | 25 fires, dDD 1/5 | 2026-10-06
- `oc_idea6` | basis-momentum dip throttle | CLOSED | gain 2/5 tail 1/5 | 2026-10-06
- `oc_idea7` | VRP-regime budget dial | CLOSED | gain 4/5 tail 2/5 | 2026-10-06
- `oc_idea8` | dominance-momentum dip throttle | CLOSED | gain 4/5 tail 3/5 | 2026-10-06
- `oc_crashfreq` | one-bar dip crashes >=3% | DIAGNOSTIC | 82 bars; -15% once 2024-01-03 | 2026-10-06
- `oc_ddanat17` | s=0 DD anatomy | DIAGNOSTIC | 9.9-18.5 DD; dip 70-72% in 2/5 | 2026-10-06
- `oc_ddanat4p` | 4-phase gate-DD anatomy | DIAGNOSTIC | gate=2024-01-03 async cascade | 2026-10-06
- `oc_b1shape` | corr-aware sizing shapes 1/(1+n) | CLOSED | keep S1; 5498 fills | 2026-10-06
- `oc_bookic` | book loss-carrier anatomy | DIAGNOSTIC | 5y +2.2787, no losing year gross | 2026-10-06
- `kelly` | distributional Kelly/mean-var rung sizing | PROMISING screen | V2 +4.720, Sharpe up | 2026-10-06
- `crashrisk` | market-state crash-risk dial | CLOSED | Step4 FAIL, DD -0.4pp max | 2026-10-06
- `kronos` | Kronos zero-shot forecasts | DIAGNOSTIC (leak) | BOOK IC neg; DIP V1 +2.52 (leak caveat) | 2026-10-06
- `oc_papercmp` | paper bots vs plan_v376 parity | DIAGNOSTIC | bot -0.08pp, 2 entries | 2026-10-06
- `oc_lots` | Bybit lot/min-notional feasibility | DIAGNOSTIC | >=99% only at A20000 | 2026-10-06
- `oc_plateau` | plateau around D17BF | DIAGNOSTIC | ref 5.425/18.33/16.90; F30 DD22.1 breach | 2026-10-06
- `oc_topbook` | live top-of-book loader (no outcomes) | DIAGNOSTIC | patchy but loadable, 9910 1m rows | 2026-10-06
- `oc_deepcheck` | TRUE vs FIFO deep-rung reconciliation | METHOD | deep TRUE +38.2 mix% | 2026-10-06
- `bot_bookgap` | book gap + exit-count fix | KEPT fix | plan-divergence; dust fixed | 2026-10-06
- `oc_signedfunding` | signed funding side row + NaN fix | METHOD | gate exact; side row only | 2026-10-06
- `bot_parity_adopt` already listed above (duplicate guard)
- `ops_liveparity` | live paper-bot parity vs Binance 1m | DIAGNOSTIC | eq ~4999.8, 0 dip/3-5 book fills | 2026-10-06
- `ops_enginespeed` | engine_user speed + engine_fast proof | DIAGNOSTIC | 1.88x/1.57x bit-exact | 2026-10-06
- `ops_kaggleengine` | generic Kaggle CPU engine bundle | DIAGNOSTIC | 6/6 pass, G2 5.41/16.91/16.82 | 2026-10-06
- `r2_4p_robust5` | R2-4P friction robustness S1-S5 (no PLAN) | DIAGNOSTIC | base 4.820/DD25.05/23.08; S1/S4/S5 breach | 2026-10-06
