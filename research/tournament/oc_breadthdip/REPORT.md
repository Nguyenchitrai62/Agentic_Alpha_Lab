# oc_breadthdip REPORT (2026-10-06; PLAN pre-registered before any outcome)

## Setup

Idea #64: when breadth = 1.0 at the bar open (all five majors' last complete
daily close above their 200-day mean), dip rung sizes x0.8; else unchanged.
BASE = oc_b1deeper B1 replica verbatim (static bid at lv = O*(1-k*sg), R2
depths 2.5/3/3.5/4/5, size 1/(1+n_fill) with v399-exact n, D0 exits from the
fill px; maker 0.0002 / taker 0.00055; longs pay 0.0001 on settling timeouts).
RULE = identical fills/nets/exit dates, only w_rule = w_base*0.8 on
breadth-on bars. Breadth from hourly_ext: D(M) = hourly close at M-1h,
SMA200(M) = mean D over M-200d..M-1d (all 200 finite), coin-up = D > SMA200
strictly, breadth_on iff all 5 up (NaN -> OFF). Bars with open in
[2021-09-24, 2026-09-24) (5 anchor years, keyed by bar open); daily sums by
exit date UTC, NO renormalisation; maxDD of cumulative daily-sum path from 0.
Breadth-on bars 2538/10956 = 23.2% (vs 23.3% in oc_grindsignal — independent
daily-close construction lands on the same extension frequency). BASE fills
5498 with per-coin 1067/1126/952/1179/1174 = oc_b1deeper B1 to the tick and
matching per-year means/win rates — replica validated. Breadth-on fills 1570
(28.6% of fills, 30.3% of weight). Ledger checksum d8bc92e4b8438ad6. All 5
years are research data: a PROMISING result would still need prospective
validation (disclosed vs RULES.md hidden-year rule).

## Per-year BASE vs RULE (raw w*y; mean in bps, win = net>0 share)

| year | BASE n/mean/win/sum/worst/DD | RULE sum/worst/DD (same n/mean/win) | sum ratio | breadth-on fill share |
|---|---|---|---|---|
| 2021 | 990/38.1/.688/2.388/-0.442/0.442 | 2.252/-0.442/0.442 | 94.3% | 10.9% (108) |
| 2022 | 1045/3.8/.695/0.183/-0.727/1.142 | 0.152/-0.727/1.112 | 83.0% | 9.7% (101) |
| 2023 | 1330/39.7/.773/3.810/-0.266/0.272 | 3.407/-0.266/0.272 | 89.4% | 42.2% (561) |
| 2024 | 989/41.1/.699/2.579/-0.216/0.216 | 2.209/-0.173/0.173 | 85.7% | 57.6% (570) |
| 2025 | 1144/13.4/.656/0.712/-0.531/0.665 | 0.709/-0.425/0.541 | 99.6% | 20.1% (230) |
| FULL | 5498/27.4/.705/9.671/-0.727/1.142 | 8.729/-0.727/1.112 | 90.3% | 28.6% (1570) |

## Decision (PROMISING = maxDD not worse in >=4/5 yrs AND sum >=95% of base in >=4/5)

| check | score | pass? |
|---|---|---|
| DD_rule <= DD_base | 5/5 (equal 2021/2023, cuts 2022/2024/2025) | YES |
| S_rule >= 95% of S_base | 1/5 (only 2025, 99.6%; others 83-94%) | NO |
| PROMISING | | NO |

## Notes

- The rule does what it was built for on the risk leg (DD never worse, cut in
  3/5 years; worst day better in 2024/2025), but the trimmed breadth-on fills
  are disproportionately winners: even with only 30% of weight gated, the
  yearly sum loses 5.7% (2021) to 17% (2022), passing the 95% bar in 1/5 years.
  The 2024 bull year is the worst trade (57.6% of fills gated, sum -14.3%).
- No post-hoc change to definitions or the decision rule. Pre-outcome code fix
  only: tz-aware Timestamp construction in run_breadthdip.py (first run
  crashed before writing any result; no outcome was seen before the fix).
- Repro: `research/tournament/oc_breadthdip/{PLAN.md,breadthdip.py,
  run_breadthdip.py,results.json,fills.parquet}` +
  `tests/test_oc_breadthdip.py` (12 tests pass); one process, peak RAM ~0.5 GB.

## Verdict

VERDICT: NOT PROMISING — breadth x0.8 never worsens maxDD (5/5 years) but keeps >=95% of the base sum in only 1/5 years, so the over-extension dip-size trim is rejected and full-size B1 stands.
