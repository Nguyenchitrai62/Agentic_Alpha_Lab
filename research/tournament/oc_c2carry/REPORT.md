# oc_c2carry — REPORT (2026-10-07, descriptive, no selection)

Account-realistic profile: G2 vs G2+carry vs K2 vs K2+carry vs C2 vs C2+carry,
each on Binance and on Bybit prices (S5). Method = ONE account
A(t)=A(t-1)*(1+r_bot(t))+dU(t) (UTA: BOT sizes on TOTAL equity; verbatim copy of
`oc_k2carry/analyze_k2carry.py` extended to the 2 C2 legs;
repro `research/tournament/oc_c2carry/analyze_c2carry.py`, CPU-only hourly,
no 1m, no engine reruns) + stationary bootstrap per row (10-day blocks,
4000 draws x 365 d, seed 0; like `oc_mcdd`). Carry = frozen oc_cashcarry
(33 entered, threshold 0.04; fees spot 0.001/side + fut 0.00055/0.0002),
f = 0.25, compounding on total equity. Gate costs inside stored paths:
maker 0.0002, taker 0.00055, longs pay 0.0001/8h, shorts 0.

## Reproduction gates (PASS, to the digit — else STOP)

- G2_bin f=0 == v421 G2 (5.41 / W 2.588 / DD 16.91 / full 16.82).
- G2_bin f=0.25 == oc_carrycompound (5.634 / 16.75 / 16.66).
- K2_bin f=0 == oc_kronoshidden/base-K2; G2_by f=0 == REF_S5 and
  K2_by f=0 == K2_S5 (oc_k2bybit table) to the digit (the 8 oc_k2carry numbers).
- C2_bin f=0 == oc_chronos C2 (dev 2.711/11.52, 3.460/15.48, 6.250/15.07,
  10.721/8.29; Y4 4.754/12.86; full-path 15.42) to the digit.
- C2_by f=0 == oc_c2bybit C2_S5 (2.213/12.21 SHORT, 3.062/16.50, 5.415/16.65,
  10.527/9.27, 4.558/12.22; 5y 5.115; full 16.50) to the digit.
- REF_S5 in the C2 file == REF_S5 in the K2 file (same engine, asserted element-wise).

## Table: per anchor-year R %/mo / DD % (reset metric, fresh 1.0 per year)

S5 y2021 is a SHORT window (Bybit live from 2021-11-15, labelled).
`recent` = anchor 2025-09-24 year (clean BUT already scored once for base
K2 and base C2 -> labelled re-score, never a selection input). K2 dev edge is an
UPPER BOUND (Kronos pretraining likely saw dev years); C2 dev edge is an UPPER
BOUND too with a smaller caveat (Chronos-Bolt 2024-11, mostly non-crypto +
synthetic). Carry overlay is post-hoc (needs prospective paper). Carry leg
close-marked: DD lower bound.

| row (BOT + carry, venue) | 2021 | 2022 | 2023 | 2024 | recent 2025 | 5y mean | worst(5y) | maxDD | losing | full-path DD (m/c/full) |
|---|---|---|---|---|---|---|---|---|---|---|
| G2 Binance | 2.588/10.86 | 3.282/16.91 | 6.045/15.81 | 10.677/8.27 | 4.648/12.90 | 5.410 | 2.588 | 16.91 | 0 | 16.82/16.05/16.82 |
| G2+carry Binance | 2.778/10.86 | 3.353/16.75 | 6.590/15.69 | 10.956/8.20 | 4.698/12.66 | 5.634 | 2.778 | 16.75 | 0 | 16.66/15.90/16.66 |
| K2 Binance (UPPER) | 2.469/11.78 | 3.478/16.20 | 6.679/15.69 | 10.653/8.54 | 4.801/12.10 | 5.577 | 2.469 | 16.20 | 0 | 16.09/15.35/16.09 |
| K2+carry Binance (UPPER) | 2.659/11.78 | 3.548/16.04 | 7.223/15.57 | 10.932/8.52 | 4.851/11.98 | 5.801 | 2.659 | 16.04 | 0 | 15.93/15.20/15.93 |
| C2 Binance (UPPER-small) | 2.711/11.52 | 3.460/15.48 | 6.250/15.07 | 10.721/8.29 | 4.754/12.86 | 5.542 | 2.711 | 15.48 | 0 | 15.42/14.64/15.42 |
| C2+carry Binance (UPPER-small) | 2.900/11.47 | 3.531/15.33 | 6.792/15.07 | 11.001/8.22 | 4.804/12.63 | 5.766 | 2.900 | 15.33 | 0 | 15.27/14.49/15.27 |
| G2 Bybit S5 | 2.129/12.36 SHORT | 2.735/18.11 | 4.932/16.89 | 10.377/9.22 | 4.443/12.37 | 4.883 | 2.129 | 18.11 | 0 | 18.09/17.48/18.09 |
| G2+carry Bybit S5 | 2.321/12.36 SHORT | 2.808/17.95 | 5.484/16.67 | 10.656/9.15 | 4.493/12.13 | 5.111 | 2.321 | 17.95 | 0 | 17.93/17.34/17.93 |
| K2 Bybit S5 (UPPER) | 1.957/13.52 SHORT | 2.982/17.49 | 5.209/16.66 | 10.355/9.10 | 4.553/11.63 | 4.972 | 1.957 | 17.49 | 0 | 17.41/16.76/17.41 |
| K2+carry Bybit S5 (UPPER) | 2.150/13.52 SHORT | 3.055/17.34 | 5.758/16.45 | 10.634/9.03 | 4.602/11.51 | 5.199 | 2.150 | 17.34 | 0 | 17.26/16.62/17.26 |
| C2 Bybit S5 (UPPER-small) | 2.213/12.21 SHORT | 3.062/16.50 | 5.415/16.65 | 10.527/9.27 | 4.558/12.22 | 5.115 | 2.213 | 16.65 | 0 | 16.50/15.84/16.50 |
| C2+carry Bybit S5 (UPPER-small) | 2.405/12.17 SHORT | 3.135/16.35 | 5.965/16.52 | 10.806/9.20 | 4.607/12.09 | 5.342 | 2.405 | 16.52 | 0 | 16.35/15.70/16.35 |

Gaps (descriptive, not selection). Binance 5y: carry adds +0.224 on G2
(5.410->5.634), +0.224 on K2 (5.577->5.801), +0.224 on C2 (5.542->5.766).
C2 vs G2 +0.132 (5.410->5.542), C2+carry vs G2+carry +0.132 (5.634->5.766);
K2+carry still top on Binance (5.801). Bybit 5y: carry adds +0.228 on G2
(4.883->5.111), +0.227 on K2 (4.972->5.199), +0.227 on C2 (5.115->5.342).
C2 vs G2 +0.232 (4.883->5.115), C2+carry vs G2+carry +0.231 (5.111->5.342);
C2+carry is top on Bybit (5.342). Recent clean year: Binance 4.648/4.801/4.754
-> with carry 4.698/4.851/4.804; Bybit 4.443/4.553/4.558
-> with carry 4.493/4.602/4.607 (C2+carry best of the 12, still < 5%).

## Bootstrap expectation per row (12-month resampled year; %)

Daily close E + daily marked low M from the continuous account (causal
00:00 UTC ffill); Binance universe 2021-09-24..2026-09-23, Bybit universe
2021-11-15..2026-09-23 (live only). Stationary Politis-Romano, mean block
10 d, 4000 paths x 365 d, seed 0, circular. Assumes ~stationary daily
returns, ~10-day dependence only (no annual regime structure); carry
close-marked so DD is a lower bound.

| row | median %/mo | P(month >= 5%) | P(DD > 20% in a year) | P(losing year) |
|---|---|---|---|---|
| G2 Binance | 5.423 | 56.30 | 9.25 | 0.60 |
| G2+carry Binance | 5.635 | 59.90 | 7.80 | 0.50 |
| K2 Binance | 5.526 | 57.88 | 7.25 | 0.55 |
| K2+carry Binance | 5.728 | 61.12 | 6.02 | 0.43 |
| C2 Binance | 5.538 | 57.70 | 7.47 | 0.53 |
| C2+carry Binance | 5.755 | 61.75 | 6.35 | 0.38 |
| G2 Bybit S5 | 4.993 | 49.88 | 13.03 | 1.07 |
| G2+carry Bybit S5 | 5.231 | 53.30 | 11.18 | 0.75 |
| K2 Bybit S5 | 5.104 | 51.45 | 11.55 | 1.05 |
| K2+carry Bybit S5 | 5.330 | 54.87 | 9.90 | 0.60 |
| C2 Bybit S5 | 5.185 | 52.65 | 12.05 | 0.95 |
| C2+carry Bybit S5 | 5.421 | 56.00 | 10.60 | 0.70 |

## Leakage / causality checks (how verified)

- Feature timing: BOT tilts use only bars closing <= T (inherited Part A);
  carry MtM uses last CLOSED hourly bar strictly before t, 0 before
  entry-close; `test_carry_mtm_causal_truncation` recomputes from a truncated
  hourly table — identical on the kept prefix. No 1m peeking (no 1m reads).
- Label windows: no labels fit here; carry rule frozen (0.04 from oc_cashcarry).
- Fit windows: no refit; K2/C2 fits frozen (harness t_exit < A - 7d, shift-0
  only); year y uses anchor-y fit only (inherited). S5 = price-source switch.
- Fill timing: inherited engine (win_start=5, trade-through, stop-first);
  `test_gates_reproduce_frozen_numbers` asserts f=0 rows to the digit
  (G2/K2/C2 x Binance/Bybit).
- Tests: `tests/test_oc_c2carry.py`, run
  `.venv/Scripts/python.exe -m pytest tests/test_oc_c2carry.py -q`.

## What failed / caveats

- Nothing failed mechanically (all gates pass); the shortfall is substantive:
  on Bybit prices the clean recent year clears 5%/mo NOWHERE (best 4.607
  C2+carry Bybit; G2+carry 4.493, K2+carry 4.602). The 5y Bybit ranking
  C2+carry 5.342 > K2+carry 5.199 > G2+carry 5.111 rests on dev years that are
  UPPER BOUNDS (K2 strongly, C2 weakly) plus a post-hoc carry overlay on the
  same five years.
- C2 dev edge on Bybit (+0.23 5y vs G2, +0.14 vs K2 with carry) is an UPPER
  BOUND and shrinks in the clean year (+0.11/+0.05 with carry); carry's +0.23
  is post-hoc (same five years, needs prospective paper).
- S5 y2021 SHORT; S5 full-path DDs (16.35-18.09) exceed Binance (15.27-16.82);
  C2 full-path DD is the lowest in each venue group.

## Tom tat tieng Viet cho chu tai khoan (<= 15 dong, Bybit, ca 3 deu +carry)

1. Tren gia Bybit (S5, tu 2021-11-15): G2+carry 5,11%/thang, K2+carry 5,20,
   C2+carry 5,34 (5y); DD full-path 17,93 / 17,26 / 16,35.
2. Voi G2+carry: ky vong thuc te ~5,1%/thang, nam sach gan nhat 4,49
   (DUOI cong 5%), bootstrap trung vi 5,23, P(thang>=5%) 53%,
   P(DD>20%) 11%, P(nam lo) 0,8%.
3. Voi K2+carry: ~5,2%/thang, nam sach 4,60 (van DUOI 5%),
   bootstrap trung vi 5,33, P(thang>=5%) 55%, P(DD>20%) 10%, P(nam lo) 0,6%.
4. Voi C2+carry: ~5,3%/thang (cao nhat), nam sach 4,61 (van DUOI 5%,
   tot nhat trong 12 hang nhung van thieu 0,39),
   bootstrap trung vi 5,42, P(thang>=5%) 56%, P(DD>20%) 11%, P(nam lo) 0,7%.
5. C2+carry hon K2+carry +0,14%/thang 5y tren Bybit nhung dev la can tren
   (K2 nhieu, C2 it hon) va carry la post-hoc tren cung 5 nam, can paper.
6. DD Bybit cao hon Binance; trong nhom Bybit C2+carry DD thap nhat (16,35).
7. De dat cong 5% tren Bybit can them carry + dieu kien tot; chay thuan
   khong carry thi ca 3 deu duoi cong 5y (4,88 / 4,97 / 5,12).

## Vietnamese verdict (3 lines)

- C2+carry tren Bybit dat 5,34%/thang 5y (cao nhat) nhung nam sach chi 4,61 (duoi cong 5%), edge dev la can tren nen khong adopt.
- G2+carry (5,11) va K2+carry (5,20) tren Bybit cung duoi cong o nam sach (4,49 / 4,60) — giu paper, khong dua von that.
- Ket luan: needs prospective evidence — giu ca K2, C2 va carry trong paper runner hien tai, khong dua vao G2 luc nay.
