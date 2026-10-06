# oc_usdtdip REPORT (2026-10-06; PLAN pre-registered before any outcome)

## Setup

D0 replica (oc_dipexit-exact: TP 1sg, close5 stop 4sg, 8sg backstop, timeout
at next-bar open; maker 0.0002 / taker 0.00055; v293 settle funding) with
oc_b1deeper B1 sizes w = 1/(1+n_fill), majors x R2 depths 2.5..5.0, live
offsets 16..238 strict trade-through, on all four clock phases (4h grid from
2020-08-01 00:00 UTC + 0/1/2/3h), bars with open in [2021-09-24, 2026-09-24).
RULE = per-fill size x1.2 when USDT z > 1, x0.8 when z < -1, else x1.0
(z = oc_usdtprem-exact: Coinbase USDT-USD prem = close-1, mean24 rolling 24,
z90 trailing-2160 shift-1, as-of last hourly row ending strictly before the
4h bar open; 47240 rows 2021-05-04..2026-09-23, median +0.5 bps — same source
as oc_usdtprem). Control = per (year, phase) constant avg mult (exposure
matched within each year-phase cell). 22312 fills, checksum 0d6f95d529edfd4f.

## Replica fidelity (base, B1 raw w*y)

Phase-0 fills/coin 1067/1126/952/1179/1174 = oc_dipexit exactly; phase-0 raw
sums 2.388/0.183/3.810/2.579/0.712 = oc_stoptf D0 to 1e-3; 4-phase-mean base
sums 0.911/0.833/2.100/3.197/0.677 and DDs 0.856/0.951/0.800/0.355/0.607 =
oc_placebo_dip base exactly (5y base 7.718). The y1.0-only pairing differs
nowhere from the placebo 3-leg pairing on this grid.

## Per-year 4-phase means (w*y units; win equal-weight, identical membership)

| year | S base / rule / ctrl | n | win | W base / rule | DD base / rule | fill up/down | bar up/down | avg mult | gain vs ctrl |
|---|---|---|---|---|---|---|---|---|---|
| 21-22 | 0.911 / 0.778 / 0.862 | 1043 | .660 | -0.740/-0.861 | 0.856/0.930 | .130/.393 | .179/.216 | 0.948 | -0.084 |
| 22-23 | 0.833 / 0.923 / 0.810 | 1015 | .699 | -0.726/-0.629 | 0.951/0.846 | .055/.196 | .056/.127 | 0.972 | +0.113 |
| 23-24 | 2.100 / 2.157 / 2.156 | 1338 | .748 | -0.735/-0.735 | 0.800/0.806 | .270/.136 | .212/.178 | 1.027 | +0.001 |
| 24-25 | 3.197 / 3.236 / 3.243 | 990 | .734 | -0.274/-0.274 | 0.355/0.360 | .263/.191 | .208/.168 | 1.014 | -0.008 |
| 25-26 | 0.677 / 0.671 / 0.633 | 1193 | .661 | -0.508/-0.508 | 0.607/0.604 | .172/.514 | .215/.269 | 0.931 | +0.039 |

Per-phase rule sums (p0..p3): 21: 2.173/0.793/0.620/-0.473;
22: 0.383/1.415/1.348/0.547; 23: 3.940/1.356/2.741/0.590;
24: 2.667/3.202/3.514/3.560; 25: 0.716/0.341/0.682/0.945
(base p0..p3 in results.json; rule signs agree with base in 19/20 cells).

## Decision (PROMISING needs all three)

| leg | score | pass? |
|---|---|---|
| (a) Sbar_rule >= Sbar_base | 3/5 (22, 23, 24; 21: -0.133, 25: -0.006) | NO |
| (a) DDbar_rule <= DDbar_base + 0.01 | 4/5 (only 21 fails, +0.074) | YES |
| (b) 5y 4-phase-mean dSum >= +0.273 | +0.047 (7.765 vs 7.718) | NO |
| (c) gain over exposure-matched control > 0 | 3/5 (22: +0.113, 23: +0.001, 25: +0.039; 21: -0.084, 24: -0.008) | NO |
| PROMISING | | NO |

## Notes

- The tilt's timing is real in 2022 (+0.113 over control while running a
  0.97 average mult) and visible in 2025 (beats control +0.039 despite a
  0.93 exposure drag from 51% down-tilted fills), but 2024's small edge over
  base (+0.038) is pure exposure (control wins by 0.008) and 2021 loses on
  both legs (-0.133 sum, +0.074 DD).
- The 5y delta +0.047 is 17% of the +0.273 placebo-p95 gate: indistinguishable
  from a lucky reweighting (shape-A placebo sd was 0.259).
- No post-hoc change to hypothesis, thresholds, multipliers, or the decision
  rule. Market data up to 2026-09-24 00:00 UTC was read per the assignment
  (all five years are research data; disclosed vs RULES.md hidden-year rule).
  One process, peak RAM ~0.2 GB (float32 1m O/C + one-coin H/L).
- Repro: research/tournament/oc_usdtdip/{PLAN.md,core.py,compute_usdtdip.py,
  results.json,panel.parquet} + tests/test_oc_usdtdip.py (10 tests pass).

## One-line verdict

NOT PROMISING: USDT dip-size tilt (x1.2 when z > 1, x0.8 when z < -1) beats the B1 base in only 3/5 years with a 5y 4-phase-mean delta of +0.047 (< +0.273 placebo gate) and beats its exposure-matched control in only 3/5 years — no transfer of the book-long USDT edge to dip rungs.
