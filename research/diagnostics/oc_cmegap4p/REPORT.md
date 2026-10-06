# oc_cmegap4p REPORT (2026-10-06): full-engine check of the CME weekend-gap book tilt on R2B1D17BFG2

POST-HOC LABELLED screen: the rule came from the vectorised screen in
`research/tournament/oc_cmegap` (idea #69); this is the full-engine check,
not a selection.

## Setup
Harness = verbatim copy of `oc_expiry4p.py` worker wiring (itself `v421`
worker wiring: `phase_offset_full` prep + `pipe_setup("v321", agents on)` +
kd=1.7 corr-size + bear-book filter + G=2.0 gross cap + `win_start=5`; gate
fees maker 0.0002 / taker 0.00055; adverse long funding 0.0001), 4 phases
s=0..3, reset-metric (`reset_metric.year_reset` per anchor year, `v388.mix`
full-path DD).
Rule: CME weekend-gap proxy `gap = P(Sun reopen)/P(Fri close)-1` from Binance
BTCUSDT 1m closes at the assignment's DST times (winter Fri 21:00/Sun 22:00
UTC, summer Fri 20:00/Sun 21:00 UTC; season by Friday date in
[2nd-Sun-Mar, 1st-Sun-Nov)); fill = first 1m trade-through of `P_fri` after
the reopen (low <= for up-gaps, high >= for down-gaps) within 72 h. On
large-gap active rows (first 4h row after the reopen .. fill or +72h, fill
known strictly before T): book LONG x0.75 if gap > +2%, x1.25 if gap < -2%
(all 5 majors, on bear-filtered longs); shorts/flats/small-gaps unchanged.
Applied AFTER the bear filter and BEFORE the shifted-clock ffill (same place
oc_expiry4p put its halving).
Rows: R2B1D17BFG2 (base) vs R2B1D17BFG2_CME (base + tilt). 262 weekends
enumerated (2021-09-17..2026-09-23); 262/262 finite gaps; 58 large
(`|gap|>2%`: 28 up / 30 down); large-gap fill rate 0.50. Active standard-grid
rows 742/10950 per shift (up 383, down 359).
Resources: strictly sequential (no Pool), RAM gate 2 GB with one bounded 300 s
wait then proceed-with-warning (host sat at 1.3-2.3 GB; s0 passed the gate,
s1/s2/s3 logged the warning; each leg ~0.5 GB, all 8 legs succeeded).
Win rate = pooled all-trade (book episodes net>0 after fees + rung exits
ret>0) by exit time in (a0, a0+365d], 4 shifts combined; book episodes mirror
`v213.trade_stats` episode logic.

## Reproduction (gate)
Base reproduces v421 exactly: 5y 5.41 %/mo, max yearly DD 16.91, full-path DD
16.82 (run.log row R2B1D17BFG2). Per-shift final equities also bit-match
oc_expiry4p base (s0 55.993, s1 17.031, s2 26.262, s3 6.264). Proceeded to CME
comparison.

## Per anchor year (reset-metric %/month, DD; pooled all-trade win, n = nb+nr)

| year | base R / DD / win (n) | CME R / DD / win (n) | gap R (CME-base) |
|---|---|---|---|
| 2021-09-24 | 2.588 / 10.86 / 0.6129 (5001) | 2.679 / 10.87 / 0.6133 (5024) | +0.091 |
| 2022-09-24 | 3.282 / 16.91 / 0.6574 (4802) | 3.201 / 17.05 / 0.6571 (4792) | -0.081 |
| 2023-09-24 | 6.045 / 15.81 / 0.6956 (5979) | 5.629 / 16.00 / 0.6996 (6196) | -0.416 |
| 2024-09-24 | 10.677 / 8.27 / 0.6699 (5010) | 11.107 / 8.78 / 0.6694 (4994) | +0.430 |
| 2025-09-24 | 4.648 / 12.90 / 0.6267 (5783) | 4.714 / 12.90 / 0.6270 (5786) | +0.066 |

## Aggregates

| row | 5y mean | worst year | max yearly DD | full-path DD | dev4 (2021-24) | win_all 5y |
|---|---|---|---|---|---|---|
| base | 5.410 | 2.588 | 16.91 | 16.82 | 5.601 | 0.6533 |
| CME | 5.424 | 2.679 | 17.05 | 17.03 | 5.602 | 0.6545 |
| CME-base | +0.014 | +0.091 | +0.14 | +0.21 | +0.001 | +0.0012 |

No losing year on either leg. Win rate is flat (5y 0.6533 -> 0.6545; yearly
within +/-0.004). CME adds +0.01 %/mo on the 5y mean but raises DD (max yearly
+0.14pp, full-path +0.21pp); 2023 is -0.416 %/mo worse -- the same year the
vectorised screen flagged as the only year the tilt lost on affected rows.

## Verdict
KEEP-CANDIDATE requires full-path DD lower (17.03 < 16.82 NO) AND 5y mean >=
5.30 (5.424 YES) AND no year worse by > 0.3 %/mo (2023 gap -0.416 NO). Fails
the first and third legs.

VERDICT: NO
