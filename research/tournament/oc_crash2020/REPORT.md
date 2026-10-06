# oc_crash2020 REPORT (2026-10-06; PLAN pre-registered before any outcome)

## Setup

Isolated G2 dip-sleeve replay (dip-only, no book, R2 agent size = 1, scale =
governor = 1): B1 sizes 1/(1+n) x kd 1.7, R2 depths 2.5/3/3.5/4/5, risk budget
0.442 (gap 0.02), close5 4-sigma stop + 8-sigma backstop + TP 1 sigma + timeout
at next 4h open, stop-first, gate fees (maker 0.0002 / taker 0.00055, settle
funding 0.0001). Arms: G2 (gross cap 2.0 per phase sub-account) vs NOCAP
(budget-only reference). 5 windows x 4 clock phases, each cell starts equity
1.0 flat, 10-day sim. Full numbers in results.json (ledger checksum
d07ee7f63ff3b6cd, 3440 rung rows). 2020-2021 is in-sample for the rule
parameters: tail measurement only, no selection.

## Per window x phase (G2; NOCAP is bit-for-bit identical in ALL 40 cells)

| window | ph | maxLoss% | maxDD% | peakGross | fills/stops | gapStops (max sg) | worst minute (UTC) | endEq | rec7d |
|---|---|---|---|---|---|---|---|---|---|
| W1 COVID 03-12 | s0 | 14.28 | 14.71 | 0.77 | 178/35 | 19 (3.38) | 03-13 04:57 | 0.933 | never |
| W1 COVID 03-12 | s1 | 21.85 | 22.30 | 0.83 | 182/45 | 13 (2.71) | 03-13 15:44 | 0.826 | never |
| W1 COVID 03-12 | s2 | 14.64 | 15.44 | 0.81 | 146/27 | 6 (2.88) | 03-13 02:16 | 0.944 | never |
| W1 COVID 03-12 | s3 | 13.56 | 13.82 | 0.85 | 134/31 | 11 (3.40) | 03-12 23:28 | 0.902 | never |
| W2 COVID 03-16 | s0 | 1.41 | 2.31 | 0.75 | 42/0 | 0 | 03-16 07:38 | 1.016 | 4.54d |
| W2 COVID 03-16 | s1 | 2.77 | 5.20 | 0.88 | 46/0 | 0 | 03-20 20:31 | 1.017 | never* |
| W2 COVID 03-16 | s2 | 1.52 | 3.45 | 0.76 | 24/0 | 0 | 03-20 20:31 | 1.042 | 0.02d |
| W2 COVID 03-16 | s3 | 2.57 | 2.89 | 0.82 | 44/0 | 0 | 03-20 20:31 | 1.003 | never* |
| W3 2021-01-21 | s0-s3 | 1.33/0.35/0.40/0.40 | 1.86/0.75/1.52/1.70 | 0.57/0.37/0.48/0.40 | 25/0,23/0,20/0,23/0 | 0 | - | 1.020/1.030/1.021/1.041 | <0.1d |
| W4 2021-05-19 | s0 | 13.73 | 14.95 | 0.96 | 198/17 | 8 (3.17) | 05-20 00:53 | 0.980 | never |
| W4 2021-05-19 | s1 | 13.29 | 13.87 | 0.91 | 151/15 | 7 (1.94) | 05-20 00:53 | 0.944 | never |
| W4 2021-05-19 | s2 | 9.79 | 10.34 | 1.03 | 203/15 | 9 (2.32) | 05-20 00:53 | 0.961 | never |
| W4 2021-05-19 | s3 | 3.02 | 5.55 | 0.86 | 196/6 | 3 (3.25) | 05-19 11:32 | 1.160 | 0.0d |
| W5 2021-06-21 | s0-s3 | 0.09/0.90/0.03/1.51 | 0.69/1.12/1.03/1.63 | 0.26/0.40/0.32/0.51 | 15/0,15/0,21/0,34/0 | 0 | - | 1.022/1.025/1.026/1.025 | <0.1d |

\* trough late in the sim (03-20); recovery searched only inside the sim.

## Phase-mean context (each phase 1/4 equity; mean-of-mins is a pessimistic proxy of the true mix)

| window | mean maxLoss% | mean maxDD% | peakGross | fills/stops/gap | endEq |
|---|---|---|---|---|---|
| W1 COVID 03-12 | 16.08 | 16.56 | 0.82 | 640/138/49 | 0.901 |
| W2 COVID 03-16 | 2.06 | 3.46 | 0.80 | 156/0/0 | 1.020 |
| W3 2021-01-21 | 0.62 | 1.46 | 0.46 | 91/0/0 | 1.028 |
| W4 2021-05-19 | 9.96 | 11.17 | 0.94 | 748/53/27 | 1.011 |
| W5 2021-06-21 | 0.63 | 1.12 | 0.37 | 85/0/0 | 1.025 |

## Comparison with the worst 2021-2026 window (oc_stresshist, labelled unit mismatch)

oc_stresshist worst G2 week (FULL pipeline, book+dip, year-equity units):
2023-12-27..2024-01-03, week -12.3%, DD 13.9%. Here (dip-sleeve-only,
sub-account units): COVID W1 mix-proxy -16.1% (worst phase -21.8%, DD 22.3%),
May-19 W4 mix-proxy -10.0% (worst phase -13.7%). A COVID-scale crash is worse
for the dip sleeve alone than any 2021-2026 full-pipeline week; the other four
windows are inside the runbook's bad-week band (-8..-12%) or negligible.

## The 2.0x gross cap did nothing in these windows

G2 and NOCAP agree bit-for-bit in all 40 cells: peak gross notional never
exceeds 1.03x (max over all cells, W4 s2) vs the 2.0 cap. Crash sigma widens
stops and shrinks notionals, so the risk budget (0.442) binds long before the
gross cap. The cap binds in calm markets (up to ~6.4x uncapped per oc_kpi),
not in crashes: crash-tail containment here comes from the risk budget + B1
sizing + stops, NOT from the cap. The cap remains justified by the
hypothetical-gap analysis (DEPLOYMENT_PLAN_VI: worst gap minute -58% -> -33.5%
with cap), which this replay neither confirms nor contradicts.

## Verdict (tieng Viet, cau tra loi chinh)

Ton that crash lich su te nhat cho dip sleeve cua G2: COVID 12-13/03/2020,
mat toi da -21.8% von sub-account o 1 pha don le (-22.3% DD, phut te nhat
13/03 15:44 UTC, 45 stop/182 lenh, 13 stop gap qua >1 sigma), trung binh 4 pha
~ -16.1% (muc conservative, mix that te hon so nay mot chut); crash 19/05/2021
mix ~ -10.0% (pha te nhat -13.7%). Ba cua so con lai khong dang ke (<= -2.1%).
Tran gross 2.0x KHONG giu duoc DD trong cac crash nay vi no chua bao gio kich
hoat (gross dinh chi ~1.0x do sigma crash lam notional nho lai) - DD duoc giu
bo risk budget + B1 + stop. Pha don le W1 (-21.8%) vuot nguong runbook 20%,
nhung mix 4 pha trien khai (~-16%) nam trong ky vong DD (tuong duong tuan xau
-8..-12% cua runbook o muc do crash COVID, la crash te hon moi tuan 2021-2026).
Khuyen nghi van giu tran 2.0x (bao ve gap gia khi thi truong yen, khong ton kem
gi trong crash) va khong bao gio chay 1 pha don le.
