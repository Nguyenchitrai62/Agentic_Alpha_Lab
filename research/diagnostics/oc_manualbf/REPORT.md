# oc_manualbf REPORT (2026-10-05): MANUAL M4/M5, 5 years, human schedule + bear book filter

Script: oc_manualbf.py (rows fixed in PLAN.md). Harness = manual_human
(agents ON, per-phase v376 tables, 15-min reaction + night bar (20+s UTC)
skipped) on the FULL 5y index (books154.index + shift, r2_decompose5 style),
live [2021-09-24+s, 2026-09-23+s). BF = v410 transform on STANDARD book rows
before shifted ffill: BTC 4h open < 1200-bar mean -> LONG x0.5, shorts/dips
unchanged. Metrics = single-clock mean over 4 phases (manual_human) + pooled
book/all-trade win (v377 / pof.book_win). Reproduction: dev4 M4_base 4.257,
M5_base 4.094, M4_human 3.604, M5_human 3.504 = manual_human.json exactly.

5y table (years = per-year %/month mean over phases; R5 = 5y geo %/month;
DD = mean max-yearly 1m DD (worst phase); wins pooled 5y):

| row | y21 y22 y23 y24 y25 | R5 | DD (max) | book_win (n) | win_all |
|---|---|---|---|---|---|
| M4_base | 1.48 1.61 5.37 8.80 3.73 | 4.15 | 23.5 (32.1) | 0.507 (4278) | 0.631 |
| M4_human | 0.85 1.67 4.33 7.74 3.98 | 3.68 | 23.8 (32.5) | 0.515 (4163) | 0.628 |
| M4_humanBF | 0.83 1.80 4.26 7.74 4.10 | 3.71 | 21.7 (24.6) | 0.522 (4170) | 0.632 |
| M5_base | 1.31 1.43 5.13 8.72 3.96 | 4.07 | 24.4 (33.2) | 0.648 (3871) | 0.683 |
| M5_human | 0.80 1.33 4.13 7.95 3.92 | 3.59 | 24.5 (33.9) | 0.648 (3744) | 0.682 |
| M5_humanBF | 0.87 1.73 3.92 7.75 3.94 | 3.61 | 21.6 (24.6) | 0.664 (3741) | 0.689 |

BF effect (human -> humanBF): M4 R +0.04, DD 23.8->21.7, worst 32.5->24.6,
W 0.15->0.65, win 0.515->0.522; M5 R +0.02, DD 24.5->21.6, worst 33.9->24.6,
W 0.00->0.77, win 0.648->0.664. The 2022 phase-1 crash rung is cut (as in
BOT v410), but the return does not rise: the filter removes grind DD, not a
return driver.

Verdict vs the base gate (R5 >= 5, DD < 20, book win > 55 %): NO row passes.
M4 rows fail all three (best BF: 3.71 / 21.7 / 52.2 %). M5 rows pass win only
(best BF: 3.61 / 21.6 / 66.4 %). The honest 5y MANUAL expectation stays
~3.6-4.2 %/month with single-clock DD ~22-24 % (worst phase ~25 % even with
BF). Nothing selected; results.json holds dev4/last splits + phase details.
