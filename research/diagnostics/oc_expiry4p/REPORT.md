# oc_expiry4p REPORT (2026-10-06): full-engine check of the 48h pre-expiry book halving on R2B1D17BFG2

POST-HOC LABELLED screen: the rule came from the vectorised screen in
`research/tournament/oc_expirybook` (idea #62); this is the full-engine check,
not a selection.

## Setup
Harness = verbatim copy of `v421_gross_cap.py` worker wiring
(`phase_offset_full` prep + `pipe_setup("v321", agents on)` + kd=1.7 corr-size +
bear-book filter + G=2.0 gross cap + `win_start=5`; gate fees maker 0.0002 /
taker 0.00055; adverse long funding 0.0001), 4 phases s=0..3, reset-metric
(`reset_metric.year_reset` per anchor year, `v388.mix` full-path DD).
Rule: book targets x0.5 (both sides, all 5 majors) for standard book rows with
T in [E-48h, E), E = last Friday of month 08:00 UTC (68 expiries 2021-01..2026-08,
12 bars each, copied from `compute_expirybook.py`), applied AFTER the bear
filter and BEFORE the shifted-clock ffill (same place v416 put its tilt).
Rows: R2B1D17BFG2 (base) vs R2B1D17BFG2_EXP (base + halving).
Resources: strictly sequential (no Pool), RAM gate 2 GB with one bounded 300 s
wait then proceed-with-warning (host sat at 1.4-1.7 GB at start; s1/s3 passed
the gate, s0/s2 logged the warning; each leg ~0.5 GB, all 8 legs succeeded).
Win rate = pooled all-trade (book episodes net>0 after fees + rung exits
ret>0) by exit time in (a0, a0+365d], 4 shifts combined; book episodes mirror
`v213.trade_stats` episode logic.

## Reproduction (gate)
Base reproduces v421 exactly: 5y 5.41 %/mo, max yearly DD 16.91, full-path DD
16.82 (run.log row R2B1D17BFG2). Per-shift final equities also bit-match run.log
(s0 55.993, s1 17.031, s2 26.262, s3 6.264). Proceeded to EXP comparison.

## Per anchor year (reset-metric %/month, DD; pooled all-trade win, n = nb+nr)

| year | base R / DD / win (n) | EXP R / DD / win (n) | gap R (EXP-base) |
|---|---|---|---|
| 2021-09-24 | 2.588 / 10.86 / 0.6129 (5001) | 2.247 / 12.68 / 0.6130 (5005) | -0.341 |
| 2022-09-24 | 3.282 / 16.91 / 0.6574 (4802) | 3.466 / 16.56 / 0.6564 (4820) | +0.184 |
| 2023-09-24 | 6.045 / 15.81 / 0.6956 (5979) | 6.670 / 16.03 / 0.6927 (6008) | +0.625 |
| 2024-09-24 | 10.677 / 8.27 / 0.6699 (5010) | 10.534 / 8.39 / 0.6709 (5047) | -0.143 |
| 2025-09-24 | 4.648 / 12.90 / 0.6267 (5783) | 4.769 / 14.30 / 0.6255 (5789) | +0.121 |

## Aggregates

| row | 5y mean | worst year | max yearly DD | full-path DD | dev4 (2021-24) | win_all 5y |
|---|---|---|---|---|---|---|
| base | 5.410 | 2.588 | 16.91 | 16.82 | 5.601 | 0.6533 |
| EXP | 5.498 | 2.247 | 16.56 | 16.53 | 5.681 | 0.6525 |
| EXP-base | +0.088 | -0.341 | -0.35 | -0.29 | +0.080 | -0.0008 |

No losing year on either leg. Win rate is flat (5y 0.6533 -> 0.6525; yearly
within +/-0.003). EXP lowers DD (max yearly -0.35pp, full-path -0.29pp) and
adds +0.09 %/mo on the 5y mean, but 2021 is -0.341 %/mo worse -- the same year
the vectorised screen flagged as the only year the expiry window was
profitable, so halving it hurts there too.

## Verdict
KEEP-CANDIDATE requires full-path DD lower (16.53 < 16.82 YES) AND 5y mean >=
5.30 (5.498 YES) AND no year worse by > 0.3 %/mo (2021 gap -0.341 NO). Fails the
third leg.

VERDICT: NO
