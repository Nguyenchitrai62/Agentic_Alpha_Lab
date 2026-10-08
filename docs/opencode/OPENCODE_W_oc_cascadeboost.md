# OpenCode task oc_cascadeboost - INCREASE the dip budget after a cascade bar (the opposite of oc_cascadedelay)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_cascadeboost/` and `tests/test_oc_cascadeboost.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) before any outcome. Engine via heavy_slot (RAM tight: one engine job at a time).

## Why and the contamination label
research/tournament/oc_cascadedelay: halving the dip budget for 3-7 days after a > 4 sigma 4h move lost decisively (dSum5y -2.0 / -2.9, timing
0.1 in 2024): post-cascade dips carry the sleeve's profit. The opposite rule is the natural hypothesis, BUT oc_cascadedelay's replica covered
all five years incl. the post-release year, so this idea was formed after seeing those years: select on dev4 ONLY; the post-release year
number is a LABELLED DIAGNOSTIC (not clean evidence); only prospective paper could confirm.

## Variants (exactly two; cascade bar definition and everything else EXACTLY as oc_cascadedelay's PLAN, multiplier inverted)
B3: dip budget x1.5 for 3 days after a cascade bar. B7: x1.5 for 7 days. The G2 dip gross cap (2.0) and every other G2 limit still bind.
## Evaluation
Replica + placebo gate first (dSum5y >= +0.273 and sum-half >= 4/5, as oc_cascadedelay), engine for passing variants: REF (G2, reproduce
5.41 / 16.91 / 16.82 first), B3, B7: dev4 per year / mean / WORST / DD, robust pick on dev4 ONLY, 5y, full-path DD (crash legs matter: report
the worst 1m-marked DD episode for each row), post-release year as a labelled diagnostic. Vietnamese 3-line verdict.
