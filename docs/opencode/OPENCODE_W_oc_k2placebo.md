# OpenCode task oc_k2placebo - is the Kronos K2 dip tilt's post-release gain (+0.15 %/month) distinguishable from random timing?
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_k2placebo/` and `tests/test_oc_k2placebo.py`.
Print progress at least every 10 minutes. DIAGNOSTIC ONLY: the post-release year 2025-09-24 .. 2026-09-23 was already scored once by
oc_kronoshidden; nothing here selects or changes anything.

## Inputs
research/tournament/oc_kronoshidden: kronos_features_4shift.parquet (sym, shift, T, low1, ...), fits.json (per-anchor direction, q20, q80 of
risk = -low1), REPORT.md (K2 = x1.25 favourable outer quintile / x0.75 unfavourable / x1 else; anchor-2025 fit for the post-release year).
Dip replica: research/tournament/oc_placebo_dip/compute_placebo_dip.py (D0 rung outcomes, B1 sizes, 4 phases; reproduce base 7.718 first).

## Test
1. In the replica (w*y units, 4-phase mean), compute for each year (dev years 2021..2024 AND the post-release year): base sum, K2 sum (rung
   weight x K2 multiplier of its (sym, shift = phase, T)), and the exposure-normalised K2 sum (divide by that year's mean realised multiplier).
2. Timing placebo: 1000 random permutations of the K2 multipliers across the (sym, shift, T) bars WITHIN each year (keeps the multiplier
   distribution and exposure; destroys timing) -> distribution of the normalised sum; report the actual's percentile per year, especially the
   post-release year (the only clean one; dev years are inside Kronos' pretraining).
3. A second placebo preserving persistence: permute in blocks of 42 consecutive bars per (sym, shift).
Report the table and a plain statement: is the post-release gain significant at 5 % (percentile >= 95)? Vietnamese 3-line verdict.
