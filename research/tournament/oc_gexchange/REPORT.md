# oc_gexchange REPORT (2026-10-07)

## Setup
CHANGES (not levels) in the oc_gex dealer-GEX proxy vs G2 dip rungs, pre-registered in
PLAN.md before any outcome. Reuses oc_gex `gex_hourly_{BTC,ETH}.parquet` and its
dip-replica join unchanged (BTC series for BTC/SOL/BNB/XRP, ETH for ETH).
d(T) = GEXn(last full hour before T) - GEXn(24 h earlier); sigma(T) = trailing 90-day
std (2160 predecessors, min 720, current excluded) of 24 h changes; z = d/sigma.
Hypothesis fixed now: fast SHORTER gamma (z < -1) -> worse rungs / more stops.

## Fidelity (base reproduced exactly)
Checksum 902c5bbfe8fed3c0; base 4-phase-mean sums 0.911/0.833/2.100/3.197/0.677,
sum5y=7.718304; 22312 fills. Both hourly grids regular (vectorized j(h)=h-24 path,
identical to the search form); z finite 47305/48049 hours, join finite 100% of fills.
Costs: replica legs already net of maker 0.0002 / taker 0.00055 + settle funding.

## Descriptive (dev fills; LOW z<-1 hypothesised worst / most stops)
| year | spear(z,y10) | low | mid | high | stop l/m/h | spread* | ok |
|---|---|---|---|---|---|---|---|
| 2021-09-24 | +0.063 | +0.00303 | +0.00147 | -0.00102 | 1.0/4.2/8.5% | -19 bps | NO |
| 2022-09-24 | +0.106 | -0.01112 | +0.00305 | +0.00358 | 19.1/2.5/6.9% | +143 bps | YES |
| 2023-09-24 | -0.003 | +0.00637 | +0.00103 | +0.00396 | 0.0/6.5/0.0% | -52 bps | NO |
| 2024-09-24 | -0.006 | +0.00415 | +0.00502 | +0.00655 | 0.0/1.4/0.0% | +10 bps | YES |
\*spread = mean(z>=-1) - mean(z<-1), unweighted y10. LOW bucket small (272-654 fills/yr;
most fills MID). Weighted means agree in sign with unweighted in 4/4 years.
Sign as hypothesised in 2/4 dev years (2022, 2024); Spearman positive in 2/4.
Pre-registered rule needs 4/4 with spread > 5 bps -> T1 NOT triggered: no tilt scored,
no year-5 run (most recent year untouched).

## Leakage checks
Feature timing: i0 = last hour_end <= bt-1min; 24 h leg 24 h before that hour;
sigma uses only changes with hour_end < i0 (current excluded). Label windows: rung
outcomes after the fill, never in GEX. Fit windows: none (threshold -1 fixed in PLAN.md
before any outcome). Fill timing: replica unchanged.

## Verdict
VERDICT: REJECT. GEX changes show no consistent edge: hypothesised sign holds in only
2/4 dev years (2021 LOW is best, 2023 LOW is best); the 2022 crash-year effect (+143 bps,
19% stops) does not repeat. T1 (x0.7 when z<-1) stays unscored per plan. No engine run.
A negative result: neither GEX levels (oc_gex) nor GEX changes gate dip rungs; close
this direction unless a new pre-registered mechanism is proposed.

## Vietnamese verdict
1. Bác bỏ: thay đổi GEX không dự báo rung dip ổn định (đúng dấu 2/4 năm, 2021 và 2023 ngược dấu).
2. Không chạy tilt/engine, không dùng năm gần nhất để chọn (T1 chưa đủ điều kiện 4/4 + spread 5 bps).
3. Đóng hướng GEX (cả mức lẫn thay đổi); chỉ mở lại với giả thuyết cơ chế mới, đăng ký trước.
