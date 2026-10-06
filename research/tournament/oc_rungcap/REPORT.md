# oc_rungcap REPORT (2026-10-06; PLAN pre-registered before any outcome)

## Setup

B1 base (oc_b1deeper-exact: static bid at lv = O(T)*(1-k*sg), strict
low < lv fill on offsets 16..238, size 1/(1+n), D0 exits from lv with
maker 0.0002 / taker 0.00055, fund 0.0001 on settling timeouts) vs CAP
(same fills, then per (coin, 4h bar) keep the first 3 by (fill minute f
ASC, rung k ASC) and cancel the rest; bot-executable at minute
granularity; same-minute multi-level trade-throughs serialised by k).
Majors x R2 depths (2.5/3/3.5/4/5), bars with open in [2021-09-24,
2026-09-24) (5 anchor years); n = other majors with C(T+m-1) <=
O(T)*(1-2.5*sg(T)), v399-exact. PRIMARY scoring = raw w*y daily sums by
exit date UTC (no renormalisation: the cap changes exposure); maxDD of
the cumulative daily-sum path from 0 within each year. Base replica
validated: 5498 fills = oc_b1deeper B1 to the tick per coin
(1067/1126/952/1179/1174) with matching renormalised sums. Cap keeps
4571, removes 927. Ledger checksum ddb1792985ab5025 (base-only ledger;
b1deeper's 47fcb772de97b005 covers B1+DEEP). All 5 years are research
data: a PROMISING result would still need prospective validation
(disclosed vs RULES.md hidden-year rule).

## Per-year base vs cap (raw w*y; mean in bps, win = net>0 share)

| year | base n/mean/win/sum/worst/DD | cap n/mean/win/sum/worst/DD | removed n/mean/win |
|---|---|---|---|
| 2021 | 990/27.4/.705/2.388/-0.442/0.442 | 813/24.0/.688/1.769/-0.417/0.417 | 177/77.5/.808 |
| 2022 | 1045/2.7/.695/0.183/-0.727/1.142 | 855/0.3/.683/0.021/-0.580/1.017 | 190/14.6/.721 |
| 2023 | 1330/39.7/.773/3.810/-0.266/0.272 | 1103/38.9/.770/3.460/-0.220/0.238 | 227/26.5/.793 |
| 2024 | 989/41.1/.699/2.579/-0.216/0.216 | 835/35.0/.677/1.847/-0.267/0.267 | 154/83.1/.825 |
| 2025 | 1144/13.4/.656/0.712/-0.531/0.665 | 965/8.0/.636/0.348/-0.489/0.674 | 179/33.9/.793 |
| FULL | 5498/27.4/.705/9.671/-0.727/1.142 | 4571/23.9/.688/7.446/-0.580/1.017 | 927/44.6/.786 |

Cap/base sum: 74% / 12% / 91% / 72% / 49% (raw); renormalised side row
(base vs cap: 3.887/0.272/5.725/3.959/1.210 vs
2.672/0.030/4.922/2.692/0.557) — same 0/5 pattern, verdict does not hinge
on exposure normalisation. Removed rungs' w*y drag: 0.62/0.16/0.35/
0.73/0.36. Worst day improves in 4/5 years (all but 2024), but maxDD only
in 3/5 (2024: 0.216 -> 0.267; 2025: 0.665 -> 0.674).

## Decision (PROMISING = maxDD not worse in >=4/5 yrs AND sum >=97% of base in >=4/5)

| check | score | pass? |
|---|---|---|
| DD_cap <= DD_base | 3/5 (2021, 2022, 2023) | NO |
| S_cap >= 0.97 * S_base | 0/5 (best 91% in 2023) | NO |
| PROMISING | | NO |

## Notes

- The cancelled 4th/5th rungs are NOT the losers: they win 72-83% of the
  time with positive mean (+15 to +83 bps) in every year — deep rungs that
  catch the bottom of the same crash bar. Cutting them removes 9-28% of
  fills but 9-88% of the yearly sum (full-path raw 9.67 -> 7.45, -23%).
- Tails improve only modestly and inconsistently: worst day shallower in
  4/5 years, but yearly maxDD shallower in only 3/5 (worse in 2024-2025,
  the years whose DD is smallest/largest respectively), so the cap is
  neither a reliable DD cut nor a cheap one.
- Repro: `research/tournament/oc_rungcap/{PLAN.md,b1core.py,run_cap.py,
  results.json,fills_base.parquet}` + `tests/test_oc_rungcap.py`
  (8 tests pass); one process, peak RAM ~0.4 GB (float32 1m arrays).

## Verdict

VERDICT: NOT PROMISING — the per-coin 3-fill cap keeps >=97% of the base sum in 0/5 years and cuts maxDD in only 3/5 years, because the removed 4th/5th rungs are high-win-rate winners; the crash-bar clustering is rejected as a cut.
