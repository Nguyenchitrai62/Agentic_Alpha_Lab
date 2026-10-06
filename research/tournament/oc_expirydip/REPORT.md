# oc_expirydip REPORT (2026-10-06; PLAN pre-registered before any outcome)

## Setup
Idea #76 (IDEAS2 idea 9: expiry-day dip-add / pin-flush buyer). Exact
oc_dipexit D0 replica (TP 1.0sg, close5 stop 4sg, 8sg backstop, timeout at
next-bar open; maker 0.0002 / taker 0.00055; v293 settle funding) with
oc_b1deeper B1 sizes w = 1/(1+n_fill), majors x R2 depths 2.5..5.0, live
offsets 16..238 strict trade-through, bars open in [2021-09-24, 2026-09-24),
all four clock phases (4h grid from 2020-08-01 00:00 UTC + 0/1/2/3h).
RULE: on Deribit monthly-expiry bars (last Friday of month, bar open in
[00:00,12:00) UTC — phase0: 00/04/08 bars; phases 1-3: 3 bars in the same
window), ONE extra 5.0-sigma rung per coin at base B1 size with D0 exits
(level/size/fill identical to the base 5.0 rung, so a filled expiry 5.0 bar
holds double 5.0 exposure); all other bars unchanged. Year = bar-open anchor
year; daily sums by exit date UTC; DD of cumulative daily-sum path from 0.
All 5 years are research data: a PROMISING result would still need
prospective validation (disclosed vs RULES.md hidden-year rule).

## Replica fidelity (base, B1 w*y sums)
Phase-0 base fills/coin 1067/1126/952/1179/1174 and sums
2.388/0.183/3.810/2.579/0.712 = oc_dipexit/oc_placebo_dip to 1e-3.
Ledger n_base = 22312 (= placebo n), checksum b0ce3ab25de34383 (hashes w/y10
only; placebo hashed 3 TP legs). Base 5y 4-phase-mean sum = 7.718 = placebo
base exactly.

## Extra-rung fills per year (all phases pooled for win/net; mean over phases)
| year | extra n (mean/phase; per-phase) | win pooled | net pooled (w*y) | sum_mean (4-phase) |
|---|---|---|---|---|
| 2021 | 4.00 (5/5/3/3; n=16) | 0.8125 | +0.0400 | +0.0100 |
| 2022 | 1.00 (0/0/1/3; n=4) | 1.0000 | +0.0161 | +0.0040 |
| 2023 | 0.00 (0/0/0/0; n=0) | — | 0.0000 | 0.0000 |
| 2024 | 0.75 (1/2/0/0; n=3) | 1.0000 | +0.0080 | +0.0020 |
| 2025 | 0.25 (1/0/0/0; n=1) | 1.0000 | +0.0016 | +0.0004 |
| 5y | 24 fills total | 0.8750 | +0.0657 | dSum5y +0.0164 |

## Base vs rule per year (4-phase means: S sum, W worst day, DD maxDD, n mean fills)
| year | S_base -> S_rule | W_base -> W_rule | DD_base -> DD_rule | n_base -> n_rule |
|---|---|---|---|---|
| 2021 | 0.9113 -> 0.9213 | -0.7398 -> -0.7398 | 0.8560 -> 0.8507 | 1042.75 -> 1046.75 |
| 2022 | 0.8326 -> 0.8366 | -0.7258 -> -0.7258 | 0.9506 -> 0.9487 | 1014.75 -> 1015.75 |
| 2023 | 2.0998 -> 2.0998 | -0.7352 -> -0.7352 | 0.8000 -> 0.8000 | 1338.00 -> 1338.00 |
| 2024 | 3.1974 -> 3.1994 | -0.2737 -> -0.2737 | 0.3545 -> 0.3545 | 989.50 -> 990.25 |
| 2025 | 0.6772 -> 0.6776 | -0.5084 -> -0.5084 | 0.6073 -> 0.6073 | 1193.00 -> 1193.25 |
| 5y sum | 7.7183 -> 7.7347 | — | mean 0.7137 -> 0.7122 | — |
| full pooled | 30.8732 -> 30.9389 | — | 3.1266 -> 3.1106 | 22312 -> 22336 |

## Decision (PROMISING = sum>=base in >=4/5 AND DD not worse by >1pp in >=4/5 AND dSum5y >= +0.273)
| check | score | pass? |
|---|---|---|
| S_rule >= S_base | 5/5 (2023 equal, no extra fills) | YES |
| DD_rule <= DD_base + 0.01 | 5/5 | YES |
| dSum5y >= +0.273 (placebo pooled p95) | +0.0164 (6% of gate) | NO |
| PROMISING | | NO |

## Notes
- Per-fill quality of the extra rung looks good (21/24 wins) but the sample
  is tiny: 24 fills in 5 years x 4 phases x 5 coins (expiry 5-sigma flushes
  almost never print; 2023 had zero in any phase). The 5y delta +0.016 w*y
  units (~0.2% of base) is noise-scale vs the placebo p95 +0.273.
- The sum/DD legs pass trivially because the addition is microscopic, not
  because of a real edge — exactly why the placebo-calibrated magnitude
  gate exists.
- Repro: `research/tournament/oc_expirydip/{PLAN.md,expirydip.py,run.py,
  results.json}` + `tests/test_oc_expirydip.py` (14 tests pass); one
  process, majors 1m O/C float32 + one-coin H/L via heavy_slot.

## Verdict
VERDICT: NOT PROMISING — the expiry-day extra 5-sigma rung passes the consistency legs (5/5 sums, 5/5 DD) but its 5y sum delta (+0.016) is far below the placebo p95 gate (+0.273), so idea #76 is closed with no full-engine follow-up.
