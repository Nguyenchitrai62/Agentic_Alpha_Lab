# oc_premexpo REPORT: are the two premium-tilt gains alpha or just extra long exposure?

Book = `forward_v205.research_books_d2` (rebuilt exactly, cell-checked vs
oc_cbpremium/oc_usdtprem); opens = v154 4h opens. Grid = 10955 bars
(2021-09-24..2026-09-23 16:00 UTC; last bar dropped, no forward open) x 5
coins = 54775 rows. BASE = raw book + v410 bear-long filter FIRST (BTC-only,
longs x0.5 when BTC 4h open < 1200-bar mean). RULE_s = BASE longs x1.15 when
z_s > 1, x0.85 when z_s < -1, else x1.0 (market-wide; shorts/flats unchanged):
s = usdt (Coinbase USDT-USD `prem = close - 1`, mean24 rolling 24/min20, z90
rolling 2160/min1728 shift 1) and s = cb (Coinbase/BTC-premium `prem = cb/bin
- 1`, same smooth/z; hourly inner join on bar START); as-of = last hourly row
with end strictly before T (`end <= T - 1s`). Combined mult =
(mult_usdt + mult_cb)/2 on BASE longs. Screen = open-to-open 4h returns with
unified gate cost 0.0002/unit turnover (oc_dvolshort mechanics, each path its
own global prev chain, first prev = 0); long-leg sums over fixed BASE-long
membership. Note: oc_usdtprem's report used 0.0005, so usdt absolute P&L here
is higher by cost only (cb reproduces oc_cbpremium's long P&L exactly:
0.156822 / 0.236864 / 0.616791 / 0.496868 / 0.253521).
Control (DIAGNOSTIC, not a rule): per-year constant long mult =
gross_rule_w / gross_base_w over base-long cells (exposure-weighted avg mult,
computed in-year); w_control = w_base x mult on longs in that year.
Placebo (DIAGNOSTIC): 500 block-shuffles by run — permute the (value,length)
run pairs of the rule mult series (same-length rebuild; total row counts per
level exact; adjacent equal-valued pairs merge on rebuild); yearly seeds
6100+i shuffle runs strictly inside year k (rest fixed); 5y seeds
9100+i shuffle full-series runs. Placebo gain = placebo long P&L - control
long P&L; percentile = 100 x mean(placebo <= rule). Full tables in
`results.json`; `panel.parquet` holds per-(T,sym) base weights + both z/mult.
z-vs-z correlation (both finite): full 0.878; by year 0.839 / 0.962 / 0.673 /
0.846 / 0.988 (2021..2025). Runs full-series: usdt 357, cb 445, combined 760.

## Per-year exposure test (net long-leg P&L, portfolio-return units)

### USDT signal

| year | avg long mult (control) | long gross w base / rule | long P&L base / rule / control | gain vs control | placebo pct (year) |
|---|---|---|---|---|---|
| 21-22 | 1.021619 | 303.569 / 310.132 | 0.153468 / 0.153095 / 0.156788 | -0.003693 | 54.2 |
| 22-23 | 0.993803 | 489.916 / 486.881 | 0.228949 / 0.236291 / 0.227529 | +0.008762 | 83.2 |
| 23-24 | 1.028160 | 566.961 / 582.927 | 0.607182 / 0.648753 / 0.624285 | +0.024469 | 98.6 |
| 24-25 | 1.026493 | 676.851 / 694.783 | 0.494588 / 0.516672 / 0.507696 | +0.008976 | 87.8 |
| 25-26 | 1.059569 | 446.968 / 473.594 | 0.235489 / 0.260091 / 0.249520 | +0.010571 | 89.4 |

5y: base 1.719676 / rule 1.814902 / control 1.765818; gain +0.049084, positive
in 4/5 years; placebo 5y pct 99.4 (mean -0.051517, sd 0.039581).

### CB signal

| year | avg long mult (control) | long gross w base / rule | long P&L base / rule / control | gain vs control | placebo pct (year) |
|---|---|---|---|---|---|
| 21-22 | 1.002781 | 303.569 / 304.413 | 0.153468 / 0.156822 / 0.153895 | +0.002928 | 56.0 |
| 22-23 | 0.993589 | 489.916 / 486.775 | 0.228949 / 0.236864 / 0.227480 | +0.009384 | 81.6 |
| 23-24 | 0.988035 | 566.961 / 560.178 | 0.607182 / 0.616791 / 0.599915 | +0.016875 | 63.4 |
| 24-25 | 1.001353 | 676.851 / 677.767 | 0.494588 / 0.496868 / 0.495258 | +0.001610 | 59.0 |
| 25-26 | 1.058009 | 446.968 / 472.896 | 0.235489 / 0.253521 / 0.249148 | +0.004372 | 83.6 |

5y: base 1.719676 / rule 1.760866 / control 1.725696; gain +0.035170, positive
in 5/5 years; placebo 5y pct 88.2 (mean -0.008337, sd 0.038409).

### Combined (average of both multipliers)

| year | avg long mult (control) | long gross w base / rule | long P&L base / rule / control | gain vs control | placebo pct (year) |
|---|---|---|---|---|---|
| 21-22 | 1.012200 | 303.569 / 307.273 | 0.153468 / 0.155034 / 0.155341 | -0.000307 | 55.8 |
| 22-23 | 0.993696 | 489.916 / 486.828 | 0.228949 / 0.236599 / 0.227505 | +0.009095 | 86.0 |
| 23-24 | 1.008097 | 566.961 / 571.552 | 0.607182 / 0.632916 / 0.612100 | +0.020816 | 91.0 |
| 24-25 | 1.013923 | 676.851 / 686.275 | 0.494588 / 0.506926 / 0.501477 | +0.005448 | 76.6 |
| 25-26 | 1.058789 | 446.968 / 473.245 | 0.235489 / 0.256923 / 0.249334 | +0.007588 | 90.8 |

5y: base 1.719676 / rule 1.788398 / control 1.745757; gain +0.042640, positive
in 4/5 years; placebo 5y pct 97.2 (mean -0.035501, sd 0.037056).

Read: all three tilts add net long exposure over 5y (avg mult 1.02-1.06 in
2025, near 1.0 before) and beat the exposure-matched constant in most years,
but random re-timing with identical run structure usually loses (5y placebo
means negative), so timing carries the edge where it passes. USDT timing is
extreme (99.4th pct); CB timing is good every year yet ordinary against its
own run structure (88.2nd pct 5y, no year above 83.6).

## Verdicts (assigned rule: ALPHA only if gain > 0 in >= 4/5 years AND 5y placebo pct >= 95; else EXPOSURE)

- USDT: ALPHA (gain > 0 in 4/5 years, 5y gain +0.049084, 5y placebo pct 99.4).
- CB: EXPOSURE (gain > 0 in 5/5 years, 5y gain +0.035170, but 5y placebo pct 88.2 < 95).
- COMBINED: ALPHA (gain > 0 in 4/5 years, 5y gain +0.042640, 5y placebo pct 97.2).

## Caveats / post-hoc log

1. No post-hoc change to hypothesis, multipliers, thresholds, seeds, or the
   verdict rule; placebo/control definitions are exactly as assigned.
2. Unified 0.0002 cost for comparability (oc_usdtprem used 0.0005); tilt
   structure and z math are bit-identical to the source studies.
3. Control and placebo are in-year diagnostics (they use in-year average
   exposure / run structure), not tradable rules.
4. Vectorised open-to-open screen only (no vol target, governor, dip sleeve,
   funding, SL/TP, or engine limit path). All five years were available when
   scored; needs prospective validation.
