# oc_b1wide REPORT (2026-10-06; PLAN pre-registered before any outcome)

## Setup
Base B1 (static bid at lv, size x 1/(1+n), n = other majors flushing) vs
B1-wide (SAME fills at SAME lv with SAME D0 exits — signal-only, majors-only
trading — but size x 1/(1+n_wide), n_wide = n + 0.5*n_alt, n_alt = alts
BCH/DOT/ETC/XLM/ATOM >= 2.5 sigma_alt below own bar open at C(T+f-1);
sigma_4h per coin as v293; maker 0.0002 / taker 0.00055; longs pay 0.0001 on
settling timeouts). Majors x R2 depths (2.5/3/3.5/4/5), bars with open in
[2021-09-24, 2026-09-24) (5 anchor years); weights renormalised per year-arm
to mean 1 (primary); daily sums by exit date UTC; maxDD of cumulative
daily-sum path from 0; eff = sum/maxDD. Base fills 5498 match oc_b1deeper B1
to the tick per coin (1067/1126/1179/1174 + 952 SOL) with identical
means/win/sums — replica validated. Alts shrink 48.6% of fills (n_alt > 0;
mean weight 0.639 -> 0.564, -12% exposure before renormalisation; mean
|w_wide/w_base - 1| = 0.155). Ledger checksum 22b4d925bac36251. All 5 years
are research data: a PROMISING result would still need prospective
validation (disclosed vs RULES.md hidden-year rule).

## Per-year base B1 vs B1-wide (renormalised w; mean in bps, win shared)
| year | BASE sum/worst/DD/eff | WIDE sum/worst/DD/eff | sum ratio | pass? |
|---|---|---|---|---|
| 2021 | 3.887/-0.720/0.720/5.40 | 3.978/-0.785/0.785/5.06 | 102.3% | sum YES, dd NO |
| 2022 | 0.272/-1.082/1.699/0.16 | 0.007/-1.107/1.897/0.00 | 2.6% | sum NO, dd NO |
| 2023 | 5.725/-0.400/0.409/14.01 | 5.831/-0.434/0.444/13.14 | 101.9% | sum YES, dd NO |
| 2024 | 3.959/-0.332/0.332/11.92 | 3.867/-0.412/0.412/9.39 | 97.7% | sum YES, dd NO |
| 2025 | 1.210/-0.903/1.130/1.07 | 0.874/-0.913/1.167/0.75 | 72.2% | sum NO, dd NO |
| FULL | 15.138/-1.138/1.787/8.47 | 14.557/-1.172/2.008/7.25 | 96.2% | — |

## Decision (PROMISING = maxDD not worse in >=4/5 yrs AND sum >=97% of base in >=4/5)
| check | score | pass? |
|---|---|---|
| S_wide >= 0.97*S_base | 3/5 (2021, 2023, 2024) | NO |
| DD_wide <= DD_base | 0/5 (worse every year) | NO |
| PROMISING | | NO |

## Notes
- The alt term fires on half the fills but reallocates toward worse tails:
  worst day is worse in 5/5 years and maxDD is worse in 5/5 years (full-path
  DD 1.79 -> 2.01, eff 8.47 -> 7.25), while the renormalised sum collapses
  in 2022 (0.27 -> 0.01) and drops 28% in 2025. Leave-one-year-out is stable:
  dd 0/4 under every omission, sum 2-3/4 — the rejection does not hinge on
  any single year.
- Because fills are shared by construction, per-fill mean/win are identical
  across arms; the entire gap is weighting. Raw (non-renormalised) sums show
  the same pattern (BASE vs WIDE: 2.39/0.18/3.81/2.58/0.71 vs
  2.15/0.00/3.38/2.21/0.46), so the verdict does not hinge on
  renormalisation either.
- Repro: `research/tournament/oc_b1wide/{PLAN.md,wide.py,run.py,
  results.json,fills.parquet}` + `tests/test_oc_b1wide.py` (13 tests pass);
  one process, peak RAM ~0.6 GB (ten float32 1m open/close arrays + one
  coin's H/L at a time).

## Verdict
VERDICT: NOT PROMISING — B1-wide keeps >=97% of the base sum in only 3/5 years and its maxDD is worse in 5/5 years, so the half-weight alt flush detector is rejected and base B1 sizing stands.
