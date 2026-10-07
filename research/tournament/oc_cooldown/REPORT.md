# oc_cooldown REPORT (2026-10-05; PLAN pre-registered before any outcome)

## Setup
Per-coin 24h dip cooldown after a stop-out (idea #11) on the actually-traded
BOT rung stream: `oc_ddanat17/rungs_s0.parquet` (R2B1D17BF s=0 engine replica),
majors x R2 depths {2.5,3.0,3.5,4.0} (v293 RUNGS; 304 depth-5.0 rungs excluded,
2 rows outside anchor years dropped) -> 5160 rungs, 157 rung_sl stop triggers,
246 rungs cooled (4.8%). Rule: bar open B of coin c cooled iff a rung_sl stop
s of c has B in (s, s+24h] (strictly causal; same-bar fills kept). P&L =
loss = weight*ret (engine-sized, fees/funding in engine); win = ret > 0;
daily sums by exit date, per-year curves from 0. Repro:
`research/tournament/oc_cooldown/{PLAN.md,run_cooldown.py,sens_iterative.py,
results.json}` + `tests/test_oc_cooldown.py` (7 pass). Parquet-only, no 1m.

## Per anchor year (bar_start in [anchor, anchor+365d))
| year | n rem/kept | sum base->cool (retain) | maxDD base->cool | worst-day base->cool | win kept/rem |
|---|---|---|---|---|---|
| 2021 | 66/845 | 0.4715->0.4554 (96.6%) | -0.0191->-0.0193 NO (-2.1e-4) | -0.0153->-0.0137 | .663/.712 |
| 2022 | 101/872 | 0.1274->0.2280 (178.9%) | -0.1172->-0.0285 YES (+8.9e-2) | -0.0670->-0.0158 | .675/.762 |
| 2023 | 52/1198 | 0.8068->0.7769 (96.3%) | -0.1578->-0.1556 YES (+2.3e-3) | -0.1141->-0.1141 | .759/.904 |
| 2024 | 7/936 | 0.6416->0.6399 (99.7%) | -0.02373->-0.02370 YES (+3.7e-5) | -0.0205->-0.0205 | .683/.429 |
| 2025 | 20/1063 | 0.2301->0.2158 (93.8%) | -0.00244->-0.00243 YES (+1.1e-5) | -0.0024->-0.0024 | .640/.900 |
| FULL | 246/4914 | 2.2773->2.3159 | -0.1190->-0.1158 | -0.0981->-0.1063 | .687/.780 |

## Decision (PROMISING = maxDD improves in >=4/5 AND sum falls <10% in >=4/5)
maxDD improves 4/5 (all but 2021); sum retained 5/5 -> PROMISING by the
pre-registered rule.

## Notes (post-hoc, labelled)
- The effect is concentrated in 2022 (FTX cascade: DD cut 4x, sum +0.10);
  2023 is small (+2.3e-3), 2024/2025 deltas are dust (4e-5/1e-5, count only by
  the letter of the tolerance-0 rule), and 2021 DD worsens slightly.
- Removed rungs: 178 TPs (+0.223 gains given up), 46 timeouts (-0.060), 22 stops
  (-0.202); net removed -0.039. Removed win rate (78%) EXCEEDS kept (69%):
  the rule mostly eats winners and pays only via dodging rare deep stops.
- Full-period worst day is marginally WORSE with cooldown (-0.106 vs -0.098;
  a TP-heavy day thinned by the filter; per-year worst days never worsen).
- Sensitivity `sens_iterative.py` (self-consistent triggers: stops of cooled
  rungs cannot refire; 22/157 stops sat on cooled rungs, 17 rungs cooled only
  by such phantoms): verdict unchanged (4/5 + 5/5; 2022 DD -0.117->-0.037).
- Double-dip caveat: the idea was motivated by oc_ddanat17 anatomy on this
  SAME rung stream; all five years are research data. A PROMISING tag here is
  a consistency check, not independent evidence — needs prospective validation
  before real money.

## Verdict
VERDICT: PROMISING by the pre-registered rule (4/5 yearly maxDD improves, 5/5 sums retained) — but the DD cut is essentially the 2022 FTX cascade plus dust elsewhere, so treat as a cascade fuse needing prospective validation, not a return upgrade.
