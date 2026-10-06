# oc_phaserebal REPORT — phase-sub-account rebalancing for R2B1D17BF (2026-10-06; PLAN pre-registered before any outcome)

Question: R2B1D17BF runs four phase sub-accounts (shifts s=0..3) at 1/4 capital
each, never rebalanced. Does moving capital back to equal weight cut drawdown
without lowering return? Arms on v411_runs.pkl R2B1D17BF via v388.hourly grid
g0=2021-09-24 04:00 .. g1=2026-09-23 12:00 UTC: (a) no-rebal = reset_metric.
year_reset reproduced EXACTLY (imported, matches v411_result.json to 1e-9);
(b) MONTHLY equalise on each 1st 00:00 UTC (60 rebalances, 2021-10-01..2026-09-01);
(c) WEEKLY equalise each Monday 00:00 UTC (261 rebalances, 2021-09-27..2026-09-21).
Zero transfer cost; open positions scaled (bot resizes at next order). Per-year
R = monthly geo mean, DD = 1m-marked, same pk convention for all arms; 5y R5 =
geo mean of the five monthlies. All five years are research data; needs
prospective validation. Repro: research/tournament/oc_phaserebal/{PLAN.md,
compute_rebalance.py, results.json}; test tests/test_oc_phaserebal.py. LIGHT:
one process, ~44k hourly rows, no 1m data.

## Per anchor year %/month (R) and 1m-marked DD (%), arms (a)/(b)/(c)

| year | (a) R | (a) DD | (b) R | (b) DD | (c) R | (c) DD |
|---|---|---|---|---|---|---|
| 2021-09-24 | 2.831 | 12.42 | 2.757 | 12.36 | 2.742 | 12.36 |
| 2022-09-24 | 3.505 | 16.23 | 3.525 | 16.29 | 3.529 | 16.20 |
| 2023-09-24 | 4.669 | 18.33 | 3.947 | 18.77 | 3.812 | 18.77 |
| 2024-09-24 | 11.270 | 8.26 | 11.305 | 8.10 | 11.298 | 8.10 |
| 2025-09-24 | 5.060 | 12.81 | 5.047 | 12.74 | 5.054 | 12.70 |

## 5y return, max yearly DD, full-path DD (4h / 1m / gate)

| arm | R5 %/mo | max yearly DD | full 4h | full 1m | full gate |
|---|---|---|---|---|---|
| (a) no-rebal | 5.425 | 18.33 | 15.34 | 16.90 | 16.90 |
| (b) monthly | 5.272 | 18.77 | 17.00 | 18.77 | 18.77 |
| (c) weekly | 5.243 | 18.77 | 17.00 | 18.77 | 18.77 |

## Decision (pre-registered rule)
- DD not-worse vs (a) (tol 0.005pp): (b) 3/5 years (worse 2022, 2023), (c) 4/5 (worse 2023 only, -0.44pp).
- 5y return gap vs (a): (b) -0.153pp, (c) -0.182pp → "not lower" FAILS for both.
- LOYO on DD effect (mean gap excl. one year >= -0.005): (b) 1/5, (c) 1/5 → FAILS.
- Specific pass: (b) false, (c) false. Default pass: (b) false, (c) false.

Verdict: NOT PROMISING — neither monthly nor weekly rebalancing cuts max yearly DD in >=4/5 years while holding the 5y return; both lower the 5y return and raise the worst-year/full-path DD (2023 drives the failure).
