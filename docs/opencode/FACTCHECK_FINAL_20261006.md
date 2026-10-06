# Fact-check FINAL_REPORT_VI.md — 2026-10-06 (blind audit, read-only)

Target: `docs/FINAL_REPORT_VI.md`. Method: for every number citing a source in
brackets, opened that source (`research/tournament/<name>/REPORT.md` +
`results.json`, `research/diagnostics/<name>/REPORT.md` + `results.json`,
`research/parallel/rounds/parallel-20260906-r2/vNNN/`, `docs/...`,
`docs/opencode/...`). Rounding to shown precision = OK. Did NOT edit the report.
No commits. Git was read-only.

OK-check count: ~109 checks OK (Sec2-base ~27, carry/margin ~22, friction/clock/crash
~25, menu/goals ~21, methods/closed/paper ~14). Details below list ONLY mismatches /
missing / superseded. Everything else checked OK.

| Line | Claim in FINAL | Source opened | Source value | Status |
|---|---|---|---|---|
| 52 | "v421/v422 audited yes" | `research/tournament/oc_frontier/REPORT.md:89,95`; `oc_frontiercarry/REPORT.md:162-163`; `oc_frontiercarry/results.json:2487` | v421 `audited NO / false`; only twin v422 `yes` | MISMATCH |
| 58 | "G2 KPI ... n=4955/21389/26344" | `research/tournament/oc_kpi_g2/REPORT.md:75`; `results.json:391-402 vs 910-921` | 4955/21389/26344 = BF (D17BF) column; G2 pooled = 5064/21513/26577 | MISMATCH |
| 60 | "G2 ... không trần ~7.1x [oc_kpi; oc_margin]" | `research/tournament/oc_margin/results.json` (G_max 3.4113; phases <=3.78); `oc_kpi/results.json:503` combined 6.4007 | No 7.1x in any cited results.json; only REPORT-text "(không trần ~7.1x)" in `oc_margin/REPORT.md:95` | NO SOURCE |
| 85 | "trễ 15' 5.24/~16.9 [DEPLOYMENT_PLAN_VI]" | `docs/DEPLOYMENT_PLAN_VI.md:11`; `RESEARCH_MAP_DRAFT_20261006.md:6` | Return 5.24 OK; "~16.9" has no exact source (nearest G2 leg 5.21/16.91 DEPLOYMENT_PLAN_VI:75) | NO SOURCE (DD part) |
| 86-87 | "S4 5.11/20.0 ... Bybit 4.97/19.9 ... trễ 30' 4.68 [DEPLOYMENT_PLAN_VI]" | `docs/DEPLOYMENT_PLAN_VI.md:75-76`; `docs/opencode/RESEARCH_MAP_DRAFT_20261006.md:6`; `oc_carryfric/REPORT.md:83,86` | Numbers exist only in research-map (`stop-slip 5.11/DD20.0`, `Bybit 4.97/19.9`, `lat30 4.68`); DEPLOYMENT_PLAN_VI gives only G2 legs (4.90/17.31, 4.88/18.11, 4.58/17.32) | MISMATCH (wrong source cited) |
| 94 | "Vốn 10k 100/98; 5k 96/94; 2k 80/81 [DEPLOYMENT_PLAN_VI]" | `docs/DEPLOYMENT_PLAN_VI.md:29`; `research/diagnostics/oc_capscale/REPORT.md:34-35` | Quoted verbatim (old oc_lots); newer G2 `oc_capscale` gives higher placeability (5000 book 0.9990/0.9995 etc) | SUPERSEDED (accurate quote, newer source exists) |
| 102 | "phase3 2023 -2.431/DD 43.23 trong khi mix +2.588" | `research/tournament/oc_phasedisp/results.json`; `oc_clockanat/results.json:108` | Phase3 2023 -2.431/43.23 OK; mix-2023 = 6.045/15.81 (mix_end_eq 2.0224); 2.588 = mix worst/2021, not mix-2023 | MISMATCH |
| 113-114 | "Mất 1-3h cắt 4h không cộng dồn tail khi mix 4 pha [research-map]" | `RESEARCH_MAP_DRAFT_20261006.md` + `...b.md`; `oc_outage/REPORT.md`; `DEPLOYMENT_PLAN_VI.md` | No such statement anywhere; oc_outage tests only weekly-2h/monthly-6h/quarterly-24h/adversarial-10h | NO SOURCE |
| 125 | "D13 carry ... 16.54 -> 16.40 (no label)" | `research/tournament/oc_frontiercarry` table; `oc_frontier` v409 row | 16.54/16.40 = chained-reset convention; official run.log full-path v409 = 16.36; FINAL omits convention here | MISMATCH (missing convention label) |
| 129-130 | "49 cửa sổ ..." (no config named) | `research/tournament/oc_rolling17/`; `docs/DEPLOYMENT_PLAN_VI.md:57-60` | Numbers are v411 R2B1D17BF rows, not G2; FINAL names no config | MISMATCH (scope misattribution) |
| 133 | "chuỗi lỗ dài nhất 2 tháng (G2 4 tháng ...) [oc_kpi]" | `research/tournament/oc_kpi/REPORT.md:36-39`; `oc_kpi_g2/REPORT.md:42-44` | 2mo = BF; G2 4mo comes from `oc_kpi_g2`, not the cited `oc_kpi` | MISMATCH (incomplete citation) |
| 139-141 | "dip stop/timeout -7..-10 ... short bù +6.8" | `research/tournament/oc_ddanat_g2/` | -7..-10 = net dip after +10..+13 TP offset, not gross stop/timeout; +6.8 = book-shorts sum (+0.45+1.73+1.92+2.69), not BNB-short | MISMATCH (wording) |
| 145 | "W=2.588-2.83" in G2 sentence | `oc_frontier`; `oc_kpi_g2`; `oc_clockluck` | 2.588 = G2 worst; 2.83 = D17BF worst 2.831; G2 sentence should be 2.588 alone | MISMATCH (mixing configs) |
| 159 | "Tay người tốn ~0.6pp" | `research/diagnostics/oc_manualbf/` (M5_base 4.066 - M5_human 3.586 = 0.48pp; M4 0.47pp); `DEPLOYMENT_PLAN_VI.md:13` | Direction right, magnitude rounded up ~0.1pp | MISMATCH (approx) |
| 160 | Friction drag "~0.2-0.8pp [oc_frontiercarry]" | `oc_carryfric`; `oc_d13robust`; `DEPLOYMENT_PLAN_VI` | Magnitudes OK (0.20..0.84) but live in oc_carryfric/oc_d13robust, not cited oc_frontiercarry | MISMATCH (citation) |
| 175 | "pha-0 43x [DEPLOYMENT_PLAN_VI]" | `docs/DEPLOYMENT_PLAN_VI.md:16`; `RESEARCH_MAP_DRAFT_20261006.md:62` | "43x" only in research-map ("lucky phase-0 43x"); DEPLOYMENT_PLAN_VI has only generic wording | MISMATCH |
| 177,190 | "[v427 PROCESS NOTE]" | `research/parallel/rounds/parallel-20260906-r2/v427/v427_c2_rank_calibrated.py:42` | Exists only as code docstring (C2 bug dev 0.88%), not a report/audit doc | NO SOURCE |
| 184,188,196,246 | "[research-map]" (4x) | `docs/opencode/RESEARCH_MAP_DRAFT_20261006.md` + `...b.md` | No file literally named `research-map`; alias resolvable (e.g. v425 pre-register in `...b.md:33`) | NO SOURCE (inexact citation; content OK) |
| 80,82 | "[bybitq]" | search `research/tournament`, `docs` | No such directory/file exists; presumably the Bybit-availability check embedded in `oc_carrycombo` §3 | NO SOURCE (source does not exist) |
| 192 | "FAR tenor (+0.43 ...)" | `research/tournament/oc_carryfar/` | +0.43 = Binance geometric (+0.425); Bybit-inverse geometric +0.372 undisclosed | MISMATCH (selective venue) |
| 207 | "không có bot thứ 6" | `docs/opencode/PAPER_DAY1_20261006.md`; `artifacts/bot/` | True only at PAPER_DAY1 snapshot (~03:28 UTC, 5 dirs); at report time 7 dirs (paper, paper_d17bf, paper_d17bfg2, paper_g2k20, paper_d13bf + paper_d17bfg2c + paper_carry) | SUPERSEDED (stale-temporal) |
| 212-213 | "stale 355/281/52/83" | `docs/opencode/PAPER_DAY1_20261006.md` table | Matches first 4 bots; omits 5th (paper_d13bf stale=0) | MISMATCH (incomplete list) |
| 213 | "`skipped_below_minimum` 596-701 dòng/bot" | `docs/opencode/PAPER_DAY1_20261006.md` | paper 658, d17bfg2 701, g2k20 596, but paper_d17bf 0 skipped; range covers 3/5; phrasing implies all | MISMATCH |
| 216 | Parity "143/144 ... fix" | `research/tournament/oc_carryparity/` | 143/144 + ETH 3.80% fix verified; omits other headline: only 56/144 within 0.2pp/yr vs kline (88 mid-vs-last breaches) | MISMATCH (selective omission) |
| 220 | Carry cancel "fix đang làm [paper_d17bfg2c]" | `docs/opencode/OPENCODE_W_bot_carryfix.md:3-4`; `bot/run.py:185` | Event verified; `[paper_d17bfg2c]` is a data dir, not a report | NO SOURCE (weak citation) |
| 229 | Carry ops "[carry_audit]" | `research/tournament/carry_audit/COMPARISON.md` | Verdict is FAIL (20/25 basis >0.1pp, 25/25 returns >0.02pp, 4/5 years, extra BTC 2026-12-25, BTC 2026-03-27 sign flip); FINAL cites as support without disclosing FAIL | SUPERSEDED (contradiction by omission) |
| 229 | "~4 quyết định/năm (~15 vé/năm)" | `research/tournament/oc_cashcarry/` (33 entered / 25 in-window over 5y) | No source line states 4/yr or 15 tickets; arithmetic ≈5-6.6/yr | NO SOURCE |
| 227 | Testnet "V1-V9" clean | `docs/opencode/TESTNET_REVIEW_20261006.md` (V1-V9 exist) | Checklist exists, but undisclosed F1 (PostOnly documented but NOT sent; live GTC can take) and V1 (Cross/5x never set/checked by code) | SUPERSEDED (undisclosed issues) |

Sources that do not exist / cannot be opened: `bybitq` (no dir/file); literal
`research-map` (alias only); `[v427 PROCESS NOTE]` (docstring only);
`[paper_d17bfg2c]` as a report (data dir only). Spelling `oc_calendar` is correct
(`research/tournament/oc_calendar/` exists; no `oc_calender` typo in FINAL).

Numbers with no source bracket (flagged, not checked): scope line "reset 1/4 vốn
mỗi anchor", "mix trung bình 4 pha giờ"; L43-44 equity/plan flags (verified against
`docs/DEPLOYMENT_PLAN_VI.md:20-21`, `QUICKSTART_VI.md:7-10` but FINAL cites only
runbook docs); L229 "~4 quyết định/năm (~15 vé/năm)" (above).
