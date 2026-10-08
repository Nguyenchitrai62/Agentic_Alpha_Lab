# OpenCode task oc_b7c2 - do the cascade boost B7 and the Chronos tilt C2 stack on the BOT?
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_b7c2/` and `tests/test_oc_b7c2.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) before any outcome. Engine via heavy_slot (RAM tight: one engine job at a time).
LABEL: both components were already scored on the post-release year (B7 also contaminated, see oc_cascadeboost) -> post-release numbers are
labelled diagnostics; selection on dev4 only.

## Why
B7 (research/tournament/oc_cascadeboost: dip budget x1.5 for 7 days after a > 4 sigma 4h move) acts on WHEN to add dip capital; C2
(research/tournament/oc_chronos: rung size x1.25 / x0.75 by Chronos downside quantile) acts on WHICH rungs get more. Different mechanisms.
## Variants (exactly two)
B7C2: both multipliers applied (product; the dip gross cap 2.0 and every G2 limit still bind). B7C2_cap: product clipped to <= 1.5.
## Report
Rows REF, B7 (copy), C2 (copy), B7C2, B7C2_cap: dev4 per year / mean / WORST / DD, robust pick on dev4 ONLY among REF / B7 / B7C2 / B7C2_cap,
5y, full-path DD, worst 1m-marked episode, post-release year (labelled diagnostic), and the same rows on Bybit prices (S5, harness of
research/tournament/oc_c2bybit) for REF / B7 / the dev4 pick. Vietnamese 3-line verdict.
