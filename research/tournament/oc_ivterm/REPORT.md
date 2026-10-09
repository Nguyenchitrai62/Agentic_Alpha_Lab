# oc_ivterm REPORT (2026-10-07; PLAN pre-registered before any outcome)

## Setup

Term structure TS(h) = 7-day ATM IV / DVOL, hourly, known at end of h.
IV_7d_ATM = amount-weighted vwap_iv over last 6h of strike rows with 3..10d to
expiry and |K/index-1| <= 2% (calls+puts); < 0.5 coin in window -> NaN, carry
last value up to 24h. DVOL = last closed hourly DVOL candle. BTC and ETH
separately; SOL/BNB/XRP use BTC's TS (disclosed). Data:
`data/raw/deribit_strike_20261007/{BTC,ETH}` + `_b` (deduped), DVOL
`data/raw/deribit_dvol_20261005`. Signal join: last FULL hour before the 4h
bar open (merge_asof T-1h backward). Dip base: read-only
`oc_depthtilt/fills.parquet` (D0+B1, 4 phases, R2 rungs). Dev years only
Y0..Y3 (2021-09-24..2025-09-23); most-recent year never used. Full numbers:
`results.json`. Repro: `compute_ivterm.py` via heavy_slot --tag oc_ivterm.

## Fidelity

Uncapped 4-phase-mean base sums per year 0.9113/0.8326/2.0998/3.1974/0.6772 =
placebo ref to 1e-6; base_sum5y 7.7183 (expect 7.718). Join NaN share 0.0%
(TS finite everywhere in dev; carry covers all gaps). n fills Y0..Y3:
4171/4059/5352/3958.

## D1 hourly TS distribution (dev years)

| year | BTC mean/med/p10/p90 | BTC inv share | ETH mean/med/p10/p90 | ETH inv share |
|---|---|---|---|---|
| 2021 | 0.887/0.880/0.818/0.956 | 3.9% | 0.879/0.869/0.802/0.964 | 5.2% |
| 2022 | 0.867/0.873/0.744/0.971 | 5.9% | 0.872/0.879/0.766/0.966 | 4.7% |
| 2023 | 0.917/0.910/0.807/1.030 | 14.7% | 0.923/0.916/0.830/1.018 | 13.5% |
| 2024 | 0.919/0.907/0.812/1.034 | 15.0% | 0.971/0.969/0.856/1.079 | 29.7% |

Contango on average (TS ~0.87-0.97, cf. oc_vrprobust Friday ratio ~0.87);
inversion (TS>1) rare in 2021-22 (4-6%) but common in 2023-24 (15-30% ETH).

## D2 dips by TS tercile (in-year cuts) and inversion, dev years

mean_wy = mean(w*ret) per rung; mean_ret bps = unweighted rung economics;
stop = close5-stop + backstop rate.

| year | Lo mean_ret / stop | Mid mean_ret / stop | Hi mean_ret / stop | sign | spread |
|---|---|---|---|---|---|
| 2021 | +24.8 / 2.5% | +18.7 / 4.0% | -5.2 / 6.8% | -1 (high worse) | -29.9 bps |
| 2022 | -50.2 / 11.4% | +48.2 / 1.0% | +28.2 / 5.2% | +1 (high BETTER) | +78.4 bps |
| 2023 | +48.0 / 1.3% | +11.9 / 5.0% | -16.4 / 11.2% | -1 (high worse) | -64.4 bps |
| 2024 | +54.1 / 0.2% | +61.7 / 0.5% | +35.2 / 2.9% | -1 (high worse) | -18.9 bps |

Inversion split TS>1 vs <=1: 2021 +13.5 vs +12.6 (better); 2022 +35.8 vs +3.3
(better); 2023 -31.3 vs +32.7 (worse); 2024 +38.7 vs +57.6 (worse). Stop rate
rises with TS in 3/4 years (2021: 2.5->6.8%; 2023: 1.3->11.2%; 2024:
0.2->2.9%) but 2022 is U-shaped (Lo 11.4% worst). Spreads are all > 5 bps in
magnitude (4/4), but the SIGN is 3x worse / 1x better -> candidate rule
(same sign 4/4) FAILS. No tilt scored (per PLAN, correctly).

## D3 book: Spearman IC(TS_used, next-24h vol-normalised return), dev years

| coin | 2021 | 2022 | 2023 | 2024 |
|---|---|---|---|---|
| BTC | -0.014 | +0.004 | -0.005 | +0.067 |
| ETH | +0.040 | -0.009 | +0.009 | +0.011 |
| SOL | +0.021 | -0.013 | -0.007 | +0.050 |
| BNB | +0.051 | -0.042 | +0.028 | +0.035 |
| XRP | +0.016 | +0.032 | +0.025 | +0.108 |

All |IC| <= 0.11, 13/20 below 0.03; no coin has a consistent sign across 4
years (BTC - + - +; ETH + - + +; SOL + - - +; BNB + - + +; XRP + + + + except
XRP 4x positive but 0.016-0.108, tiny). No book signal; no rule from BOOK.

## Why 2022 flips (post-hoc description, not selection)

2022's Lo tercile concentrates the year's stop cluster (11.4% stop rate vs
1.0% Mid): low-TS (calm contango) dips caught the protracted 2022 drawdown
trend, while high-TS hours sat out or mean-reverted faster. In 2023 the mirror
holds (Hi stop 11.2% vs Lo 1.3%). The state interacts with the year's trend
regime rather than acting as a uniform dip filter -- consistent with
oc_dvol's lesson (level adds risk, not edge) now extended to slope.

## Leakage checks (how verified)

Strike window (h-5h..h] uses only row.hours ending <= signal hour_end;
DVOL = candle starting at h (ends hour_end), ffilled; join = last hour with
hour_end <= T (T-1h merge_asof backward -- truncation test in
tests/test_oc_ivterm.py recomputes 5 sampled fills from series truncated at
T-1h and matches); BOOK sigma excludes the bar (shift-1), labels post-open
only; p80 path (not executed) would use hourly history before anchor-7d;
D2 terciles are in-year descriptives, never sizing; no 2025-09-24+ row enters
any cut, sign, or threshold (dev mask asserted in test).

## Verdict

NOT A CANDIDATE: tercile sign is high-TS-worse in 3/4 dev years but flips in
2022 (+78 bps the other way), and the inversion split flips 2/2; book ICs are
~0 with no consistent sign. Per the pre-registered rule no tilt is scored and
none is requested from the leader. Term-structure level/slope as a static dip
size tilt is rejected; a regime-conditional use (if ever) needs a new
pre-registered direction and prospective evidence.

## Vietnamese verdict (3 lines)

- Tu choi: TS cao -> dip te hon chi dung 3/4 nam dev, nam 2022 dao nguoc manh (+78 bps) nen khong dat quy tac ung vien 4/4, khong cham tilt nao.
- BOOK IC ~0 o moi coin/nam, khong co dau on dinh; inversion TS>1 luc tot luc xau theo nam.
- De nghi: dong huong tilt co dinh nay; neu muon dung TS thi phai dang ky huong moi theo che do trend + bang chung prospective.
