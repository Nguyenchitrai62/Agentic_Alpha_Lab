# oc_btclead REPORT (2026-10-06; PLAN pre-registered before any outcome)

## Setup
BASE = B1 size-only replica (static bid at lv, size x 1/(1+n_fill)) vs
BTC-LEAD (alts only: while BTC is >= 1.5 of its own 4h sigma below its bar
open at minute m-1 AND the alt close is still above its rung, the resting bid
is amended to lv x (1 - 0.5 x beta_clip x s_BTC x sg_alt), back to lv
otherwise, never above lv; beta = walk-forward 30-day (180-bar) 4h-open-return
OLS beta vs BTC, min_periods 60, clipped [0,3], NaN fallback 1.0; BTC's own
rungs identical to BASE; size kept as B1; fill on strict low < level in force;
exits = D0 replica from the ACTUAL fill px; maker 0.0002 / taker 0.00055;
longs pay 0.0001 on settling timeouts). Majors x R2 depths (2.5/3/3.5/4/5),
bars with open in [2021-09-24, 2026-09-24) (5 anchor years); n = other majors
with C(T+m-1) <= O(T) x (1 - 2.5 sg(T)), v399-exact. Weights w = 1/(1+n_fill),
renormalised per year-arm to mean 1 (primary); daily sums by exit date UTC;
maxDD of cumulative daily-sum path from 0. BASE fills 5498 = oc_b1deeper B1 to
the tick per coin (1067/1126/952/1179/1174) with matching sums — replica
validated. LEAD fills 4998 (-9%: BTC 1067 unchanged + alts 980/836/1073/1042).
Beta fallback-1.0 bars: ETH 61, SOL 327, BNB 61, XRP 61. Ledger checksum
d144c8c3bd38611c. All 5 years are research data: a PROMISING result would still
need prospective validation (disclosed vs RULES.md hidden-year rule).

## Per-year BASE vs BTC-LEAD (renormalised w; mean in bps, win = net>0 share)
| year | BASE n/mean/win/sum/worst/DD | LEAD n/mean/win/sum/worst/DD |
|---|---|---|
| 2021 | 990/38.1/.688/3.887/-0.720/0.720 | 902/24.4/.652/2.324/-0.765/0.765 |
| 2022 | 1045/3.8/.695/0.272/-1.082/1.699 | 948/-6.1/.671/-0.366/-1.012/1.780 |
| 2023 | 1330/39.7/.773/5.725/-0.400/0.409 | 1202/33.2/.757/4.559/-0.274/0.274 |
| 2024 | 989/41.1/.699/3.959/-0.332/0.332 | 913/31.5/.671/3.242/-0.343/0.343 |
| 2025 | 1144/13.4/.656/1.210/-0.903/1.130 | 1033/2.5/.621/0.420/-0.847/1.263 |
| FULL | 5498/27.4/.705/15.138/-1.138/1.787 | 4998/17.5/.678/10.333/-1.096/1.928 |

## Decision (PROMISING = sum not lower in >=4/5 yrs AND maxDD not worse in >=4/5)
| check | score | pass? |
|---|---|---|
| S_lead >= S_base | 0/5 (gaps -1.56/-0.64/-1.17/-0.72/-0.79) | NO |
| DD_lead <= DD_base | 1/5 (only 2023, 0.274 vs 0.409) | NO |
| LOYO sum gap >= 0 (supplementary) | 0/5 | NO |
| PROMISING | | NO |

## Notes
- BTC-lead deepening lowers per-fill quality in every year (mean -14/-10/-7/
  -10/-11 bps; win rate -2 to -4 pp) and still loses the yearly sum in all 5
  years; full-path DD is worse (1.79 -> 1.93). Unlike oc_b1deeper's
  correlation-deepening (which cut tails 5/5), gating on the BTC leg alone
  misses ~9% of fills — disproportionately winners — without a tail payoff.
- Raw (non-renormalised) sums show the same 0/5 pattern (BASE vs LEAD:
  2.39/0.18/3.81/2.58/0.71 vs 1.31/-0.24/2.89/2.04/0.22), so the verdict does
  not hinge on renormalisation.
- Repro: `research/tournament/oc_btclead/{PLAN.md,btclead.py,run.py,
  results.json,fills.parquet}` + `tests/test_oc_btclead.py` (11 tests pass);
  one process, peak RAM ~0.4 GB (float32 1m arrays).

## Verdict
VERDICT: NOT PROMISING — BTC-lead alt deepening loses the yearly sum in 0/5 years and cuts drawdown in only 1/5 years, so the BTC-lead dip price is rejected and B1 size-only stands.
