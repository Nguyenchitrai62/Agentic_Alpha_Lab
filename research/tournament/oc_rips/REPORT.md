# oc_rips REPORT: regime-conditional rip-sell ladder

Setup, exits, regimes, rules and the PROMISING gate are all pre-registered in
PLAN.md (fixed before any outcome was computed). 5 majors x k {2.5,3.0,4.0},
pooled per rule x anchor year. Costs: maker 0.0002 / taker 0.00055, no funding.

## Verdict: NO rule is PROMISING (all fail gate i, and the 5y sum is negative)

Mean net per fill (bps) / n — years 21-22 .. 25-26 | 5y sum | daily-sum DD:
- UNCOND: +2.2 / -14.5 / -7.3 / -24.1 / -7.1 | sum -3.71 | DD 4.49 (0/5 yrs >+5)
- R1 (below200): +4.3 / +14.7 / -38.9 / -21.8 / -4.6 | sum -0.39 | DD 1.22
- R2 (trend90<0, calm): +30.6 / +26.6 / -23.6 / -139.2 / -40.4 | sum -0.36 | DD 1.57
- R3 (breadth<0.4): -0.1 / +1.7 / -13.3 / -41.7 / +9.9 | sum -0.35 | DD 1.62
- DIP reference (same code mirrored): +36.0 / +15.7 / +39.4 / +37.6 / +10.4,
  5y sum +11.68, DD 1.28 — positive in all 5 years (win 64-77%).
Gate (iii) needs DD < 2x dip DD = 2.56: UNCOND fails (4.49); R1-R3 pass (iii)
but fail (i) 1-2/5 yrs >+5bps and (ii) negative 5y sum.

## Support: LOYO sign match / daily-PnL corr vs dip

LOYO (held-year mean sign vs other-4y mean): UNCOND 4/5 (consistently
negative), R1 2/5, R2 1/5, R3 2/5 — conditional signs are unstable.
Corr(daily PnL, dip): UNCOND 0.04, R1 0.08, R2 0.03, R3 0.08 — near-zero
(diversifying direction, but negative edge). Rip win rates are 51-69% with
negative means: small TP wins vs large stop/timeout losses.

## Caveats / post-hoc log

1. No outcome-driven changes. Two pre-outcome fixes: `is_bar.to_numpy()`
   crash fix in run.py (numpy array has no to_numpy); float-tolerance asserts
   in tests. Regimes recomputed from 1m (full span) instead of the parquet
   (ends 2026-09-01); cross-check overlap: trend90 med|d|=0.014 (hourly 23:00
   vs 1m last-minute close), volratio 0.0, breadth50 0.088 (5 majors vs 35).
2. R2 2024 (n=33, -139 bps) shows regime gates thin fills; tail dominates.
3. Causality: 20-day truncation test + 3 synthetic exit paths pass
   (tests/test_oc_rips.py, 5 passed). Fills >= minute 16, exits after fill,
   sigma/regimes known at bar open/day start, data < 2026-09-24.
4. Side observation only: the mirrored dip with this exit stack is positive in
   all 5 years — reported, not selected (needs its own pre-registered study).
   Any rip finding needs prospective validation.
