# oc_dipexit REPORT (2026-10-05; PLAN pre-registered before any outcome)

## Setup
Replica of v293 Asset/outcomes for LONG dip rungs (majors, rungs 2.5/3/3.5/4/5 sigma
below the 4h bar open; fills offsets 16..238 on strict low<level trade-through;
close5 stop 4sg on absolute clock, 8sg backstop, TP limit, timeout at next-bar open;
maker 0.0002 / taker 0.00055; longs pay 0.0001 on settling timeouts). Bars with open
in [2021-09-24, 2026-09-24) (5 anchor years); 1m read to 2026-09-24 00:00 (timeout
opens only). Paired rungs: kept only if D0+E1legs+E2+E3+E4 all finite -> 5498 rungs
(BTC 1067, ETH 1126, SOL 952, BNB 1179, XRP 1174; ledger checksum 0c4c198ab7ae1136).
Year = bar-open anchor year; daily sums by exit date (E1 halves booked to their own
exit days). Win = net > 0 strictly. All 5 years are research data: a PROMISING exit
still needs prospective validation (disclosed vs RULES.md hidden-year rule).

## Per-year rung stats (n paired; mean/win/sum over rungs; worst-day / max-DD of exit-day sums)
| year | D0 mean/win/sum/worst/DD | E1 split 0.5+1.5 | E2 TP1+120min | E3 breakeven trail | E4 TP=open cap2sg |
|---|---|---|---|---|---|
| 2021 | .00381/.688/3.777/-0.430/-0.454 (n990) | .00320/.690/3.164/-0.515/-0.515 | .00376/.691/3.723/-0.431/-0.439 | .00332/.591/3.286/-0.524/-0.524 | .00323/.594/3.194/-0.888/-1.007 |
| 2022 | .00038/.695/0.393/-1.924/-2.282 (n1045) | .00005/.704/0.048/-1.914/-2.347 | .00025/.687/0.258/-1.924/-2.258 | -.00016/.596/-0.172/-1.977/-2.276 | .00018/.631/0.186/-1.942/-2.621 |
| 2023 | .00397/.773/5.276/-0.495/-0.495 (n1330) | .00333/.788/4.425/-0.445/-0.445 | .00390/.765/5.187/-0.453/-0.481 | .00305/.664/4.060/-0.446/-0.446 | .00533/.718/7.090/-0.870/-0.870 |
| 2024 | .00411/.699/4.066/-0.507/-0.507 (n989) | .00367/.716/3.632/-0.503/-0.503 | .00396/.697/3.920/-0.369/-0.377 | .00344/.592/3.403/-0.375/-0.375 | .00489/.629/4.837/-0.634/-0.853 |
| 2025 | .00134/.656/1.538/-1.018/-1.269 (n1144) | .00103/.684/1.176/-1.217/-1.416 | .00138/.648/1.580/-1.018/-1.257 | .00077/.545/0.886/-0.802/-0.996 | .00128/.576/1.468/-1.943/-2.170 |
| FULL | .00274/.705/15.050/-1.924/-2.282 (n5498) | .00226/.720/12.445/-1.914/-2.347 | .00267/.700/14.668/-1.924/-2.258 | .00208/.600/11.462/-1.977/-2.276 | .00305/.634/16.775/-1.943/-2.621 |

## Decision (PROMISING = yearly sum >= D0 in >=4/5 yrs AND worst day not worse, per year)
| exit | years >= D0 | worst-day-not-worse (all 5 yrs) | verdict |
|---|---|---|---|
| E1 split TP | 0/5 | NO (worse 2021, 2025) | NOT PROMISING |
| E2 TP1 + 120min | 1/5 (only 2025) | NO (marginally worse 2021: -0.4312 vs -0.4300) | NOT PROMISING |
| E3 breakeven trail | 0/5 (2022 sum negative) | NO (worse 2021, 2022) | NOT PROMISING |
| E4 reversion cap2sg | 2/5 (2023, 2024) | NO (worse all 5 yrs) | NOT PROMISING |

## Notes
- Per-rung means (27bps D0, 31bps E4) are well above the ~4-8bps round-trip cost, but
  that is rung-conditional (fills are ~2% of rung-bars), not a strategy return.
- E4 has the highest total sum (+1.73 over D0 from 2023-24) yet loses on consistency
  and tail (worse worst-day in 4/5 years, full DD -2.62 vs -2.28).
- E3 cuts win rate 70%->60% and posts a negative 2022: moving the stop to breakeven
  after +0.5sg whipsaws the rung.
- Repro: `research/tournament/oc_dipexit/{PLAN.md,exits.py,run.py,results.json,
  rungs.parquet}` + `tests/test_oc_dipexit.py` (12 tests pass); one process, one coin
  at a time, float32 1m.

## Verdict
VERDICT: No alternative exit is PROMISING — all four fail the pre-registered rule, so the deployed TP 1-sigma exit stands.
