# oc_diptilt REPORT — regime-tilted dip size proxy (IDEA #39, 2026-10-06; PLAN pre-registered)

Universe: R2B1D17BF engine replicas `oc_kpi/events_s{0..3}.parquet`
(4 phase sub-accounts, live 2021-09-24..2026-09-23+shift), TRUE rung pairing
by positional adjacency in the engine's append order (exact copy of
oc_deepcheck `pair_true`: 21,389 rungs, 0 adjacency violations, max
fill/exit weight diff 0.0, 0 outside anchor years). Year = FILL time in
anchor year `[A_k, A_k+365d)`, A = 2021..2025-09-24. `pnl` = exit weight x
engine ret (net of rung fees, fraction of sub-account equity).
Bear flag = v410 exact at T0 = floor(fill_t to standard 4h grid):
BTC 4h open[T0] < MA1200[T0] (rolling 1200, min 600, incl T0, NaN->bull),
from hourly_ext only — known at the bar open. MAIN tilt m = 1.2 bull /
0.8 bear; SENS m = 1.1 / 0.9 (reported only, never for selection).
Equity proxy per shift+year: `eq = 1 + cumsum(pnl_scaled)` sorted by exit_t
from 1.0 at the anchor; mix path per year = time-union mean of the 4 shift
paths (1/4 each, reset at anchors — the reset_metric idea).
`R_proxy = eq_end^(1/12)-1` (%/month), `DD_proxy` = max drawdown of the mix
path. APPROXIMATION: additive (no compounding), no budget/notional
interaction, no book leg (dip sleeve only). Replication: base yearly mix%
matches oc_regimetrue totals exactly (max abs diff 0.0). Base pooled
+176.65 mix%, tilt +191.02, sens +183.84. All five years are research data;
findings need prospective validation. Full numbers: `results.json`.
Repro: `research/tournament/oc_diptilt/{PLAN.md,analyze_diptilt.py,
results.json}`; test `tests/test_oc_diptilt.py`.

## MAIN: base vs tilt per anchor year (dip-sleeve proxy)

| year | n | base R%/mo | tilt R%/mo | ret? | base DD% | tilt DD% | dd? |
|---|---|---|---|---|---|---|---|
| 2021-09-24 | 4109 | 2.0722 | 1.7653 | NO | 9.0138 | 7.4823 | YES |
| 2022-09-24 | 4060 | 1.5345 | 1.5495 | YES | 8.8026 | 10.3856 | NO |
| 2023-09-24 | 4545 | 2.1328 | 2.3958 | YES | 11.7251 | 13.5081 | NO |
| 2024-09-24 | 3946 | 5.0451 | 5.7215 | YES | 2.6240 | 2.9760 | NO |
| 2025-09-24 | 4729 | 1.4855 | 1.5006 | YES | 7.7506 | 9.2193 | NO |

PASS_ret 4/5, PASS_dd 1/5. Rule: PROMISING iff ret >= 4/5 AND dd >= 4/5.

## Sensitivity x1.1/x0.9 per year (NOT for selection)

| year | sens R%/mo | ret? | sens DD% | dd? |
|---|---|---|---|---|
| 2021 | 1.9201 | NO | 8.2622 | YES |
| 2022 | 1.5420 | YES | 9.6008 | NO |
| 2023 | 2.2652 | YES | 12.6347 | NO |
| 2024 | 5.3893 | YES | 2.8049 | NO |
| 2025 | 1.4931 | YES | 8.4882 | NO |

Same pattern as MAIN (ret 4/5, dd 1/5): smaller tilt, smaller gaps.

## Bull/bear split per year (additive mix%, base -> tilt)

| year | bear n / base -> tilt | bull n / base -> tilt |
|---|---|---|
| 2021 | 3274 / +25.30 -> +20.24 | 835 / +2.60 -> +3.12 |
| 2022 | 1456 / +9.50 -> +7.60 | 2604 / +10.56 -> +12.67 |
| 2023 | 1166 / +4.32 -> +3.46 | 3379 / +24.50 -> +29.40 |
| 2024 | 318 / +4.13 -> +3.30 | 3628 / +76.39 -> +91.66 |
| 2025 | 3493 / +9.15 -> +7.32 | 1236 / +10.21 -> +12.25 |

Pooled: bear 9707 rungs +52.39 -> +41.91; bull 11682 rungs +124.26 ->
+149.11. The tilt adds (+24.85 bull) and removes (-10.48 bear) for a net
+14.37 mix% pooled — the return gain is real but concentrated in bull bars,
so the mix path scales up with it.

## Plain paragraph

Scaling dip size 1.2x in bull bars and 0.8x in bear bars does what the
regime table predicts on returns — it beats the base proxy in 4 of 5 years
(everything except 2021, where 80% of fills sit in bear bars so the 0.8x
dominates) — but it fails the second leg: the proxy drawdown is worse than
base in 4 of 5 years (only 2021 improves, the same bear-heavy year). The
mechanism is visible in the split: bull cells carry most of the P&L, so
1.2x-ing them scales both the climb and the within-year dip of the path
(2023 tilt DD 13.51 vs 11.73; 2025 9.22 vs 7.75). The gentler 1.1x/0.9x
sensitivity shows the identical 4/1 pattern with smaller gaps, confirming
this is the tilt's signature, not a 1.2-specific accident. Under the
additive no-interaction proxy this is not a free lunch — a live engine run
would additionally face budget/notional interactions the proxy ignores.

## Caveats / post-hoc log

1. No post-hoc change: one fixed multiplier pair (+ one fixed sensitivity),
   one run, no tuning; PLAN.md predates results.json (checked in test).
2. Proxy only: additive equity, no compounding inside the year, no
   risk-budget or margin interaction, dip sleeve only (book excluded), so
   R/DD levels are NOT comparable to full-strategy gate numbers — only the
   base-vs-tilt gaps within this proxy enter the rule.
3. T0 is the standard 4h grid while s=1..3 replicas run on shifted grids
   (still causal: T0 <= bar open <= fill_t); boundary fills attribute exit
   P&L to the fill year (fill-year ~= exit-year; rungs exit inside the same
   4h bar).
4. 2021 is the mirror year (bear-heavy): the only year the tilt loses
   return and the only year it improves DD — consistent, not contradictory.

## One-line verdict

NOT PROMISING: the x1.2/x0.8 tilt improves the proxy return in 4/5 years but leaves DD not-worse in only 1/5 years — no registered engine version is requested.
