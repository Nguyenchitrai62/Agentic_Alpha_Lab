# oc_presample REPORT (2026-10-07; PLAN pre-registered before any outcome)

## Setup (fixed rules, no tuning, G2 arm only)

Isolated G2 dip-sleeve replay, dip-only, R2 agent size = 1, scale = governor
= 1: B1 sizes 1/(1+n) x kd 1.7, R2 depths 2.5/3/3.5/4/5 sigma, risk budget
0.442 (gap 0.02), gross cap 2.0 per phase sub-account, close5 4-sigma stop +
8-sigma backstop + TP 1 sigma + timeout at the next 4h open, stop-first,
live offsets 16..238 (no fill in minutes 0..15), gate costs (maker 0.0002 /
taker 0.00055, longs pay 0.0001 per 8h settlement held). Core functions
vendored VERBATIM from oc_crash2020/crash.py.
FIDELITY GATE: PASS - the vendored core replayed oc_crash2020 window W1
(2020-03-12, 10-day sim) from the old perp store and matched results.json
cells W1_covid0312|s{0..3}|G2 bit-for-bit on all 12 simulate-level fields
(end_equity, min_marked, max_loss, max_DD, peak_gross, fills, stops, tps,
timeouts, gap_stops, gap_max, worst_minute). tmp/gate.json.
Full numbers in results.json (presample ledger checksum 1be0b1ef6c2c2976,
9732 rung rows; reference checksum d744f20c284e23d7, 22306 rows).

## Data (Binance SPOT 1m, sha256-verified, genuinely new)

data/raw/spot_1m_presample_20261007/: BTCUSDT 2017-08..2020-09, ETHUSDT
2017-08..2020-09, BNBUSDT 2017-11..2020-09 (2017-10 404), XRPUSDT
2018-05..2020-09 (2018-04 404); every monthly zip sha256-verified against
its .CHECKSUM (manifest.json lists all 131 zips). SOL has no pre-2020-08
data: pre-sample legs use the 4 coins (B1 n counts only coins present).
First bars: BTC/ETH 2017-08-17 04:00, BNB 2017-11-06 03:54, XRP 2018-05-04
08:11; trading starts 60 days later per coin (warm-up: BTC/ETH 2017-10-16,
BNB 2018-01-05, XRP 2018-07-03). Y2017 = [2017-10-16, 2018-01-01), BTC+ETH
only (77 days); Y2018/Y2019 full years; Y2020p = [2020-01-01, 2020-09-01)
(244 days; PLAN said 243 - exact interval is 244, metric uses exact days).
Genuine outage gaps stay NaN (never fill/trigger/exit; worst: 2010 min Feb
2018, 600-min maintenance windows; BNB additionally has ~2900 scattered
1-4 min thin-trading holes from 2017 illiquidity). Two archive artefacts
found while packing (pre-outcome, disclosed in PLAN.md): (a) 21602 rows per
symbol in 2017-12..2018-02 carry sub-minute open_time offsets (+20.8 s BTC,
+20.8 s ETH, +21.8 s BNB, +~15 s Feb-2018 chunk) - 75-99.6 % are REAL klines
(e.g. the full Dec-2017 rally), floored to the minute grid; (b) flat
zero-volume backfill rows (BTC 81, ETH 213, BNB 5349, Dec-04..18) dropped to
NaN. Without the floor fix the Dec-2017 rally would have been deleted.
Cross-check: Y2020p COVID worst minutes (s0 03-13 04:57, s2 03-13 02:16)
match oc_crash2020's perp-store W1 cells exactly - two independent stores
agree to the minute.

## Pre-sample legs (4-phase; each phase starts 1.0, compounds, reset yearly)

%/mo = geometric monthly on full equity; DD = 1m-marked incl. open rungs;
win = rung ret > 0 after costs; worst-day = worst UTC boundary day.

| leg | s0 %/mo | s1 | s2 | s3 | MEAN | s0 DD | s1 | s2 | s3 | MEAN | endEq mean | fills | stops | win |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Y2017 (BTC+ETH) | 12.48 | 9.91 | 10.21 | 10.24 | 10.71 | 6.03 | 5.18 | 4.12 | 4.81 | 5.04 | 1.294 | 909 | 30 | 87% |
| Y2018 | 2.89 | 2.45 | 2.35 | 2.32 | 2.50 | 5.98 | 9.53 | 8.65 | 9.56 | 8.43 | 1.345 | 2986 | 99 | 69% |
| Y2019 | -0.18 | 0.36 | 1.49 | 0.25 | 0.48 | 11.50 | 9.41 | 9.95 | 14.34 | 11.30 | 1.062 | 3116 | 207 | 70% |
| Y2020p | -0.04 | -1.45 | 1.00 | 1.58 | 0.27 | 16.22 | 24.53 | 15.48 | 13.85 | 17.52 | 1.026 | 2721 | 206 | 71% |

Worst single days line up with known dumps (2019-09-25 -11.7 % phase s3,
2020-03-13 -13.2 %, 2018-08-15 -3.9 %), i.e. the replay reacts to real
history. No losing pre-sample YEAR on the 4-phase mean (Y2019 s0 alone
-0.18 %/mo is a losing phase, not a losing year).

## Reference legs (same code, perp store, 5 coins incl. SOL - rules ARE in-sample here)

| leg | mean %/mo | mean DD | worst-phase DD | endEq mean | fills | win |
|---|---|---|---|---|---|---|
| R1 21-09..22-09 | 0.78 | 11.38 | 13.86 | 1.105 | 4171 | 66% |
| R2 22-09..23-09 | 0.70 | 12.76 | 15.32 | 1.089 | 4059 | 70% |
| R3 23-09..24-09 | 1.89 | 10.76 | 15.65 | 1.264 | 5352 | 75% |
| R4 24-09..25-09 | 3.01 | 5.42 | 6.23 | 1.429 | 3958 | 73% |
| R5 25-09..26-09 | 0.59 | 9.00 | 10.48 | 1.073 | 4766 | 66% |

The dip sleeve ALONE earns 0.6-3.0 %/mo on research years - far below the
full G2 pipeline (5.41 %/mo): the book carries G2, the dip sleeve harvests
rebounds at 66-75 % rung win rate. Do NOT read the R-rows as gate results
(the 5 %/mo gate applies to the full pipeline, never to a sleeve). Context
only: pre-sample 2018 (2.50 %/mo) beats R1/R2/R5; pre-sample 2019 (0.48)
is below every research year; Y2017 (10.7) beats all. No sleeve year
anywhere exceeds DD 20 % on the 4-phase mean.

## Key question

**YES for 2018 (profitable, +34.5 % year / 2.50 %/mo mean, DD 8.4 % mean /
9.6 % worst phase) and YES, barely, for 2019 (+6.2 % year / 0.48 %/mo mean,
DD 11.3 % mean / 14.3 % worst phase) - both with DD <= 20 % under the frozen
rules - but at 1/2 to 1/10 of the research-window rate, so the sleeve
transfers as a low-DD rebound harvester, not as a return engine.** 2018
survived the -80 % bear market with every phase green and DD < 10 %; 2019's
grind (207 stops, worst day -11.7 %) still ended green on the mean while one
phase (s0, -0.18 %/mo) lost. Caveats: Y2020p s1 single phase hit DD 24.5 %
(COVID; mean 17.5 %); Y2020p overlaps the research window from 2020-08, so
the fully clean evidence is Y2017-Y2019.

## Leakage / execution statement

No fitting anywhere (all constants frozen from 2020-08..2026-09 research):
sigma(j) uses 4h opens ending at j-1 (shift-1, min_periods 120); n uses
closes up to minute f-1; fills use strict low trade-through at minutes
16..238 with price lv; exits evaluated f+1..240 + next-bar open; NaN exit
price drops the rung; warm-up masks pre-eligible coins from opens, sigma AND
n-counts. Reference R-legs reuse the perp store with the identical code
path (separate runs, no cross-contamination). Spot-vs-perp caveat on every
pre-sample number: fills/exits evaluated on SPOT prices with perp gate costs
(maker 0.0002/taker 0.00055, adverse funding); perp/spot dip dynamics differ
by basis, directionally the same. Two replica limitations found and
disclosed (both inherited from oc_crash2020, gate-proven): (1) 1m marks hold
the last print through outage NaNs (reported DD is blind inside gaps -
conservative); (2) the 2.0x gross cap is enforced per-bar, so overlapping
bars stack beyond it (observed peak gross 2.07 Y2020p s2, 2.66 R4 s1) - the
cap binds calm markets, not crashes, exactly as oc_crash2020 concluded.
Tests: tests/test_oc_presample.py, 10 tests (strict fill, TP/stop-first,
funding, budget/cap, sizing, sigma causality, n causality/NaN, interval
truncation, NaN-mark hold, store window) - all pass.

## Verdict (tieng Viet, ket luan chinh)

Nam 2018 co lai +34.5%/nam (2.50%/thang, DD 8.4%) va 2019 van xanh nhe +6.2%/nam (0.48%/thang, DD 11.3%) voi luat G2 dong bang - song sot bear market -80% ma DD deu duoi 20%.
Nhung loi nhuan chi bang 1/2 den 1/10 thoi nghien cuu: dip sleeve chuyen thanh cong vai tro thu hoach rebound DD thap, khong phai dau tau loi nhuan - giu sleeve trong G2, khong tang ty trong dua tren pre-sample.
COVID 2020 cho thay 1 pha don le co the DD 24.5% (mean 4 pha 17.5%) - khong bao gio chay 1 pha don le.
