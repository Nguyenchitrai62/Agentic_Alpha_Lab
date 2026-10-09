# oc_k2manual REPORT (frozen rows, single heavy pass 2026-10-08)

Can the MANUAL product use the Kronos K2 multiplier (human reads it at the
bar open)? Pre-registered rows only: M5_human (deployed MANUAL reference),
KM_K2 (dip rungs x K2 1.25/0.75/1.0 from Kronos low1 + per-anchor fits),
CTRL (dip rungs x C_y constant = KM_K2 decision mean, exposure control).
LABEL: new product variant; dev years inside Kronos pretraining = UPPER
BOUND; most-recent year 2025-09-24..2026-09-23 POST-HOC, scored once.

## Baseline reproduction (gate, passed)

- M5_human rerun is BIT-EXACT vs oc_manualcap_runs.pkl (max abs d(eq) =
  0.000e+00) and equals R5 3.728 / W 0.847 / maxDD 17.94 / fullDD 17.79 /
  book_win .6482. CTRL C_y (decision means): 2021 0.887055 (n=43800),
  2022 0.942249, 2023 0.983761, 2024 0.958048, 2025 0.944305 (n=43680).
- Harness: MANUAL 4-phase (M5 pipe v367, human schedule win_start=15 /
  sleeve_start=16, night bar skipped, agents ON); gate costs maker
  0.0002 / taker 0.00055, longs pay 0.0001/8h, shorts nothing; limits fill
  only on 1m trade-through, no fill minutes 0..15, stop-first.

## Results (reset metric %/month geo; DD = max yearly 1m DD; fullDD v388.mix)

| year | M5_human R | KM_K2 R | CTRL R | M5 DD | KM DD | CTRL DD |
| --- | --- | --- | --- | --- | --- | --- |
| 2021-09-24 | 0.847 | 0.661 | 0.580 | 16.54 | 15.98 | 15.38 |
| 2022-09-24 | 1.585 | 1.931 | 1.558 | 17.94 | 17.18 | 17.80 |
| 2023-09-24 | 4.413 | 5.039 | 4.205 | 17.36 | 18.06 | 17.24 |
| 2024-09-24 | 7.948 | 7.747 | 7.865 | 8.24 | 7.92 | 7.95 |
| 2025-09-24 (POST-HOC) | 3.994 | 3.968 | 3.898 | 11.69 | 11.25 | 11.52 |

| row | R5 | W | maxDD | fullDD | Rdev4 | Wdev4 | DDdev4 | Rlast |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| M5_human | 3.728 | 0.847 | 17.94 | 17.79 | 3.661 | 0.847 | 17.94 | 3.994 |
| KM_K2 | 3.840 | 0.661 | 18.06 | 16.93 | 3.808 | 0.661 | 18.06 | 3.968 |
| CTRL | 3.591 | 0.580 | 17.80 | 17.59 | 3.514 | 0.580 | 17.80 | 3.898 |

Trades/wins: book M5 3744 @.6482, KM 3745 @.6475, CTRL 3740 @.6497;
rung M5 6417 @.7013, KM 6338 @.7009, CTRL 6468 @.7008;
all-trade win .6817 / .6810 / .6821. Sized-mean KM ~ decision mean
(.888/.956/1.032/1.009/.942), so the engine applied the rule as coded.
KM_K2 beats CTRL on R5 (+0.249pp) and Rdev4 (+0.294pp): small timing
skill over pure exposure, but the worst dev year falls (Wdev4 0.661 vs
M5 0.847) and the clean year is flat (-0.026pp vs M5). Dev numbers are
UPPER BOUND (Kronos pretraining contamination); the clean year shows no
edge. MANUAL gate (R5>=5, fullDD<20, book win>=55%): all rows fail R5.

## Leakage audit

- feature timing: K2 mult for holding-bar open T joins the frozen Kronos
  row (sym, shift, T) with low1 built only from the 400 4h bars closing
  <= T on that shift's grid (oc_kronoshidden PLAN); R2 size/TP tables keyed
  by bar-open T only; no 1m data enters any decision (causality test in
  tests/test_oc_k2manual.py asserts the bar-open key and bans fill-minute
  markers).
- label windows: no new labels; no outcome enters any sizing decision.
- fit windows: fits.json pre-fit on harness rows with t_exit < A - 7d
  (inherited); fits of anchor A apply to year [A, A+365d); CTRL C_y from
  feature rows + fits only, no outcomes; no test-year statistic feeds any
  choice.
- fill timing: no fill minutes 0..15 (win_start=15 books, sleeve_start=16
  dips, stricter than the minute-5 user rule); limits fill only on 1m
  trade-through; stop-first on same-bar SL+TP touch; dip timeout at next
  4h open.

## Verdict

KM_K2 closes 0.112pp of the 1.272pp MANUAL gap to 5 %/month (R5 3.840 vs
M5 3.728, gap 1.160pp; Rdev4 +0.147pp) but lowers the worst dev year
(Wdev4 0.661 vs 0.847) and adds nothing in the clean year (-0.026pp vs
M5) - timing skill over CTRL (+0.249pp R5) is real but far too small;
close the K2-bracket direction, MANUAL still needs entry edge.

K2 nhan he so dip chi cong them ~0,11 diem %/thang (R5 3,84 so voi san 5 %) nhung nam te nhat kem di va nam sach khong cai thien: loai.
MANUAL van thieu ~1,16 diem %/thang, can edge vao lenh chu khong phai co lai dip.
Tu choi dua K2 vao san xuat MANUAL: giu M5_human, dong huong bracket theo Kronos.
