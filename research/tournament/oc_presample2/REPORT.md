# oc_presample2 REPORT (2026-10-07; PLAN pre-registered before any outcome)

## Setup (fixed rules, no tuning, 7 rows x 4 legs x 4 phases = 112 cells)

Same harness as oc_presample's G2 arm (4 clock phases, dip-only, R2 agent
size 1, gate costs), ONE knob per row (PLAN.md): G2 (baseline), NOB1
(mult=1, no 1/(1+n)), KD13/KD20 (kd 1.3/2.0, budget 0.26*kd = 0.338/0.52),
NOCAP (G=none), TOUCH (1m-low touch stop at 4 sg, exit at min(sl,open),
backstop unchanged), TP15 (tp = lv*(1+1.5*sg)).
FIDELITY GATE: PASS - G2 knobs replayed all 16 oc_presample pre-sample cells
(Y2017/Y2018/Y2019/Y2020p s{0..3}) and matched results.json bit-for-bit on
all 18 simulate-level fields (tmp/gate2.json, 16/16 match).
Full numbers in results.json (ledger checksum 2160b192e159dc2d, 68095 rung
rows); compact means in summary.json.

## Data (reuse, read-only, genuinely new vs 2021-2026 selection)

data/raw/spot_1m_presample_20261007 (Binance SPOT 1m, sha256-verified; BTC/
ETH 2017-08.., BNB 2017-11.., XRP 2018-05..; SOL absent; warm-up BTC/ETH
2017-10-16, BNB 2018-01-05, XRP 2018-07-03). No new download, no edit.
Spot-vs-perp caveat on every number below (SPOT fills/exits, perp gate
costs maker 0.0002/taker 0.00055, adverse long funding 0.0001/8h).

## Per-year 4-phase means (mean %/mo | mean DD | worst-phase DD, 1m-marked; fills/stops/win)

| leg | G2 | NOB1 | KD13 | KD20 | NOCAP | TOUCH | TP15 |
|---|---|---|---|---|---|---|---|
| Y2017 mean%/mo | 10.71 | 14.62 | 8.11 | 12.70 | 10.71 | 10.33 | 12.64 |
| Y2017 mDD/wDD | 5.04/6.03 | 7.42/7.94 | 3.85/4.61 | 5.92/7.09 | 5.04/6.03 | 4.84/6.00 | 6.96/7.89 |
| Y2017 fills/stops/win | 909/30/86.5% | 909/30/86.5% | 909/30/86.5% | 909/30/86.5% | =G2 | 909/40/85.7% | 909/42/79.2% |
| Y2018 mean%/mo | 2.50 | 3.85 | 1.91 | 2.94 | 2.50 | 2.12 | 3.04 |
| Y2018 mDD/wDD | 8.43/9.56 | 13.88/16.21 | 6.47/7.35 | 9.89/11.21 | 8.43/9.56 | 8.63/10.48 | 9.17/10.67 |
| Y2018 fills/stops/win | 2986/99/69.4% | 2984/99/69.3% | 2986/99/69.4% | 2986/99/69.4% | =G2 | 2986/152/68.7% | 2986/124/63.7% |
| Y2019 mean%/mo | 0.48 | 0.56 | 0.38 | 0.55 | 0.48 | 0.49 | 0.65 |
| Y2019 mDD/wDD | 11.30/14.34 | 18.91/23.27 | 8.69/11.06 | 13.23/16.75 | 11.30/14.34 | 9.49/11.40 | 12.26/17.05 |
| Y2019 fills/stops/win | 3116/207/69.9% | 3107/206/70.0% | 3116/207/69.9% | 3116/207/69.9% | =G2 | 3116/281/69.7% | 3111/227/65.1% |
| Y2020p mean%/mo | 0.27 | -0.88 | 0.24 | 0.31 | 0.27 | 0.67 | 0.37 |
| Y2020p mDD/wDD | 17.52/24.53 | 35.77/42.88 | 13.56/19.10 | 20.42/28.47 | 17.52/24.53 | 12.96/18.53 | 20.05/26.65 |
| Y2020p fills/stops/win | 2721/206/71.2% | 2709/204/71.2% | 2721/206/71.2% | 2720/206/71.2% | =G2 | 2721/263/70.5% | 2721/238/65.4% |

Per-phase %/mo (s0/s1/s2/s3): Y2017 G2 12.48/9.91/10.21/10.24; Y2018 G2
2.89/2.45/2.35/2.32; Y2019 G2 -0.18/0.36/1.49/0.25 (s0 losing phase, year
still green on the mean); Y2020p G2 -0.04/-1.45/1.00/1.58. NOB1 is the ONLY
row with a losing pre-sample year (Y2020p -0.88). TOUCH wins the COVID leg
(0.67, lowest DD 12.96); TP15 out-earns G2 in all 4 legs but at higher DD
in all 4 legs.

## Rank table: research-year judgement vs pre-sample (row by row)

| # | research judgement (2021-2026 selection) | pre-sample direction | agree? |
|---|---|---|---|
| 1 | G2 > NOB1: v399/B1 corr size DD 25.05->13.88, R 4.82->4.55 (CLOSED s1) | NOB1 DD >> G2 in ALL 4 legs (7.42/13.88/18.91/35.77 vs 5.04/8.43/11.30/17.52); NOB1 earns more in calm legs but prints the only losing year (Y2020p -0.88, worst-phase DD 42.88) | AGREE |
| 2 | D17 between D13 and K20 on return/DD frontier: D17BF 5.425/18.33 (CLOSED s1); D13BF 4.97/14.98 (CLOSED s6); x2.0 5.78/DD20.95 breach (CLOSED s1); G2K20 5.874/17.79 (CLOSED s12) | monotone frontier in ALL 4 legs: return KD13<G2<KD20 (e.g. Y2018 1.91<2.50<2.94) AND DD KD13<G2<KD20 (6.47<8.43<9.89) | AGREE 4/4 |
| 3 | cap = same return, less tail: v421/G2 same R 5.41, DD -1.4pp, gap -10% 58%->33.5% (CLOSED s1); oc_crash2020 G2==NOCAP 40/40 cells | NOCAP == G2 bit-for-bit 16/16 cells (cap never binds pre-sample; peak gross 2.07 is overlapping-bar stacking, same mechanism as oc_presample) | AGREE (inert, costs nothing) |
| 4 | close5 > touch: S1 every-1m-close sums 2/5, DD 5/5 -> NOT PROMISING (oc_stoptf; CLOSED s11); marktrig tails 2/5 | close5 wins Y2017 (10.71>10.33) + Y2018 (2.50>2.12); tie Y2019 (0.48 vs 0.49); LOSES Y2020p (0.27<0.67, DD 17.52>12.96). TOUCH fires ~30-50% more stops every leg (40/152/281/263 vs 30/99/207/206) | PARTIAL (2/4 legs; faster stop helps in the crash leg) |
| 5 | TP 1.0 > 1.5: oc_dipexit E1 split 0/5, all 4 exits fail (CLOSED s1); tpbyn TP1.5 fails 4/5; deeptp 1/5 | TP15 out-earns TP10 in ALL 4 legs (12.64/3.04/0.65/0.37 vs 10.71/2.50/0.48/0.27) BUT at higher DD in ALL 4 legs (6.96/9.17/12.26/20.05 vs 5.04/8.43/11.30/17.52) with lower win (65-79% vs 69-87%, timeouts +~50%) | DISAGREE on return 0/4; AGREE TP15 carries more tail |

## Leakage / execution statement

No fitting anywhere (all constants frozen from 2020-08..2026-09 research:
kd/budget/cap/stop/TP levels; budget = 0.26*kd exactly as D13BF/G2K20):
sigma(j) uses 4h opens ending at j-1 (shift-1, min_periods 120); n uses
closes up to minute f-1 (tested); fills use strict low trade-through at
minutes 16..238 with price lv; exits evaluated f+1..240 + next-bar open;
NaN exit price drops the rung; warm-up masks pre-eligible coins from opens,
sigma AND n-counts. G2 outcome == oc_presample outcome_d0 on randomised
synthetic paths (test_g2_knobs_match). Reference R-legs not re-run (G2
fidelity gate covers the shared core). Spot-vs-perp caveat on every number.
Tests: tests/test_oc_presample2.py, 11 tests (strict fill, TP10/TP15 levels,
stop-first, TOUCH-whipsaw, funding, kd-budget scaling, cap, NOB1 sizing,
G2-vs-oc_presample equivalence, sigma/n causality, interval truncation) -
all pass.

## Verdict (tieng Viet, ket luan chinh)

Bon tren nam lua chon thiet ke chuyen sang du lieu 2017-2020: tuong quan B1 cat DD mot nua, frontier KD13<G2<KD20 don dieu ca 4 ky, cap vo hinh nhung khong ton kem - chi co TP 1.5 thang TP 1.0 ca 4 ky (nhung DD cao hon) va stop-touch thang close5 trong nhip COVID la khong chuyen.
TP 1.5 chi hon o loi nhuan goc rally/rebound manh chu khong hon o kiem soat duoi (DD cao hon ca 4 ky, win thap hon) - giu TP 1.0 va close5 cho ban trien khai, khong doi luat dua tren pre-sample.
Bang xep hang tong: cac lua chon phong thu (B1, kd 1.7, cap, TP 1.0) deu dung o phia DD thap - G2 van la diem dung an toan, can bang nhat.
