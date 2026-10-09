# oc_gex REPORT (2026-10-07)

## Setup
Dealer-GEX proxy from Deribit strike-level hourly trades (BTC+ETH, 2021-01..2026-09;
overlap months byte-identical, deduped): q=cumsum(taker_buy-taker_sell) per
instrument; GEX=-sum q*Gamma_BS(r=0)*S^2*0.01 over alive (t<expiry+8h UTC);
iv=last vwap_iv as-of (raw is PERCENT, [1,990)->/100->clip[0.05,3.0]); S=hourly
median index; GEXn=GEX/(S*N30), N30=trailing 720h mean notional (pre-registered;
z-score rejected). Proxy from 2021-04-01. Dip side: exact oc_placebo_dip replica
(D0 outcomes, B1 sizes, 4 phases, majors x R2 rungs) + how10 column; join GEXn of
last full hour before each bar open (BTC series for BTC/SOL/BNB/XRP, ETH for ETH).

## Fidelity (base reproduced exactly)
Checksum 902c5bbfe8fed3c0; base 4-phase-mean sums 0.911/0.833/2.100/3.197/0.677,
sum5y=7.718304; 22312 fills; join finite 100%. Left-censoring: alive+listed at
2021-04-01 = 248 BTC / 221 ETH instruments, older (first trade <=2021-01-15) = 0,
|q|-at-start share 0.000 (pre-start notional in older, all expired, 0.48/0.44).

## Sanity (no dip outcomes; vol corr dev-only)
Median GEXn < 0 everywhere (dealers net short gamma): BTC -4.7e-06, ETH -1.0e-04;
expiry-Friday 00-08h slightly more negative; 2022 crash months mixed (no pinning
story). GEXn vs subsequent 24h realised vol (dev only, expect NEGATIVE): pooled
+0.11 BTC / +0.24 ETH; per-year 1/4 negative each (only 2024). Mechanism rejected.

## Descriptive (dev fills; HIGH GEXn hypothesised better/fewer stops)
| year | spear | bottom | middle | top | stop b/m/t |
|---|---|---|---|---|---|
| 2021-09-24 | +0.120 | -0.00248 | +0.00373 | +0.00262 | 7.1/3.0/3.2% |
| 2022-09-24 | -0.030 | +0.00312 | -0.00182 | +0.00125 | 3.5/7.8/6.3% |
| 2023-09-24 | +0.059 | +0.00327 | +0.00131 | -0.00023 | 3.5/7.6/6.3% |
| 2024-09-24 | -0.086 | +0.00418 | +0.00608 | +0.00487 | 1.2/2.1/0.2% |
Sign as hypothesised (top>bottom) in 2/4 dev years (2021, 2024); Spearman and
tercile order disagree in 2023/2024 (non-monotonic). Pre-registered rule needs
>=3/4 -> T1 NOT triggered: no tilt scored, no year-5 run (nothing to select).

## Verdict
VERDICT: REJECT. Dealer-GEX proxy builds cleanly and is leakage-free, but shows
no consistent edge: 2/4 sign years, pooled vol corr positive (wrong sign), no
expiry-day effect. T1 (x1.25 top / x0.75 bottom) stays unscored per plan. No
engine run. A negative result: GEX level does not gate dip rungs; do not revisit
without a new hypothesis (e.g. GEX *changes*, not levels).

## Vietnamese verdict
1. Bác bỏ: GEX dealer không dự báo rung dip (đúng dấu 2/4 năm, tương quan vol sai dấu).
2. Không chạy engine, không dùng năm gần nhất để chọn (T1 còn chưa đủ điều kiện).
3. Hướng mới (nếu có): thử thay đổi GEX theo giờ thay vì mức GEX, đăng ký trước rồi mới test.
