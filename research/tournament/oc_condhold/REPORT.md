# oc_condhold REPORT (2026-10-06; PLAN pre-registered before any outcome)

## Setup
BASE = oc_b1deeper B1 / oc_holdext BASE replica (static bid at lv=O*(1-k*sg),
strict low<lv fill at lv, w=1/(1+n_fill); D0 exits from fill px: TP px*(1+sg),
close5 stop 4sg, backstop 8sg, timeout at next-bar open o2; maker 0.0002 /
taker 0.00055; longs pay 0.0001 on settling timeouts). CONDITIONAL = identical
entry/weights/exits, except a rung with BASE how=="time" AND IN PROFIT at the
mid open (base_ret > 0 strictly, i.e. o2 above fill + round-trip fees + any
mid-settlement fund; 1e-12 dust = flat; causal, o2 only) keeps the SAME
sl/bl/tp into minutes 240..479 with the same stop-first priority and clock,
time-exiting at o3=T+480; every extended exit pays the mid fund if settling,
o3 timeouts additionally the final fund (oc_holdext leg exact). Gate-FALSE
timeouts exit at o2 as today. Majors x R2 depths (2.5/3/3.5/4/5), bars open in
[2021-09-24, 2026-09-24) (5 anchor years, keyed by entry T); paired keep (both
nets finite) -> 5498 rungs (BTC 1067, ETH 1126, SOL 952, BNB 1179, XRP 1174 —
tick-identical to oc_holdext/oc_b1deeper B1 counts, means and win rates;
replica validated). 2253 BASE timeouts (41.0%), of which 803 (35.6%) passed
the profit gate and ran the extended leg; residual COND timeouts 31.5%.
Daily sums by each arm's own exit date (w*y); maxDD of cumulative daily-sum
path from 0. Ledger checksum 9a7e259dc075c86e. All 5 years are research data:
a PROMISING result would still need prospective validation (disclosed vs
RULES.md hidden-year rule).

## Per-year BASE vs CONDITIONAL (paired; mean in fraction, win = net>0 share)
| year | BASE n/mean/win/sum/timeout/worst/DD/eff | COND n/mean/win/sum/timeout/worst/DD/eff |
|---|---|---|
| 2021 | 990/.00381/.688/2.388/.445/-0.442/0.442/5.40 | 990/.00418/.657/2.653/.335/-0.443/0.443/5.99 |
| 2022 | 1045/.00038/.695/0.183/.396/-0.727/1.142/0.16 | 1045/.00062/.661/0.321/.297/-0.725/1.183/0.27 |
| 2023 | 1330/.00397/.773/3.810/.328/-0.266/0.272/14.01 | 1330/.00383/.738/3.674/.245/-0.269/0.269/13.65 |
| 2024 | 989/.00411/.699/2.579/.433/-0.216/0.216/11.92 | 989/.00389/.656/2.300/.335/-0.230/0.351/6.54 |
| 2025 | 1144/.00134/.656/0.712/.467/-0.531/0.665/1.07 | 1144/.00147/.623/0.717/.379/-0.537/0.734/0.98 |
| FULL | 5498/.00274/.705/9.671/.410/-0.727/1.142/8.47 | 5498/.00280/.670/9.665/.315/-0.725/1.183/8.17 |

## Gate (share of BASE timeouts extended one more bar)
| year | base timeouts | gate TRUE | share |
|---|---|---|---|
| 2021 | 441 | 155 | 0.351 |
| 2022 | 414 | 159 | 0.384 |
| 2023 | 436 | 182 | 0.417 |
| 2024 | 428 | 143 | 0.334 |
| 2025 | 534 | 164 | 0.307 |
| FULL | 2253 | 803 | 0.356 |

## Decision (PROMISING = sum strictly higher in >=4/5 yrs AND maxDD not worse in >=4/5)
| check | score | pass? |
|---|---|---|
| S_cond > S_base | 3/5 (2021 +0.26, 2022 +0.14, 2025 +0.01; 2023 -0.14, 2024 -0.28) | NO |
| DD_cond <= DD_base | 1/5 (only 2023, 0.269 vs 0.272) | NO |
| LOO sum-diff sign (descriptive) | 2/5 | — |
| PROMISING | | NO |

## Notes
- The gate fires on about one third of timeouts (30-42% per year) and, unlike
  the unconditional hold, LOWERS the win rate (70.5% -> 67.0% full; lower in
  all 5 years): winners held an extra bar often give the profit back via the
  frozen stop/backstop or a second timeout, while losers are still cut at o2.
- Sum improves in 2021/2022/2025 but the extra bar adds tail almost
  everywhere: DD worse in 4/5 years (only 2023 marginally better, -0.003);
  full-path sum is flat (9.671 -> 9.665, -0.01) at worse DD (1.142 -> 1.183)
  and worse efficiency (8.47 -> 8.17). 2024 is the worst leg (-0.28 sum,
  DD 0.22 -> 0.35).
- Failure mode differs from oc_holdext (which raised win to 0.77 but lost sum
  4/5): conditioning on profit recovers some sum (3/5 vs 1/5) but sacrifices
  win rate and still carries the second-bar tail.
- Repro: `research/tournament/oc_condhold/{PLAN.md,condhold.py,run.py,
  results.json,fills.parquet}` + `tests/test_oc_condhold.py` (15 tests pass);
  one process, peak RAM ~0.5 GB (float32 1m arrays).

## Verdict
VERDICT: NOT PROMISING — the in-profit-only hold beats the next-open timeout in only 3/5 years on sum and 1/5 on drawdown, so timeouts stay exited at the next 4h open.
