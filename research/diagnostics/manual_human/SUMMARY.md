# MANUAL with a real human schedule - honest 4-phase harness, dev years only (2026-10-05)

Script: manual_human.py (docstring = fixed rows). Phase_offset_full harness, agents ON (per-phase tables), standard books forward-filled,
dev 2021-09-24..2025-09-23. "human" = 15-minute reaction + the night bar (starting 20+s UTC = 03:00+s local) skipped: no new book order,
no new dip limit (resting orders, SL, TP stay). R = mean over the 4 phases of the dev4 geometric %/month; DD = mean over phases of the max
yearly 1m DD (worst phase in brackets); W = mean worst-year %/month. M5_base reproduces v377 (4.094) exactly.

| pipeline | base R / DD (max) / W | human R / DD (max) / W |
|---|---|---|
| M2 (v340, 1 bracket dip) | 3.60 / 22.8 (28.5) / 1.07 | 3.00 / 22.0 (25.2) / 0.61 |
| M3 (v342) | 4.18 / 23.7 (31.2) / 0.56 | 3.52 / 23.8 (31.5) / 0.29 |
| M4 (v362) | 4.26 / 23.5 (32.1) / 0.46 | 3.60 / 23.7 (32.5) / 0.15 |
| M5 (v367, deployed) | 4.09 / 24.4 (33.2) / 0.28 | 3.50 / 24.2 (33.9) / 0.00 |

Reading: a sleeping, 15-minute-late human loses ~0.6 %/month on every MANUAL pipeline; the honest MANUAL expectation is ~3.0-3.6 %/month
with single-clock DD 22-24 % (one phase reaches 32-34 % in 2022 through the second 4-sigma dip rung). No MANUAL pipeline meets the floor
(5 %/month, DD < 20) honestly. M3/M4/M5 are equivalent within noise; M2 has the best worst year. To hold DD < 20 a human should run a
MANUAL pipeline on ~80 % of the capital (expect ~2.8 %/month). Nothing was selected on this table.

Audit 2026-10-05 (OpenCode blind, research/diagnostics/diag_20261005_audit/COMPARISON.md): PASS, 0 mismatches, look-ahead PASS.
