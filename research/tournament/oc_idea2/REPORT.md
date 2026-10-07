# oc_idea2 REPORT: per-coin dip close-stop (XRP 5.5sg, rest 4sg)

## Setup

Rung-level replica of oc_dipexit D0 (v293 Asset/outcomes) for LONG dip rungs
(majors, rungs 2.5/3/3.5/4/5 sigma below the 4h bar open; fills offsets
16..238 on strict low<level trade-through; 5m-block CLOSE stop on absolute
clock, 8sg backstop, TP 1.0sg limit, timeout at next-bar open; maker
0.0002 / taker 0.00055; longs pay 0.0001 on settling timeouts). Bars with open
in [2021-09-24, 2026-09-24) (5 anchor years); 1m read to 2026-09-24 00:00
(timeout opens only); one coin in memory at a time, one process. U = uniform
close-stop 4.0sg (= D0); V = XRP 5.5sg, BTC/ETH/SOL/BNB 4.0sg (ONE
pre-registered pair; backstop/TP/clock/fees unchanged; stop affects exits
only, fills identical). Paired rungs kept only if U and V both finite ->
5498 rungs (BTC 1067, ETH 1126, SOL 952, BNB 1179, XRP 1174). Uniform leg
reproduces oc_dipexit D0 yearly sums EXACTLY (max|sum diff| = 0.0). Year =
bar-open anchor year; daily sums by exit date (UTC). Win = net > 0 strictly.
All 5 years are research data per assignment (disclosed vs RULES.md
hidden-year rule); a PROMISING screen still needs prospective validation.

## Per-year rung stats (n paired; mean/win/sum over rungs; worst-day / max-DD of exit-day sums)

| year | U uniform-4sg mean/win/sum/worst/DD | V XRP-5.5sg mean/win/sum/worst/DD | D = V-U sum |
|---|---|---|---|
| 2021 | .00381/.688/3.7766/-0.430/-0.454 (n990) | .00382/.689/3.7816/-0.486/-0.486 | +0.0050 |
| 2022 | .00038/.695/0.3933/-1.924/-2.282 (n1045) | .00054/.696/0.5600/-1.747/-2.115 | +0.1667 |
| 2023 | .00397/.773/5.2761/-0.495/-0.495 (n1330) | .00412/.774/5.4827/-0.482/-0.482 | +0.2066 |
| 2024 | .00411/.699/4.0658/-0.507/-0.507 (n989) | .00431/.699/4.2644/-0.507/-0.507 | +0.1986 |
| 2025 | .00134/.656/1.5380/-1.018/-1.269 (n1144) | .00134/.656/1.5380/-1.018/-1.269 | +0.0000 |
| FULL | .00274/.705/15.0498/-1.924/-2.282 (n5498) | .00284/.706/15.6267/-1.747/-2.115 | +0.5768 |

LOO mean D excl. year: +0.1430/+0.1025/+0.0926/+0.0946/+0.1442 (5/5 > 0).
Worst-day-not-worse (V >= U): 4/5 years (only 2021 worse: -0.486 vs -0.430;
2022/2023 better, 2024/2025 tied). Full-path worst day -1.747 vs -1.924 and
maxDD -2.115 vs -2.282 both improve under V.

## Per-coin context (yearly sums U -> V; XRP stop-hit rate U -> V)

Non-XRP coins coincide by construction (same M=4 stops; verified equal).
XRP only:

| year | XRP n | sum U -> V | stop rate U -> V |
|---|---|---|---|
| 2021 | 206 | 0.6982 -> 0.7032 | .0485 -> .0146 |
| 2022 | 206 | 0.8106 -> 0.9773 | .0340 -> .0146 |
| 2023 | 320 | 0.6699 -> 0.8765 | .0406 -> .0250 |
| 2024 | 220 | 1.3286 -> 1.5271 | .0182 -> .0045 |
| 2025 | 222 | 0.9861 -> 0.9861 (tie) | .0000 -> .0000 (no stops either way) |

The 2025 tie is exact (zero XRP close-stop hits under both distances that
year), not a rounding artifact.

## Decision (PROMISING = D>0 in >=4/5y AND LOO D>0 in >=4/5 AND worst-day-not-worse in >=4/5)

D>0 in 4/5 years (2021-2024; 2025 tie = 0); LOO>0 in 5/5; worst-day-not-worse
in 4/5 (only 2021 worse). All three pre-registered bars met.

## Verdict

PROMISING: per-coin close-stop (XRP 5.5sg, rest 4sg) beats uniform 4sg in 4/5 years with LOO>0 in 5/5 and worst-day-not-worse in 4/5 (+0.577 total sum, full-path worst-day/DD improve).

## Caveats / repro

- No post-hoc change: the single (4.0, 5.5) pair, the replica/priority/fee
  definitions, and the 3-part decision rule were all pre-registered in PLAN.md
  before any outcome was computed.
- Effect is XRP-only and modest (+0.58 sum over 5y, ~+3.8% of the uniform
  total); 2025 contributes nothing (no XRP stops under either distance).
  2021's worst day worsens (-0.486 vs -0.430) while its sum barely moves
  (+0.005): the tail trim is not free in every year.
- Repro: `research/tournament/oc_idea2/{PLAN.md,analyze_idea2.py,
  results.json,REPORT.md}` (majors 1m only, one coin at a time, RAM < 1 GB) +
  `tests/test_oc_idea2.py`.
