# oc_d1c2 — REPORT (2026-10-08; PLAN frozen before any outcome, pytest 7/7)

Do the two strongest dip tilts (D1 downside share, C2 Chronos) combine?
Pre-registered ensembles of the FROZEN legs: AVG = mean of the rung multipliers,
AGREE = 1.25 iff both 1.25 / 0.75 iff both 0.75 else 1.0. D1/C2 rows COPIED
(not re-run). STATUS: DONE — overlap + dev engine (REF reproduces G2 to the
digit, determinism OK) + last-window ONCE for REF/AVG/AGREE + placebo per year.

## Overlap: the two signals are different (descriptive, not a selection input)

Inner-joined frozen feature rows (sym, shift, T): 258,085 (downshare 268,325).
Spearman(m_D1, m_C2): pooled **0.0302**; per year 2021 **0.2024**, 2022 0.0202,
2023 -0.0074, 2024 0.0299, 2025-09-24..2026-09-23 0.0194. Same-bucket agreement
rate only 0.33-0.54 per year. Joint 1.25x1.25 is rare (193-1,369 rows/year);
the mass sits off-diagonal (e.g. 2022: D1=1.0 x C2=0.75 is 18,185/43,800).
Verdict: genuinely different tilts — an ensemble is a real diversification test.

Agreement table (m_D1 x m_C2), full counts in tmp/overlap.json:

| year | 0.75x0.75 | 0.75x1.0 | 0.75x1.25 | 1.0x0.75 | 1.0x1.0 | 1.0x1.25 | 1.25x0.75 | 1.25x1.0 | 1.25x1.25 |
|---|---|---|---|---|---|---|---|---|---|
| 2021 | 1402 | 2053 | 50 | 11061 | 18554 | 1282 | 1586 | 6443 | 1369 |
| 2022 | 2287 | 2474 | 169 | 18185 | 11773 | 284 | 4167 | 4268 | 193 |
| 2023 | 795 | 1911 | 303 | 12801 | 17620 | 645 | 3455 | 5968 | 302 |
| 2024 | 2820 | 4433 | 573 | 13253 | 19443 | 707 | 369 | 1939 | 263 |
| 2025 clean | 3068 | 8025 | 1339 | 18471 | 40655 | 3803 | 1381 | 4989 | 1154 |

## Engine dev4 (4-phase reset %/mo + DD; REF reproduces v421 G2 to the digit)

| row | y0 R/DD | y1 R/DD | y2 R/DD | y3 R/DD | mean | WORST | DDmax |
|---|---|---|---|---|---|---|---|
| REF (run) | 2.588/10.86 | 3.282/16.91 | 6.045/15.81 | 10.677/8.27 | 5.601 | 2.588 | 16.91 |
| D1 (copied) | 2.921/12.59 | 3.604/16.09 | 6.541/15.74 | 10.191/8.19 | 5.776 | 2.921 | 16.09 |
| C2 (copied) | 2.711/11.52 | 3.460/15.48 | 6.250/15.07 | 10.721/8.29 | 5.739 | 2.711 | 15.48 |
| AVG (run) | 2.820/12.06 | 3.536/15.77 | 6.308/15.54 | 10.480/8.25 | 5.744 | 2.820 | 15.77 |
| AGREE (run) | 2.753/11.49 | 3.485/16.21 | 5.993/15.83 | 10.689/8.27 | 5.685 | 2.753 | 16.21 |

Robust pick on dev4 ONLY among REF/AVG/AGREE: all DD <= 20, no losing year, all
mean >= 5 — highest WORST: **AVG (2.820 > 2.753 > 2.588)**. AVG also cuts DDmax
to 15.77 (fullDDdev 15.67) vs REF 16.91. Neither ensemble beats D1's dev4
(5.776 / W 2.921). Dev all-win rates are flat (REF 0.613-0.697 vs AVG
0.612-0.694 vs AGREE 0.613-0.696 across years).

## Post-release year 2025-09-24..2026-09-23 — LABELLED DIAGNOSTIC, scored ONCE

(both legs already saw this year, so no ensemble number here is clean evidence)

| row | %/mo | DD | full-path DD | book win | rung win | all win |
|---|---|---|---|---|---|---|
| REF | 4.648 | 12.90 | 16.82 | 0.5365 | 0.6478 | 0.6267 |
| D1 copied | 4.591 (-0.057) | 13.38 | 15.98 | — | — | — |
| C2 copied | 4.754 (+0.106) | 12.86 | 15.42 | — | — | — |
| AVG | 4.696 (+0.048) | 13.10 | 15.67 | 0.5361 | 0.6489 | 0.6276 |
| AGREE | 4.740 (+0.092) | 12.73 | 16.14 | 0.5374 | 0.6483 | 0.6272 |

5y geo mean: REF 5.410 / D1 5.538 / C2 5.542 / AVG 5.533 / AGREE 5.495; no losing
year anywhere; full-path DD <= 20 everywhere. The dev4 pick (AVG) keeps only
+0.048 on the diagnostic year and stays below the 5.0 gate (4.696 < 5.0);
AGREE keeps +0.092 (4.740) but was NOT the dev4 pick, and both legs' Y4 numbers
were already known — this is the same dev-mean-does-not-transfer lesson as
v189-v197. Win rates flat (all-win 0.6267-0.6276).

## Timing placebo per year (replica ledger, 1000 perms; significant iff >= 95)

| year | AVG timing | AVG block | AGREE timing | AGREE block |
|---|---|---|---|---|
| 2021 | 99.40 | 99.00 | 97.50 | 98.30 |
| 2022 | 100.00 | 100.00 | 99.90 | 99.90 |
| 2023 | 100.00 | 100.00 | 99.70 | 98.40 |
| 2024 | 100.00 | 100.00 | 83.82 | 88.91 |
| 2025 clean | 97.80 | 98.30 | 99.20 | 99.80 |

AVG timing is significant every year including clean (97.8/98.3); AGREE is
significant except 2024 (83.8/88.9 — the year D1 points the wrong way on the
replica). Timing signal is real but, as with both legs, does not convert into a
>= 5 %/mo clean-year return.

## Leakage checklist

- Feature timing: D1 36 closes <= T, C2 512 closes <= T (truncation-tested in
  their own studies); here both parquets joined read-only on exact (sym, shift,
  T), tz-aware UTC — the join cannot create foresight. Coverage: joined
  258,085/268,325 (chronos is the binding leg; missing -> mult 1, counted:
  ledger join missing 0/22,312 both variants).
- Label windows: harness t_exit < A - 7d inherited via frozen fits; no test
  labels in any fit.
- Fit windows: shift-0 only + 7d embargo inherited; anchor-y fit for year y;
  fits frozen before this study, never refit; AVG/AGREE rules frozen in PLAN.
- Fill timing: replica live 16..238 strict trade-through + stop-first inherited;
  engine win_start=5 + 1m trade-through + stop-first; perms reassign mults
  within-year only (seeds 20261007+y / 20261008+y).
- No statistic from any test year feeds any choice (selection on dev4 only;
  last window scored once after the pick was frozen).
- Gate costs inside replica outcomes and the engine (maker 0.0002 / taker
  0.00055 / longs pay 0.0001 per 8h, shorts 0).
- Contamination label: C2 leg released 2024-11 (dev possibly contaminated);
  ensemble post-release is a labelled diagnostic regardless (both legs saw Y4).

## What failed and why

The ensembles do exactly what diversification predicts — AVG lands between the
legs on dev4 (mean 5.744 vs D1 5.776 / C2 5.739; WORST 2.820 vs 2.921 / 2.711)
with the lowest DDmax (15.77) — but diversification of two tilts that each miss
the clean-year gate (D1 4.591, C2 4.754) cannot manufacture a gate pass: AVG
4.696, AGREE 4.740, both < 5.0. AGREE's slightly better diagnostic year comes
from concentrating on joint tails that happened to agree there, at the cost of
the 2024 placebo failure (83.8). Nothing here changes the verdict on either leg.

## Vietnamese verdict

AVG thắng dev4 về worst-year (2,82, DDmax 15,77, timing sạch 97,8%) nhưng năm
diagnostic chỉ +0,048 (4,696 < cổng 5%); AGREE +0,092 (4,740) nhưng không phải
dev4 pick và rớt placebo 2024 (83,8).
Kết luận: REJECT cả hai ensemble ở dạng đăng ký trước; giữ kết quả làm bằng
chứng prospective, không adopt vào G2.
