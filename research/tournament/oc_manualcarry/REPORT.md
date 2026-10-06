# oc_manualcarry REPORT — honest MANUAL rows + frozen cash-carry sleeve (POST-HOC)

Question: does any honest MANUAL row named in docs/FINAL_REPORT_VI reach the
MANUAL floor (>= 5 %/mo, DD < 20, book win >= 55 %) once the frozen
oc_cashcarry sleeve is overlaid at f in {0.25, 0.5}? Method: YEARLY-LEVEL
equity combination (labelled — this file says so), carry trades reused
UNCHANGED from `oc_cashcarry/results.json` (33 entered / 13 skipped / 2
incomplete, threshold 4 %/yr, fees 0.001/side + 0.00055/0.0002). No engine
reruns, one process, JSON/4h data only, no 1m. Repro:
`research/tournament/oc_manualcarry/{combine_manualcarry.py,results.json}`;
test `tests/test_oc_manualcarry.py`. POST-HOC, REPORTING ONLY: all five years
are research data; the carry rule was frozen before any combination
(oc_cashcarry PLAN pre-registered); prospective paper is the clean check.

## Bases (all from FINAL_REPORT_VI; stored equity paths in results.json meta)

- oc_manualcap/M5_human: 5y 3.728, worst 0.847, maxDD 17.94, fullDD 17.79,
  book win 64.82% (n=3744). Equity:
  `research/diagnostics/oc_manualcap/oc_manualcap_runs.pkl` row M5_human.
- oc_manualcap/M5_human_G15: 3.006 / 0.634 / 14.93 / 14.88, win 64.92%
  (n=3914). Same pkl, row M5_human_G15.
- oc_manualcap/M5_human_G10: 2.615 / 0.446 / 13.54 / 13.51, win 64.85%
  (n=3918). Same pkl, row M5_human_G10.
- oc_manualbf/M5_humanBF: 3.609 / 0.767 / 21.55 (overall; no per-year DD
  stored, no full-path DD stored), win 66.35% (n=3741). Equity:
  `research/diagnostics/oc_manualbf/oc_manualbf_runs.pkl` row M5_humanBF.
- oc_manual2/M5_humanBF_top2: 3.060 / 0.368 / 19.53 (overall; same storage
  gap), win 66.91% (n=3844). Equity:
  `research/diagnostics/oc_manual2/oc_manual2_runs.pkl` row M5_humanBF_top2.

Carry sleeve per ENTRY year (frozen sums, account units at f=0.25):
2021 +1.17% / 2022 +1.32% / 2023 +7.40% / 2024 +3.05% / 2025 +0.14%
(x2 at f=0.50). Worst 4h-close MtM at f=0.25: -0.25 / -0.18 / -0.66 / -0.10 /
-0.54% (x2 at f=0.50). 25 in-window pairs, ALL net positive on allocated
capital (33 entered total, 8 pre-window excluded from 5y stats) — listed
separately, never mixed into the book win rate. Human work: 4 roll decisions
per year (when <= 7 days remain, check basis >= 4 %/yr); each entered pair is
~3 manual tickets (spot buy + futures short, spot sell at delivery); 25 pairs
/ 5 years ~= 5 pairs/year ~= ~15 tickets/year.

## Combos (per anchor year R %/mo, DD %; base in brackets; DD yearly = base,
## conservative — carry MtM above is the bound, troughs do not coincide)

M5_human @ f=0.25 — 5y 3.862, worst 0.936, maxDD 17.94, full 17.79, book win
64.82% unchanged:

| year | R (base) | DD (base) | carry +pp |
|---|---|---|---|
| 2021-09-24 | 0.936 (0.847) | 16.54 (16.54) | +0.089 |
| 2022-09-24 | 1.677 (1.585) | 17.94 (17.94) | +0.092 |
| 2023-09-24 | 4.789 (4.413) | 17.36 (17.36) | +0.376 |
| 2024-09-24 | 8.057 (7.948) | 8.24 (8.24) | +0.109 |
| 2025-09-24 | 4.002 (3.994) | 11.69 (11.69) | +0.008 |

M5_human @ f=0.50 — 5y 3.993, worst 1.024, maxDD 17.94, full 17.79:

| year | R (base) | DD (base) | carry +pp |
|---|---|---|---|
| 2021-09-24 | 1.024 (0.847) | 16.54 | +0.177 |
| 2022-09-24 | 1.768 (1.585) | 17.94 | +0.183 |
| 2023-09-24 | 5.151 (4.413) | 17.36 | +0.738 |
| 2024-09-24 | 8.165 (7.948) | 8.24 | +0.217 |
| 2025-09-24 | 4.010 (3.994) | 11.69 | +0.016 |

Other rows (5y / worst / maxDD / full; per-year tables in results.json):
- G15 f=0.25: 3.157 / 0.725 / 14.93 / 14.88; f=0.50: 3.304 / 0.815 / 14.93 / 14.88.
- G10 f=0.25: 2.774 / 0.539 / 13.54 / 13.51; f=0.50: 2.927 / 0.631 / 13.54 / 13.51.
- humanBF f=0.25: 3.754 / 0.958 / 21.55 (overall proxy) / none stored;
  f=0.50: 3.888 / 1.045 / 21.55 / none stored.
- top2 f=0.25: 3.210 / 0.477 / 19.53 (overall proxy) / none stored;
  f=0.50: 3.350 / 0.570 / 19.53 / none stored.
- Book win in every combo = base book win (carry adds zero book trades);
  no losing year appears or disappears anywhere.

## Verdict (MANUAL floor: 5 %/mo AND DD < 20 AND book win >= 55 %)

NO — no MANUAL + carry row reaches the MANUAL floor. The best combo
(M5_human f=0.50, 3.993 %/mo) still misses return by ~1.0pp; the equity-level
MAN rows in oc_carrycombo (the more realistic marking: MAN_f0.25 3.746 /
MAN_f0.50 3.765, vs yearly-level 3.862 / 3.993 here) miss by ~1.2pp, same
verdict. DD and win pass for M5_human/G15/G10/top2 but return never does;
humanBF additionally fails DD (>= 20). Yearly-level overstates the sleeve by
~0.1-0.2pp vs equity-level (ENTRY-year grouping ignores delivery timing and
intra-year dilution on the fast-growing account) — labelled, verdict-robust
either way.

## Caveats

- Yearly-level combination (said so above): full ENTRY-year carry P&L is
  counted in the entry year though delivery falls next year; intra-year
  compounding/dilution is ignored. The equity-level cross-check
  (oc_carrycombo MAN_f0.25/0.50: gaps +0.116/+0.228pp) bounds this optimism.
- DD_comb yearly = base DD (conservative flat); full-path DD = base stored
  value or conservative proxy (labelled per row). Equity-level MAN measured a
  slight improvement (17.79 -> 17.19/16.61), so flat is conservative.
- oc_carryd13/combine_carryd13.py (BOT equity-level hourly combination) was
  NOT re-run (needs hourly_ext.parquet, absent here); only its frozen-carry
  definition is reused verbatim. No new predictive features were built.
