# OpenCode task oc_d1c2 - do the two strongest dip tilts (D1 downside share, C2 Chronos) combine? (pre-registered ensembles)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_d1c2/` and `tests/test_oc_d1c2.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) before any outcome. Engine via heavy_slot (RAM tight: one engine job at a time).

## Why
oc_downshare D1 lifts the worst dev year (2021: 2.921 vs 2.588) but not the post-release year; oc_chronos C2 lifts the post-release year
(+0.106) and the 2021 year less (2.711). If the two signals are different, an ensemble may keep both. LABEL: both components were already
scored once on the post-release year, so the ensemble's post-release number is a labelled diagnostic, not clean evidence (prospective paper
decides).
## Variants (exactly two; multipliers frozen from research/tournament/oc_downshare (D1) and oc_chronos (C2))
AVG: rung multiplier = mean of the D1 and C2 multipliers. AGREE: 1.25 only if both are 1.25, 0.75 only if both are 0.75, else 1.0.
## Report
Spearman correlation and the agreement table of the two multipliers per year; engine rows REF, D1, C2 (copied), AVG, AGREE: dev4 per year,
mean, WORST, DD; robust pick on dev4 ONLY among REF / AVG / AGREE; post-release year (labelled diagnostic), 5y, full-path DD; timing placebo per
year. Vietnamese 3-line verdict.
