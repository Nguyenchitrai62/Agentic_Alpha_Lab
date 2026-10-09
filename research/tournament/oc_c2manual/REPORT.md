# oc_c2manual REPORT (frozen rows, single heavy pass 2026-10-08)

Can the MANUAL product use the Chronos C2 multiplier (human reads it at the
bar open)? Pre-registered rows only: M5_human (deployed MANUAL reference),
KM_C2 (dip rungs x C2 1.25/0.75/1.0 from Chronos ch_q10 + per-anchor
oc_chronos fits), CTRL (dip rungs x C_y constant = KM_C2 decision mean,
exposure control), KM_K2 copied from oc_k2manual (same harness, context).
LABEL: new product variant; dev years possibly in Chronos pretraining =
UPPER BOUND; most-recent year 2025-09-24..2026-09-23 POST-HOC, scored once.

## Baseline reproduction (gate, passed)

- M5_human rerun is BIT-EXACT vs oc_manualcap_runs.pkl (max abs d(eq) =
  0.000e+00) and equals R5 3.728 / W 0.847 / maxDD 17.94 / fullDD 17.79 /
  book_win .6482. Harness copied exactly from oc_k2manual (M5 pipe v367,
  human schedule win_start=15 / sleeve_start=16, night bar skipped, agents
  ON); only the multiplier table swapped (Kronos low1 -> Chronos ch_q10).
- CTRL C_y (decision means): 2021 0.935228 (n=43800), 2022 0.863054,
  2023 0.909812, 2024 0.914960, 2025 0.960892 (n=43680).
- Gate costs maker 0.0002 / taker 0.00055, longs pay 0.0001/8h, shorts
  nothing; limits fill only on 1m trade-through, no fill minutes 0..15,
  stop-first.

## Results (reset metric %/month geo; DD = max yearly 1m DD; fullDD v388.mix)

| year | M5_human R | KM_C2 R | CTRL R | KM_K2 R (copied) | M5 DD | KM_C2 DD | CTRL DD |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2021-09-24 | 0.847 | 0.705 | 0.839 | 0.661 | 16.54 | 17.55 | 15.28 |
| 2022-09-24 | 1.585 | 2.052 | 1.871 | 1.931 | 17.94 | 17.37 | 17.99 |
| 2023-09-24 | 4.413 | 4.819 | 3.437 | 5.039 | 17.36 | 17.33 | 17.76 |
| 2024-09-24 | 7.948 | 7.933 | 7.766 | 7.747 | 8.24 | 7.71 | 7.46 |
| 2025-09-24 (POST-HOC) | 3.994 | 4.061 | 3.951 | 3.968 | 11.69 | 11.85 | 11.64 |

| row | R5 | W | maxDD | fullDD | Rdev4 | Wdev4 | DDdev4 | Rlast |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| M5_human | 3.728 | 0.847 | 17.94 | 17.79 | 3.661 | 0.847 | 17.94 | 3.994 |
| KM_C2 | 3.885 | 0.705 | 17.55 | 17.55 | 3.840 | 0.705 | 17.55 | 4.061 |
| CTRL | 3.546 | 0.839 | 17.99 | 17.77 | 3.445 | 0.839 | 17.99 | 3.951 |
| KM_K2 (copied) | 3.840 | 0.661 | 18.06 | 16.93 | 3.808 | 0.661 | 18.06 | 3.968 |

Trades/wins: book M5 3744 @.6482, C2 3806 @.6484, CTRL 3705 @.6480;
rung M5 6417 @.7013, C2 6513 @.7026, CTRL 6542 @.7031;
all-trade win .6817 / .6826 / .6832 (K2 copied: book 3745 @.6475,
rung 6338 @.7009, all .6810). Engine-sized C2 means
(1.044/0.915/0.980/1.009/1.024) run above decision means
(0.935/0.863/0.910/0.915/0.961) because the engine skips night bars
while the feature means include them; the rule applied as coded.
KM_C2 beats CTRL on R5 (+0.339pp) and Rdev4 (+0.395pp): timing skill over
pure exposure. C2 also beats K2 on R5 (+0.045pp), worst year (0.705 vs
0.661) and the clean year (+0.093pp vs K2, +0.067pp vs M5). But the worst
dev year still falls vs M5 (0.705 vs 0.847). Dev numbers are UPPER BOUND
(Chronos pretraining); the clean year adds only +0.067pp. MANUAL gate
(R5>=5, fullDD<20, book win>=55%): all rows fail R5.

## Leakage audit

- feature timing: C2 mult for holding-bar open T joins the frozen Chronos
  row (sym, shift, T) with ch_q10 built only from the 512 closes of bars
  closing <= T on that shift's grid (oc_chronos PLAN); R2 size/TP tables
  keyed by bar-open T only; no 1m data enters any decision (causality test
  in tests/test_oc_c2manual.py asserts the bar-open key and bans
  fill-minute markers).
- label windows: no new labels; no outcome enters any sizing decision.
- fit windows: fits.json pre-fit on harness rows with t_exit < A - 7d
  (shift-0 only, inherited); fits of anchor A apply to year [A, A+365d);
  CTRL C_y from feature rows + fits only, no outcomes; no test-year
  statistic feeds any choice.
- fill timing: no fill minutes 0..15 (win_start=15 books, sleeve_start=16
  dips, stricter than the minute-5 user rule); limits fill only on 1m
  trade-through; stop-first on same-bar SL+TP touch; dip timeout at next
  4h open.

## Verdict

KM_C2 closes 0.157pp of the 1.272pp MANUAL gap to 5 %/month (R5 3.885 vs
M5 3.728, gap 1.115pp; Rdev4 +0.179pp) and beats K2 on every headline
(R5 +0.045, worst year +0.044, clean year +0.093) with real timing skill
over CTRL (+0.339pp R5) - but the worst dev year still falls (0.705 vs
0.847) and the clean year adds almost nothing (+0.067pp); close the
bracket-tilt direction, MANUAL still needs entry edge.

C2 chi cong them ~0,16 diem %/thang vao khoang cach MANUAL den 5 % (R5 3,89, con thieu ~1,12) va hon K2 moi chi so nhung nam te nhat kem di va nam sach hau nhu dung yen: loai.
MANUAL van thieu edge vao lenh, khong phai co lai dip: giu M5_human, dong huong tilt tren bracket.
Can bang chung prospective truoc khi dua bat ky multiplier nao vao san xuat MANUAL.
