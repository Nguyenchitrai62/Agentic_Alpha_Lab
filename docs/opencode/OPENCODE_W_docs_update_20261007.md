# OpenCode task docs_update_20261007 - record the 2026-10-07 wave in the closed-directions map + a short owner summary
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. EXCEPTION (leader-assigned docs task): you may edit `docs/CLOSED_DIRECTIONS.md`
(append only - a new section "## 11. 2026-10-07 wave" with one row per item in the existing row format, plus updating the "Still OPEN" bullets
for the items listed below) and CREATE `docs/SUMMARY_FOR_OWNER_20261007b_VI.md`. Nothing else. Every number must be copied from the cited
REPORT / COMPARISON / doc (cite the path in brackets); do not invent or round differently.

## Items (read each source)
CLOSED: research/tournament/oc_relflush, oc_tailhedge, oc_ripcont, oc_manualsplit, oc_stablegate, oc_putwrite, oc_vrpgate (REPORT.md each).
VRP straddle family (one combined row + detail): oc_vrpstraddle (REPORT), audit_vrpstraddle (COMPARISON, PASS-WITH-NOTES), oc_vrprobust
(REPORT = leader note), oc_vrpconsistent (REPORT), oc_vrpstrangle (REPORT): status = NOT DEPLOYED; headline +1 pp was DVOL pricing bias (traded
7d ATM IV ~0.87 x DVOL); consistent repricing: standalone loses, overlay +0.14 pp at r 0.87, -0.35 at r 0.80; prospective Bybit paper ledger
(scripts/straddle_paper.py, if it exists) is the only remaining evidence.
DIAGNOSTIC / KEPT: oc_presample (dip sleeve on 2017-2020 pre-sample: no losing year, 2018 2.50 %/mo DD 8.4), oc_paperpower (8 weeks weak;
26 weeks recommended), data_hlfunding (PARKED: 2023-05+ only), oc_ideascan3 (docs/opencode/IDEAS_20261007c.md), ops_bybitoptions
(docs/opencode/BYBIT_OPTIONS_20261007.md).
OPS: bot exit-cancel bug fixed in commit cb14cb7 (docs/opencode/BOT_EXITSOAK_20261007.md, docs/opencode/PAPERFIX_20261007.md); scorecard
correction window (docs/opencode/SCORECARDFIX_20261007.md); keepalive script (docs/opencode/KEEPALIVE_20261007.md); OOS week 2
(docs/opencode/OOS_WEEK2_20261007.md).
PENDING (mark as running): oc_kronoshidden (Kronos dip tilt, post-release year), Deribit strike-level fetch, bot_soakinv.

## Owner summary (Vietnamese, <= 60 lines, plain language, honest)
1. What changed today for the money (nothing deployed changes: G2 + carry stays; paper bots fixed and restarted). 2. The bot bug in 3 lines
and why it matters for testnet/live. 3. Owner actions in order: run `.\scripts\register_keepalive.ps1 -Status` then `-Register`; keep paper
running; testnet per docs/TESTNET_PLAN_VI.md; the evidence horizon (26 weeks for a confident go-live; 8 weeks allows at most a small pilot -
oc_paperpower numbers). 4. What failed today (one line each). 5. What is still being tested.
