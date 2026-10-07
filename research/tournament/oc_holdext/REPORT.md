# oc_holdext REPORT (2026-10-06; PLAN pre-registered before any outcome)

## Setup
BASE = oc_b1deeper B1 replica (static bid at lv=O*(1-k*sg), strict low<lv fill
at lv, w=1/(1+n_fill); D0 exits from fill px: TP px*(1+sg), close5 stop 4sg,
backstop 8sg, timeout at next-bar open o2; maker 0.0002 / taker 0.00055; longs
pay 0.0001 on settling timeouts). EXTENDED = identical entry/weights; a rung
with BASE how=="time" (no TP/stop/backstop signal; a close5 signal at m=239
counts as stop) keeps the SAME sl/bl/tp into minutes 240..479 with the same
stop-first priority and clock, time-exiting at o3=T+480; every extended exit
pays the mid-open fund if settling, o3 timeouts additionally the final fund.
Majors x R2 depths (2.5/3/3.5/4/5), bars open in [2021-09-24, 2026-09-24)
(5 anchor years, keyed by entry T); paired keep (both nets finite) -> 5498
rungs (BTC 1067, ETH 1126, SOL 952, BNB 1179, XRP 1174 — tick-identical to
oc_b1deeper B1 counts/means/win rates, replica validated). 2253 BASE timeouts
(41.0%) ran the extended leg; residual EXT timeouts 21.7%. Daily sums by each
arm's own exit date (w*y); maxDD of cumulative daily-sum path from 0.
Ledger checksum 3bd0247213594305. All 5 years are research data: a PROMISING
result would still need prospective validation (disclosed vs RULES.md
hidden-year rule).

## Per-year BASE vs EXTENDED (paired; mean in fraction, win = net>0 share)
| year | BASE n/mean/win/sum/timeout/worst/DD/eff | EXT n/mean/win/sum/timeout/worst/DD/eff |
|---|---|---|
| 2021 | 990/.00381/.688/2.388/.445/-0.442/0.442/5.40 | 990/.00310/.748/2.305/.230/-0.566/0.566/4.07 |
| 2022 | 1045/.00038/.695/0.183/.396/-0.727/1.142/0.16 | 1045/.00064/.744/-0.180/.209/-1.185/1.612/-0.11 |
| 2023 | 1330/.00397/.773/3.810/.328/-0.266/0.272/14.01 | 1330/.00335/.817/3.678/.174/-0.356/0.356/10.33 |
| 2024 | 989/.00411/.699/2.579/.433/-0.216/0.216/11.92 | 989/.00604/.792/3.354/.217/-0.201/0.201/16.65 |
| 2025 | 1144/.00134/.656/0.712/.467/-0.531/0.665/1.07 | 1144/.00132/.740/0.423/.264/-0.652/0.932/0.45 |
| FULL | 5498/.00274/.705/9.671/.410/-0.727/1.142/8.47 | 5498/.00285/.770/9.579/.217/-1.185/1.612/5.94 |

## Decision (PROMISING = sum strictly higher in >=4/5 yrs AND maxDD not worse in >=4/5)
| check | score | pass? |
|---|---|---|
| S_ext > S_base | 1/5 (only 2024, +0.77; 2022 flips +0.18 -> -0.18) | NO |
| DD_ext <= DD_base | 1/5 (only 2024, 0.201 vs 0.216) | NO |
| LOO sum-diff sign (descriptive) | 3/5 | — |
| PROMISING | | NO |

## Notes
- The extra bar converts about half the timeouts into exits (timeout share
  41% -> 22%, win rate 70.5% -> 77.0%, mean +1.1 bps per fill) but the
  converted rungs add tail, not return: worst day worse in 4/5 years, full
  DD 1.14 -> 1.61, efficiency 8.47 -> 5.94; only 2024 gains on both legs.
- Failure concentrates in 2022 (-0.36 swing, worst day -0.73 -> -1.19) and
  2025 (-0.29); 2021/2023 lose small sums at worse DD despite higher win rates.
- Repro: `research/tournament/oc_holdext/{PLAN.md,holdext.py,run.py,
  results.json,fills.parquet}` + `tests/test_oc_holdext.py` (17 tests pass);
  one process, peak RAM ~0.5 GB (float32 1m arrays).

## Verdict
VERDICT: NOT PROMISING — the +4h hold beats the next-open timeout in only 1/5 years on sum and 1/5 on drawdown, so timeouts stay exited at the next 4h open.
