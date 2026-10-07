# oc_kellydip REPORT: analytical Kelly/DD sizing of the dip sleeve (descriptive)

Universe: 5498 majors R2 rung fills (y1.0) over the 5 walk-forward years; unit =
R2 base per-rung notional; deployed `f_dep = 1.7`. `n` = distinct other majors
coins with an R2 fill in the same 4h bar within ±15 min (timestamp-only).

## n histogram (share of fills; timestamp-clustered, cf. b1shape's 1m-detection n)

| year | n=0 | n=1 | n=2 | n=3 | n=4 | fills |
|---|---|---|---|---|---|---|
| 2021-09-24 | 0.184 | 0.137 | 0.228 | 0.147 | 0.303 | 990 |
| 2022-09-24 | 0.223 | 0.186 | 0.215 | 0.141 | 0.235 | 1045 |
| 2023-09-24 | 0.214 | 0.144 | 0.167 | 0.158 | 0.317 | 1330 |
| 2024-09-24 | 0.246 | 0.152 | 0.219 | 0.222 | 0.161 | 989 |
| 2025-09-24 | 0.155 | 0.117 | 0.127 | 0.155 | 0.447 | 1144 |
| overall | 0.203 | 0.146 | 0.188 | 0.164 | 0.299 | 5498 |

## Kelly growth-optimum per year (flat A: z=y1.0; shrunk B: z=y1.0/(1+n))

| year | f*_flat | G*_flat | G(1.7)_flat | 1.7/f*_flat | f*_shr | G*_shr | G(1.7)_shr | 1.7/f*_shr |
|---|---|---|---|---|---|---|---|---|
| 2021 | 5.53 | 0.01272 | 0.00584 | 0.31 | 15.43 | 0.01946 | 0.00325 | 0.11 |
| 2022 | 0.52 | 0.00010 | -0.00049 | 3.27 | 2.77 | 0.00095 | 0.00080 | 0.61 |
| 2023 | 6.13 | 0.01619 | 0.00627 | 0.28 | 18.67 | 0.02709 | 0.00347 | 0.09 |
| 2024 | 6.46 | 0.01772 | 0.00654 | 0.26 | 5.94 | 0.00742 | 0.00293 | 0.29 |
| 2025 | 3.89 | 0.00289 | 0.00189 | 0.44 | 18.34 | 0.00832 | 0.00129 | 0.09 |

## Daily-sum DD fractions per year (maxDD_1 at f=1; f_DD15/20 hit 15%/20%)

| year | maxDD_1 flat | f_DD15 flat | f_DD20 flat | DD(1.7) flat | 1.7/f_DD20 flat | maxDD_1 shr | f_DD15 shr | f_DD20 shr | DD(1.7) shr | 1.7/f_DD20 shr |
|---|---|---|---|---|---|---|---|---|---|---|
| 2021 | -0.435 | 0.34 | 0.46 | -0.74 | 3.70 | -0.202 | 0.74 | 0.99 | -0.34 | 1.72 |
| 2022 | -2.282 | 0.07 | 0.09 | -3.88 | 19.40 | -0.648 | 0.23 | 0.31 | -1.10 | 5.51 |
| 2023 | -0.496 | 0.30 | 0.40 | -0.84 | 4.22 | -0.136 | 1.10 | 1.47 | -0.23 | 1.16 |
| 2024 | -0.507 | 0.30 | 0.39 | -0.86 | 4.31 | -0.237 | 0.63 | 0.85 | -0.40 | 2.01 |
| 2025 | -1.269 | 0.12 | 0.16 | -2.16 | 10.78 | -0.311 | 0.48 | 0.64 | -0.53 | 2.64 |

## Verdict

Deployed x1.7 sits well below the per-year Kelly growth optima (0.26–0.44x flat, 0.09–0.61x shrunk) except 2022-flat where it exceeds Kelly 3.3x with negative growth, while sitting well above the 15/20%-DD fractions (3.7–19.4x flat, 1.2–5.5x shrunk) — growth wants more size, drawdown wants less, and the 1/(1+n) shrink narrows both gaps with 2022 as the binding year.

## Caveats

- Units are R2-base notionals summed per day, not equity: many rungs/day stack
  notionally, so DD(1.7) = -3.88 in 2022-flat is a relative benchmark, and the
  equity-DD map needs the sleeve budget/notional-to-equity scale (not modelled).
- Kelly here is sequential per-rung compounding in t_fill order within each year
  (no cross-year compounding, no overlap/capital constraint, no parameter fit).
- Flat worst-day/maxDD reproduce oc_b1shape S0 (-1.92 worst day, -2.28 maxDD).
- `min(1+1.7*z)` > 0.62 every year/weighting: no single-rung ruin at deployed.
- Descriptive only: no rule selected, no PROMISING gate, needs prospective logs.
