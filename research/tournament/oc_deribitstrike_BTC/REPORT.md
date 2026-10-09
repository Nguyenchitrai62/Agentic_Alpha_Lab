# oc_deribitstrike_BTC REPORT

Sample months: 2021-06, 2023-03, 2025-06

## Check 1: rebuild 4h iv_otm_put (notional-weighted OTM puts, strike<index, DTE<=60)
Ref: data/raw/deribit_opt_20260926/BTC_options_4h.parquet.

| month | bars | corr | median_abs_diff | mean_abs_diff | bias |
|---|---|---|---|---|---|
| 2021-06 | 180 | 0.9998 | 0.016 | 0.101 | -0.007 |
| 2023-03 | 186 | 0.9997 | 0.021 | 0.101 | -0.001 |
| 2025-06 | 180 | 0.9992 | 0.016 | 0.063 | 0.013 |

Expected: small differences (hour-level amount-weighted VWAP re-aggregated by
notional vs trade-level notional weighting; DTE/index sampled hourly vs per trade).
Large/bias differences would need explanation.

## Check 2: coverage (per month)

| month | trades | instruments | hours | weekly-put-hour share | protective-put-hour share |
|---|---|---|---|---|---|
| 2021-06 | 205616 | 951 | 720 | 0.529 | 0.514 |
| 2023-03 | 329850 | 1582 | 744 | 0.605 | 0.647 |
| 2025-06 | 348230 | 1815 | 720 | 0.531 | 0.740 |

Weekly-put = put trade 5..9 DTE, strike/index 0.85..0.98. Protective-put = 20..40 DTE, 0.70..0.90.

