# FACTCHECK owner docs VI — 2026-10-06 (audit_ownerdocs)

Scope: `docs/OWNER_SUMMARY_VI.md`, `docs/QUICKSTART_VI.md`, `docs/BOT_RUNBOOK_VI.md`,
`docs/TESTNET_PLAN_VI.md`, `docs/DEPLOYMENT_PLAN_VI.md`.
Method: every number with a `[source]` opened at its source
(`research/tournament/<n>/REPORT.md` or `results.json`, `research/diagnostics/<n>/…`,
`research/data_fetch/bybitq/…`, `docs/…`); rounding to shown precision allowed.
Commands checked via `--help` of each script (no trading command run). Git untouched, no commits.
Totals: **~125 OK**, **3 MISMATCH**, **2 SUPERSEDED/CONTRADICTED**, **1 STALE command**,
**3 text-vs-command contradictions**, **2 wrong-path refs**, **3 wrong code-line refs**
(details below). Table lists every MISMATCH / SUPERSEDED / NO SOURCE / STALE item in full;
OK items are counted per group with representative rows.

## 1. Number fact-check (claim → source → status)

| # | Doc:line | Claim | Source | Source value | Status |
|---|---|---|---|---|---|
| G1 | OWNER:4; RUNBOOK:3; QUICK:7,14; DEPLOY:285 | G2 = R2B1D17BF + dip-cap 2x (v421): 5.41 %/mo, worst 2.588, DD 16.91 / full 16.82 | `research/tournament/oc_frontiercarry/results.json` (official G2); REPORT:75-76 + :51-52 (chained 16.91 vs official 16.82) | 5.41 / 2.588 / 16.91 / 16.82 | OK |
| G2 | OWNER:4,7; QUICK:19; DEPLOY:70-73; RUNBOOK:26,129 | D17BF no-cap 5.43, DD 18.3; gap −10% worst minute 58% → 33.5% with 2x cap | `oc_frontiercarry/results.json` v411 5.425/2.831/18.33; `oc_gapstress/REPORT.md:48` max 58.3/39.1/33.5 | 5.43 / 18.3 / 58%→33.5% | OK |
| G3 | OWNER:17 | D13BF 4.97, DD 14.98/14.86; friction DD 15.51/15.08/15.62 | `research/diagnostics/oc_d13robust/ROBUST.md:6-7,32-34,87,90,93` | 4.971/14.98/14.86; S1 15.51 S2 15.08 S3 15.62 | OK |
| G4 | OWNER:18; DEPLOY:307,339 | MANUAL M5_human 3.73 (dev4 3.66, recent 3.99), DD 17.9/17.8, win 64.8%; M5+carry f=0.50 best 3.993 (equity-level 3.765) | `research/diagnostics/oc_manualcap/REPORT.md:18,26`; `research/tournament/oc_manualcarry/REPORT.md:55`; `oc_carrycombo/REPORT.md:42` | 3.73/3.66/3.99/17.9/17.8/.648; 3.993; 3.765 | OK |
| G5 | OWNER:16,57-58,69; QUICK:61; RUNBOOK:145; DEPLOY:366-367,380 | Saturation max ~5.9/mo at DD>17.5 (D20B11 5.894/21.21); G2K20 5.874→5.989 (17.79→17.66); D13 4.957→5.091 (15.00→14.87) | `oc_saturation/REPORT.md:30-36,118`; `oc_frontiercarry/REPORT.md:58,92` | as claimed | OK |
| G6 | OWNER:61-62; DEPLOY:372-373 | v428 C1 dev 1.927/1.768/3.191/7.590 mean 3.593 DD 19.17 vs deployed book 5.601/16.91 | `research/parallel/rounds/parallel-20260906-r2/v428/result_manifest.json:32-76` | bit-identical | OK |
| G7 | DEPLOY:10 | BOT R2-4P (v376) 4.8, yearly 2.0/3.8/4.0/10.6/3.9, DD 25 / full 23.08 | `research/diagnostics/r2_4p_robust5/REPORT.md:10,17` | 4.820; 1.956/3.765/4.005/10.633/3.949; 25.05 | OK |
| G8 | DEPLOY:11-12 | v411 5.43 (Bybit 4.97, delay-15' 5.24); R2B1D18 5.45 / R2B1D16 5.14 | `oc_frontiercarry/results.json` v411; `v421/result_manifest.json:172` S5 4.88 (see K4) | 5.425; delay row per v421 manifest | OK |
| C1 | OWNER:6; QUICK:15; DEPLOY:287-293 | G2+carry f=0.25 year-start 5.533/2.736/16.78; f=0.50 5.654/2.881/16.64; roll-only f=0.25 5.413/2.647/16.78 (close 15.60/marked 16.34); f=0.50 5.418/2.705/16.65/15.86 | `oc_carryfric/REPORT.md:72-73,72-88`; `oc_carrycombo/REPORT.md:32-33` | all 12 friction cells + 4 combo cells identical | OK |
| C2 | OWNER:6-7; QUICK:15; DEPLOY:291-293,380 | Sleeve +0.12pp account (+0.21%/mo allocated); frontier +0.11..+0.14 avg +0.13; DD −0.1..−0.3pp | `oc_carryfric/REPORT.md:72,104,112-113`; `oc_cashcarry/REPORT.md:38-40` (+13.09% = +0.218% arith/+0.213% geom); `oc_frontiercarry/REPORT.md:35-36` | +0.123; +0.218/+0.213; +0.11..+0.14 mean +0.13 | OK |
| C3 | OWNER:7,36; DEPLOY:294-295,326-330 | UTA f=0.25 free 22.49%/IM 77.51%/0 blocked/gap −10% −28.85%; f=0.50 1.85%/98.15%/1 blocked 2025-09-25 18:00/spot 179.9%; 10x leg 32.67%; f=0.375 bound row | `oc_utamargin/REPORT.md:52-53,61-66`; `oc_utamargin2/REPORT.md:45-46,49,67,99-105` | identical | OK |
| C4 | DEPLOY:227-234; QUICK:36-38; DEPLOY:299-302 | Cashcarry sums 0.0470/0.0528/0.2960/0.1219/0.0058; BTC/ETH splits + basis row; 5y +13.09% (+0.218/+0.213); MtM −1.01/−0.71/−2.65/−0.39/−2.17%; IM rows; rule basis≥4%/front≤7d/f×equity/drag 0.275%/~4 dec/~15 tickets | `oc_cashcarry/REPORT.md:32-36,38-40,47-49,63-74`; `oc_cashcarry/PLAN.md:48,58,64-76`; `oc_carrycombo/REPORT.md:102-105` | verbatim | OK |
| C5 | OWNER:55-56,70; DEPLOY:362-364,381 | Carry audit +0.543 vs +0.497; corr −0.0909/−0.0782, 10 worst weeks +0.0097; parity 144/144, 141/144, 143/144, ETH 3.80%<4%; FAR 1.07064/0.523436, inv 0.931737/0.497293; topup −0.011209/−0.007952 | `carry_audit/COMPARISON.md:62`; `oc_carrycorr/REPORT.md:19-23`; `oc_carryparity/REPORT.md:19,36,39-42`; `oc_carryfar/REPORT.md:24-26,40-42`; `oc_carrytopup/REPORT.md:34-35,50-51` | verbatim | OK |
| C6 | DEPLOY:29; OWNER:40-41 | Capscale ≥5000 book 0.9990/0.9995 dip 0.9780/0.9985/0.9967; 2000 book 0.9585/0.9704 dip 0.9269/0.9950/0.9804; 10000 ~100%/99.92% | `research/diagnostics/oc_capscale/REPORT.md:34-36` | identical | OK + PATH-NOTE (no `research/tournament/oc_capscale`; source is diagnostics copy) |
| K1 | DEPLOY:59-61; OWNER:10,12; QUICK:16; RUNBOOK:136 | Rolling49: 2.73/3.25/4.89/8.88/11.71; DD 8.3/13.5/18.3/18.7; 49%/61%/100%, no losing window | `oc_rolling17/results.json` R2B1D17BF summary | 2.725/3.252/4.887/8.875/11.712; 8.26/13.52/18.314/18.69; 0.4898/0.6122/1.0/0 losing | OK |
| K2 | DEPLOY:53-55; OWNER:10,12-13; QUICK:17; RUNBOOK:136 | Bootstrap 10k-y: median ~5.1 (1.5/10.3); ~52% ≥5%; P(DD>20%) ~11%; P(lose) ~0.7%; DD 14.5/p95 22.6 | `oc_mcdd/results.json` R2B1D17BF bootstrap | 0.05118; 0.01470/0.10317; 52.18%; 0.1098; 0.0072; 0.14472/0.22566 | OK |
| K3 | DEPLOY:63; OWNER:13; QUICK:18; RUNBOOK:136 | KPI: 41% months ≥+5%, 72% non-loss, streak 2; win book 51.5 / dip 68.7 / all 65.5 (as G2 numbers) | `research/tournament/oc_kpi/results.json` (D17BF no-cap): 0.4098/0.7213/streak 2/0.515/0.6869/0.6546 vs `oc_kpi_g2/results.json` (G2): 0.4098/0.7049/streak 4/0.5154/0.6858/0.6533 | 72% + streak 2 + 68.7/65.5 are D17BF values; G2 is 70.5%, streak 4, 68.6/65.3 | **MISMATCH** (stale-variant mix; 41%/51.5% match both) |
| K4 | QUICK:15; DEPLOY:76,94-95 | Bybit drag ~0.5pp/mo; Bybit-price row ~4.9%/4.88% | `v421/result_manifest.json:172` S5 4.88/18.11; `oc_bookvenue`, `oc_venuegap/REPORT.md:24,65,72` | magnitude OK | **MISMATCH (location)**: "drag sits in dip ladder, not book" contradicts `oc_venuegap` (dip gap small, must live in BOOK leg) and `oc_bookvenue` (NOT book execution; residual sizing/valuation). Magnitude ~0.5pp OK; location statement SUPERSEDED by the two venue reports |
| K5 | DEPLOY:87-89; QUICK:18 | Worst week −12.3% 2023-12-27 (DD 13.9, recover ~54d; no-cap −14.7/16.3); −9.7/−9.6/−8.6/−8.9; FTX −2.2; LUNA −3.0 | `oc_stresshist/results.json` worst5 + named | −12.34/13.92/54.12d; −14.73/16.27; −9.69/−9.62/−8.63/−8.89; −2.19/−2.96 | OK |
| K6 | DEPLOY:352-356; OWNER:50-52; QUICK:19,60; RUNBOOK:129 | Crash2020 mix ~−16.1% (maxLoss 16.08/endEq 0.901), worst phase −21.85% (DD 22.30); 2021-05-19 mix ~−10.0% | `oc_crash2020/results.json` | 16.081/0.901; 21.847/22.296; 9.958 | OK |
| K7 | DEPLOY:357-360; OWNER:53-54; QUICK:51-52; RUNBOOK:92,109 | Outage routine 2.4/1.7/0.9% of 5y dip; worst-hour +0.684 ~9% | `oc_outage/results.json` summary | 2.434/1.739/0.927%; 0.683793/7.718 = 8.86% | OK |
| K8 | DEPLOY:319-325; OWNER:10,32-35; QUICK:14 | Clockluck 24 offsets 4.55/9.67/7.12/7.13/1.54; deployed 9.67/7.54/8.76/4.90; mean 7.72 vs 7.12 gap −0.59; yearly gaps +0.00/−0.03/−0.42/+0.01/−0.15; ratios 1.002/0.958/0.798/1.004/0.779; adj 2.593/3.233/5.453/10.691/4.401; random-clock ~5.24 vs 5.41 | `research/diagnostics/oc_clockluck/results.json` part2/part3 + REPORT:52-61 | verbatim (method self-labelled APPROXIMATE/proxy) | OK |
| K9 | DEPLOY:345-348,369-371; OWNER:59-60; QUICK:47; RUNBOOK:138 | Edgedecay slope +0.067 CI [−0.158;+0.160]; first30 5.59 vs last30 6.61, last6m 7.38; gates 1.61 (median 5.44) / 0.434 (median 0.488) | `research/diagnostics/oc_edgedecay/results.json` trend + REPORT:32-36,80-81 | 0.0668; [−0.1576;+0.1596]; as claimed | OK |
| K10 | DEPLOY:115-121 | Seedengine 5.343/5.371/5.382/5.410/5.430 mean 5.387 std 0.034; worst 2.588 all; DD 16.54..17.03 | `research/diagnostics/oc_seedengine/results.json` | identical | OK |
| K11 | DEPLOY:125-131 | Stopslip 1699 = 773+926; medians −4.6/−1.6; p90 +146/+197 p99 +495/+738 max +813/+1347; 7.2% Bybit-no-touch | `oc_stopslip/results.json` pooled + REPORT:98-100 | −4.59/−1.59; 145.59/196.85; 494.91/738.05; 812.61/1346.98; 7.2% | OK |
| K12 | DEPLOY:135-139 | VIP +0.1117→5.7183, +0.1590→5.7657 (base 5.6066); tau 22.98x; 435241/1088101 USDT | `oc_vipfees/results.json` five_year | identical | OK |
| K13 | DEPLOY:99-101,162-174,105-111,382,387-388 | Underwater 47 ep, median ~9d p90 63d max 149d, depths 16.8/14.7/13.8/13.2; phasedisp singles 3.102–6.923 DD≤43.55, phase3-2023 −2.431; blendsens flat ≤0.7pp; liqcheck 3230 rows gaps 7.26h+4.70h burst ±0.5%; spreadcost 1097819 rows −0.275/−0.176 DD +0.012–0.016; planparity 0 mismatch; capfix 0.0710 dip219/book83, C_on 0.0320, A_off 0.0358 | `oc_underwater`, `oc_phasedisp/REPORT.md:12-18`, `oc_blendsens/REPORT.md:21-29,53`, `oc_liqcheck/results.json`, `oc_spreadcost/REPORT.md:6,68,79`, `oc_planparity/REPORT.md:3`, `diagnostics/bot_capfix/REPORT.md:5,14-16,26-27`, `carry_audit/COMPARISON.md:4,62` | all match (8.71d→9d; 13.18→13.2 rounding OK) | OK |
| K14 | OWNER:44-46,63-65; DEPLOY:337-341,374-376 | Closed screens one-liners (linvinv 2.55pp; marktrig 4/5−2022/−0.227/+0.057; discsniper −0.5291; manual2coin 3.73/3.24/3.39/24.3; phase8 4.960/17.98/17.32; carrytopup; bidttl −1.339; calendar; depthtilt −0.066; tpfill 0/22312; expirybook 2.061253→2.077167 etc.) | respective `oc_*` REPORTs | verbatim per reports | OK |
| K15 | OWNER:79; DEPLOY:390 | Prepush 253 commits / 752 files / SAFE TO PUSH; backend `GET /api/carry` restart-once | `docs/opencode/PREPUSH_AUDIT_20261006.md:3,20,30` | 253 commits; 752 files; SAFE TO PUSH | OK |
| K16 | OWNER:24,43; QUICK:37,40; DEPLOY:304 | Prospective `too early`; paper_d17bfg2c started 2026-10-06 07:19, BTC-25DEC26 basis +5.42%, ETH skip 3.7%, alloc −0.15% | `docs/opencode/PROSPECTIVE_20261006.md:40,42,46` | `too early`; +5.42%/yr; 3.7%<4%; alloc −0.15% | OK |
| K17 | OWNER:4; DEPLOY:285 | v421 "audited yes" (FINAL_REPORT:52 shared) | `oc_frontiercarry/REPORT.md:162-163` | v421 `audit.passed false`; identical twin v422 audited yes | **MISMATCH (labelling)**: numbers identical, audit label overstates v421 alone |
| K18 | QUICK:30 | "checklist V1–V9 trong TESTNET_REVIEW" | `docs/opencode/TESTNET_REVIEW_20261006.md:95-105` | V1..V9 checklist present | OK (but see §4: review verdict itself is SUPERSEDED, "not ready until V1–V4" + §5 guard claim predates bot_testnetfix) |

## 2. Numbers with NO SOURCE (flagged, not necessarily wrong)

- OWNER:7 "riêng phần vốn carry ~+0,21%/tháng" — has `[oc_carryfric]`; geometric +0.213 rounds to 0.21: sourced, OK (listed for clarity).
- OWNER:10 "trung vị ~5 %/tháng … Nói gọn: 4–6 %/tháng [FINAL_REPORT_VI]" — range is editorial rounding of 4.89/5.1 medians: OK as gloss, no exact source needed.
- OWNER:11 "năm tệ nhất lịch sử BOT là 2,83 (G2 là 2,588)" — 2.83 cites `[FINAL_REPORT_VI]` (pre-cap variant worst); G2 2.588 OK. No separate mismatch.
- OWNER:24 "bot/paper mới ~0,2–1,1 ngày" — cites `[PROSPECTIVE_20261006]` (day-1 ages): OK.
- OWNER:32-33 dip-clock offset table (24 offsets, pct 100/58/88/8%) — cites `[oc_clockluck]` only at line 35 tail; numbers verified OK (K8).
- QUICK:32 "5 paper runner" / RUNBOOK:97 "5 runner paper" — runner inventory (paper, d17bf, d17bfg2, g2k20, d13bf per PAPER_DAY1 + d17bfg2c replacing/supplementing); count wording drifts between docs (5 vs named sets); no P&L impact. Minor consistency note, not a number mismatch.
- DEPLOY:48 "IM tối đa 68% … free ≥32% … sập −29% … ~300%/73–76%" — inside `oc_margin` section citing runbook; detailed margin quantiles not re-verified here (source `oc_margin`/`oc_utamargin` not fully reopened for these cells). Flagged as NOT RE-CHECKED, not failed.
- Generic operational thresholds repeated without brackets (4h30m plan age, 5-min cycle, 20s window, 8-week/14-day/56-day clocks, DD 20/15%,/varnothing percentiles) all cite `[BOT_RUNBOOK_VI]`/`[DEPLOYMENT_PLAN_VI]` at section heads: treated as sourced.

## 3. Sources that do not exist / path notes (all resolvable, none blocking)

- `[oc_capscale]` → no `research/tournament/oc_capscale`; real source `research/diagnostics/oc_capscale/REPORT.md` (numbers identical). PATH-NOTE.
- `[bybitq]` → no `research/{tournament,diagnostics}/bybitq`; real source `research/data_fetch/bybitq/REPORT.md` (+ `oc_carrycombo/REPORT.md:77,86` deliveryFeeRate 0). PATH-NOTE.
- `[oc_carrycombo]`/`[oc_carryfric]` etc. cited bare (no path) — all resolve under `research/tournament/<name>/`. OK.
- `[FINAL_REPORT_VI]` / `[DEPLOYMENT_PLAN_VI]` / `[BOT_RUNBOOK_VI]` / `[QUICKSTART_VI]` = sibling docs in `docs/`; self/cross citations are internal consistency claims, verified against research sources above where numeric.
- `[docs_update6 \`oc_clockluck\`]` (OWNER:9) is not a file path; resolves to DEPLOYMENT docs_update6 section + `research/diagnostics/oc_clockluck/`. PATH-NOTE.
- `[restart_all.sh]` / `[carry_paper.py]` / `[BOT_EXECUTION.md …]` = `scripts/restart_all.sh`, `scripts/carry_paper.py`, `docs/BOT_EXECUTION.md`. OK.
- `[artifacts/bot/paper_d17bfg2c; docs/BOT_EXECUTION.md]` (OWNER:43) — local artifacts dir EXISTS (actions.jsonl/exchange.json present); not a research source but a live-paper caveat. OK.
- `[PREPUSH_AUDIT_20261006]` / `[PROSPECTIVE_20261006]` / `[PAPER_DAY1_20261006]` / `[TESTNET_REVIEW_20261006]` = `docs/opencode/<name>.md`. All exist. OK.
- `check_parity.py` (DEPLOY:387): `scripts/check_parity.py` does NOT exist — real file `research/tournament/oc_carryparity/check_parity.py` (takes no argparse flags). WRONG PATH (see §5).

## 4. Statements contradicting / superseded by later reports

- S1 — **KPI attached to G2 (MISMATCH, §1 K3)**: 72% non-loss months, streak 2, dip 68.7 / all 65.5% are `oc_kpi` (D17BF no-cap) values, not `oc_kpi_g2` (70.5%, streak 4, 68.6/65.3). Fix: use `oc_kpi_g2` row for G2 claims or label as D17BF.
- S2 — **Venue-drag location (CONTRADICTED, §1 K4)**: "nằm ở thang dip, không ở book" contradicts `oc_venuegap` (dip gap small; drag must live in BOOK leg) and `oc_bookvenue` (NOT book execution; residual sizing/valuation). Magnitude ~0.5pp stands.
- S3 — **`TESTNET_REVIEW_20261006` §5 "risk_guard NOT wired" SUPERSEDED**: review predates `bot_testnetfix`; guard is now wired ON-default at testnet/live (`bot/run.py:1290`, verified). Review verdict "not ready until V1–V4" is likewise overtaken by the fix + 2026-10-06 paper/testnet runs; do not use the review as a live gate without re-review.
- S4 — **v421 "audited yes" labelling (MISMATCH, §1 K17)**: v421 `audit.passed false`; twin v422 audited yes, numbers identical. Fix label to "v421/v422 (twin, v422 audited)".
- S5 — **TESTNET:13 / RUNBOOK:26 "`--adopt-fresh` TẮT for testnet/live" vs commands WITH `--adopt-fresh`** (RUNBOOK:40,45; TESTNET:58): text-vs-command contradiction (see §5 C2). One side must change.
- S6 — **TESTNET:15 "`--interval` default 20s" vs command `--interval 25`** (TESTNET:58): text-vs-command contradiction (see §5 C3).
- S7 — **DEPLOYMENT:21 bare paper command** (`python -m bot.run --mode paper --equity 5000`, no G2 flags): STALE pre-freeze command, superseded by frozen command (QUICKSTART:27 / RUNBOOK:33). Must be replaced.

## 5. Command consistency (`--help` evidence; no trading command run)

`bot.run --help` flags: `--mode {dry,paper,testnet,live} --plan --equity --once --interval
--risk-mult --corr-size --dip-mult --bear-book --dip-cooldown-h --dip-sl-coin --dip-gross-cap
--adopt-fresh --tag --no-risk-guard --risk-guard --carry-f --maint-start --maint-end`
(defaults: `--mode dry`, `--equity 1000.0`, `--interval 20.0`, overlays off; `--adopt-fresh`
`store_true` default OFF; guard ON at testnet/live, OFF at paper/dry per `run.py:1290`).

| # | Command (as in docs) | Location | Flags | Status |
|---|---|---|---|---|
| 1 | `-m bot.run --once --equity 5000 --corr-size --dip-mult 1.7 --bear-book --dip-gross-cap 2.0` | QUICK:26 (dry) | all exist | OK but NOTE: no `--carry-f` → different pipeline from RUNBOOK dry |
| 2 | `-m bot.run --mode paper --equity 5000 --corr-size --dip-mult 1.7 --dip-gross-cap 2.0 --bear-book --adopt-fresh --carry-f 0.25 --interval 25 --tag d17bfg2c` | QUICK:27, RUNBOOK:33 (paper) = `restart_all.sh:62` ground truth | all exist | OK |
| 3 | `-m bot.run --once --equity 5000 --corr-size --dip-mult 1.7 --bear-book --dip-gross-cap 2.0 --carry-f 0.25` | RUNBOOK:30, TESTNET:52 (dry) | all exist | OK |
| 4 | `-m bot.run --mode testnet --corr-size --dip-mult 1.7 --bear-book --dip-gross-cap 2.0 --adopt-fresh --carry-f 0.25 --interval 25 --tag tnetg2c` | RUNBOOK:40, TESTNET:58 | all exist, no `--equity` (correct: dry/paper-only) | OK flags; contradicts §4 S5/S6 prose |
| 5 | `-m bot.run --mode live … --tag liveg2c` (+ `BOT_ALLOW_LIVE=yes-real-money`) | RUNBOOK:45 | all exist | OK flags |
| 6 | `python -m bot.run --mode paper --equity 5000` | DEPLOY:21 | exist | **STALE** — missing all frozen G2 flags; replace with #2 |
| 7 | `scripts/carry_paper.py --once --equity 5000 --f 0.5 --tag carry` | QUICK:40, RUNBOOK:80, DEPLOY:303 | `--once --equity --f --tag` (+`--base --interval --state-dir`) | OK |
| 8 | `scripts/bot_preflight.py --mode testnet` / `--mode live` | QUICK:29, RUNBOOK:36-37, TESTNET:44 | `--mode {testnet,live}` (+`--plan`) | OK (cp1252 `--help` crash is a pre-existing i18n bug, not a flag error) |
| 9 | `scripts/daily_status.py` (bare) | QUICK:28, RUNBOOK:53, TESTNET:69, DEPLOY:22 | none (`--md --root --fast --json` only) | OK |
| 10 | `scripts/bot_health.py <dir>` | QUICK:28, RUNBOOK:54, TESTNET:70 | positional `dirs` | OK |
| 11 | `scripts/paper_report.py <dir>` | RUNBOOK:55 | positional `dirs` | OK |
| 12 | `scripts/prospective_scorecard.py` (bare) | RUNBOOK:56, DEPLOY:25 | no argparse flags | OK |
| 13 | `scripts/paper_divergence.py <dir>` | RUNBOOK:57, DEPLOY:27 | positional `dirs` | OK |
| 14 | `scripts/alert_watch.py --every 300` / `--once --no-toast` | RUNBOOK:66,68, DEPLOY:389 | `--every --once --no-toast` (+`--interval --root --log`) | OK |
| 15 | `scripts/weekly_report.py` (bare) | RUNBOOK:74 | none (`--root --out --now`) | OK |
| 16 | `scripts/snapshot_untracked.py [--dry-run] [--restore-list ZIP]` | RUNBOOK:117,119,121 | both exist | OK |
| 17 | `bash scripts/restart_all.sh [--dry-run] [--only bots\|backend\|carry]` | OWNER:28, QUICK:32, RUNBOOK:101-106, DEPLOY:312 | `--dry-run`, `--only` | OK with syntax caveat: literal pipe is shell shorthand; valid calls are `--only bots` / `--only backend` / `--only carry` |
| 18 | `.\run_backend.ps1 -Status/-Background/-Stop` | QUICK:24, RUNBOOK:16-18 | all switches exist | OK |
| 19 | `--maint-start/--maint-end` + `maintenance.json` | QUICK:51, RUNBOOK:89, TESTNET:89 | both in `bot.run --help`; path `<state-dir>/maintenance.json` (`run.py:271`) | OK |
| 20 | `check_parity.py` | DEPLOY:387 | `scripts/check_parity.py` MISSING (exit 2); real `research/tournament/oc_carryparity/check_parity.py` takes no flags | **WRONG PATH** |

Deployment-flag matrix (must differ ONLY by `--mode`/`--tag`): `--corr-size/--dip-mult 1.7/--bear-book/
--dip-gross-cap 2.0/--carry-f 0.25/--interval 25` identical across frozen paper/testnet/live — OK.
`--equity 5000` paper/dry-only, absent testnet/live — CORRECT per design. `--tag` distinct per mode — OK.
Deviations: **C1** QUICK dry (#1) lacks `--carry-f` vs RUNBOOK dry (#3) — two different dry pipelines.
**C2** `--adopt-fresh` ON in testnet/live commands but prose says TẮT (RUNBOOK:26, TESTNET:13).
**C3** `--interval 25` in command but prose says default 20s (TESTNET:15). **C4** DEPLOY:21 stale bare
command (S7). Code-line refs: `run.py:576-577` (BOT_ALLOW_LIVE gate) HALF-WRONG — gate is at
`run.py:1282-1283`, 576-577 is `_carry_cycle` internals; `run.py:117-120` (hedge) WRONG — real
`run.py:250-253`; `bybit_v5.py:302-323` (cross/leverage) WRONG RANGE — only auto-call is hedge at
`bybit_v5.py:395-396`, no leverage/margin setters exist (claim itself TRUE). `bot_preflight.py:246-380`
ref CORRECT (9 rows as claimed). Behavior prose verified TRUE: guard defaults, `--adopt-fresh` default
OFF, PostOnly entries + `postonly_reject` retry, `maintenance.json` per-runner path.

## 6. Counts

- OK numeric checks: ~125 (groups G1-G8, C1-C6, K1,K2,K5-K16,K18 + §5 rows 1-5,7-19).
- MISMATCH: 3 (K3 KPI variant mix; K4 venue-drag location; K17 v421 audit label).
- SUPERSEDED / contradicted: 2 (S2 venue location — same as K4; S3 testnet-review guard wiring) + 1 STALE (S7/DEPLOY:21) + 3 text-vs-command (S5,S6,C1).
- NO SOURCE (true gaps): 0 blocking; §2 lists editorial glosses + 1 not-re-checked margin cell (DEPLOY:48).
- Missing sources: 0 blocking (2 path-notes + 1 wrong path `scripts/check_parity.py`).
- Commands with unknown flags: 0 (all flags exist; 1 wrong path, 3 wrong code-line refs, Williamsburg i18n `--help` crash noted).
