# Rolling (clock-free) dip anchor vs the 4h-open anchor - dev-only event study (2026-10-05)

Script: rolling_anchor_dips.py (docstring = fixed rules). Dip-only, equal notional per fill, no book / agents / budget, minutes < 2025-09-24.
Sum of net returns per fill (units of notional), k = 3 sigma_4h:

| rule | 2021 | 2022 | 2023 | 2024 | pre (2020-10..2021-09) |
|---|---|---|---|---|---|
| anchored phase 0 (deployed grid) | 0.98 | 0.55 | 1.45 | 1.32 | 2.91 |
| anchored 4-phase mix (1/4 each) | 0.44 | 0.46 | 0.67 | 1.34 | 3.59 |
| rolling open (price 240 min ago) | -0.39 | -0.28 | 0.46 | 1.33 | 4.40 |
| rolling max (4h running high) | -1.24 | -1.08 | 0.12 | 1.65 | 5.07 |

Rolling-anchor DD 1.0-2.1 vs 0.2-0.4 anchored (2021-2023). k = 4 the same picture.
Reading: a clock-free anchor fills during sustained declines (a 4h drop is not a flush), loses in 2021-2022 -> CLOSED. The 4h-open anchor
with bids from minute 16 and the bar-end time exit is a real part of the edge, not only an artefact. Phase 0 is again best in dev
(2021 0.98 vs 0.16-0.42) and worst pre-research (2.91 vs 2.67-5.00) -> phase luck confirmed; the dip-only edge in 2021-2023 is modest
(4-phase Sharpe 1.0-1.5 per year at equal notional; 2024 and the pre period are much stronger).

Audit 2026-10-05 (OpenCode blind, research/diagnostics/diag_20261005_audit/COMPARISON.md): PASS, 0 mismatches, look-ahead PASS.
