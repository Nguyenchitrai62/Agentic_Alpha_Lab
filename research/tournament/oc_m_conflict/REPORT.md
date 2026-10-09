# oc_m_conflict REPORT (frozen rows, single heavy pass 2026-10-08)

IDEAS9 #3 (docs/opencode/IDEAS9_20261008.md): book-vs-dip conflict skip
(human netting-lite) on the MANUAL product. Pre-registered rows only:
M5_human (deployed MANUAL reference), V1 (skip new long dip iff close-known
book w < 0), V2 (skip iff w < 0 and |w| > per-coin pre-anchor median |w|,
7d embargo). Dip sleeve ONLY; book orders untouched; night skip first.

## Baseline reproduction (gate, passed)

- M5_human rerun is BIT-EXACT vs oc_manualcap_runs.pkl (max abs d(eq) =
  0.000e+00) and equals R5 3.728 / W 0.847 / maxDD 17.94 / fullDD 17.79 /
  book_win .6482.
- THR medians (BTC, per anchor): inf, 0.039315, 0.069518, 0.079939, 0.088837
  (inf = < 100 book rows before 2021-09-17, so V2 never skips in 2021 and its
  2021 R is identical to M5, as frozen in PLAN.md). Skip coin-bar rates:
  V1 36.8-59.2 %/yr, V2 0-30.4 %/yr (2021: 0).
- Harness: MANUAL 4-phase (M5 pipe v367, human schedule win_start=15 /
  sleeve_start=16, night bar skipped, agents ON); gate costs maker
  0.0002 / taker 0.00055, longs pay 0.0001/8h, shorts nothing; limits fill
  only on 1m trade-through, no fill minutes 0..15, stop-first.

## Results (reset metric %/month geo; DD = max yearly 1m DD; fullDD v388.mix)

| year | M5_human R | V1 R | V2 R | M5 DD | V1 DD | V2 DD |
| --- | --- | --- | --- | --- | --- | --- |
| 2021-09-24 | 0.847 | 1.639 | 0.847 | 16.54 | 11.46 | 16.54 |
| 2022-09-24 | 1.585 | 2.346 | 1.543 | 17.94 | 18.79 | 19.78 |
| 2023-09-24 | 4.413 | 4.091 | 4.100 | 17.36 | 17.22 | 17.46 |
| 2024-09-24 | 7.948 | 7.460 | 7.755 | 8.24 | 7.13 | 7.31 |
| 2025-09-24 POST-RELEASE | 3.994 | 3.522 | (3.835) | 11.69 | 10.00 | (10.82) |

| row | Rdev4 | Wdev4 | DDdev4 | R5 | W | maxDD | fullDD | Rlast | book_win | rung_win | win_all |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| M5_human | 3.661 | 0.847 | 17.94 | 3.728 | 0.847 | 17.94 | 17.79 | 3.994 | .6482 | .7013 | .6817 |
| V1 (PICK) | 3.860 | 1.639 | 18.79 | 3.792 | 1.639 | 18.79 | 18.87 | 3.522 | .6524 | .7218 | .6854 |
| V2 | 3.526 | 0.847 | 19.78 | 3.588 | 0.847 | 19.78 | 19.66 | (3.835) | .6502 | .6996 | .6794 |

Robust pick on dev4 ONLY: all three eligible (DD <= 20, no losing dev
year); neither variant has dev4 mean >= 5, so highest dev4 WORST wins:
V1 (1.639) over V2 (0.847). PICK = V1. The most recent year was scored ONCE
in the same frozen pass, for the pick V1 and M5_human only (labelled
POST-RELEASE, never used to choose); V2's last-year (3.835, in parentheses)
is shown for completeness from the same pass and was not used for any
decision. Book trades: M5 3744, V1 3855, V2 3779; rung exits: M5 6417,
V1 3501, V2 5480.

V1 closes 0.064 pp of the 1.272 pp MANUAL gap to 5 %/month (R5 3.792 vs
M5 3.728, gap left 1.208 pp; Rdev4 +0.199 pp, Wdev4 +0.792 pp) - inside the
idea's pre-registered +0.0-0.12 band - but gives it all back where it
matters: the clean post-release year is WORSE by 0.472 pp (3.522 vs 3.994)
and DD rises (fullDD 18.87 vs 17.79, maxDD 18.79 vs 17.94). V2 is worse
everywhere (R5 3.588 < 3.728, DD 19.66/19.78). MANUAL gate (R5 >= 5,
fullDD < 20, book win >= 55 %): all rows fail R5. Win-rate gains (+0.4 pp
book, +2.0 pp rung, +0.4 pp all-trade for V1) do not pay for the skipped
winners' return.

## Leakage audit

- feature timing: skip keys only on (bar i, coin a) via the ffill'd
  close-known book target w[i,a] at idx[i] (oc_netting precedent); THR[c,A]
  from book-weight rows with index < A - 7d only; R2 size/TP tables keyed
  by holding-bar time T (bar-open lookup only); no 1m/minute/fill data
  enters any decision (causality test in tests/test_oc_m_conflict.py bans
  fill-minute markers).
- label windows: no new labels; no outcome enters any placement decision.
- fit windows: no fits; THR medians use book weights only (not returns),
  anchor A's THR applies to year [A, A+365d); no test-year statistic feeds
  any choice.
- fill timing: no fill minutes 0..15 (win_start=15 books, sleeve_start=16
  dips, stricter than the minute-5 user rule); limits fill only on 1m
  trade-through; stop-first on same-bar SL+TP touch; dip timeout at next
  4h open.

## Verdict

V1 closes 0.064 pp of the 1.272 pp MANUAL gap (R5 3.792 vs 3.728) with a
better worst dev year, but the clean post-release year is 0.472 pp worse
and DD rises: dev gains do not transfer, same failure mode as the
dev-mean chases noted in AGENTS.md. V2 fails everywhere. Close the
conflict-skip direction; MANUAL still needs entry edge, not dip vetoes.

V1 chi cong them ~0,06 diem %/thang (R5 3,79 so voi san 5 %) nhung nam sach kem hon 0,47 diem va DD tang: loai.
MANUAL van thieu ~1,21 diem %/thang, can edge vao lenh chu khong phai bo bot dip.
Tu choi dua conflict-skip vao san xuat MANUAL: giu M5_human, dong huong veto theo book.
