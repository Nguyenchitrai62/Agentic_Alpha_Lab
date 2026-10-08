# OpenCode task oc_d1bybit - does the downside-share dip tilt D1 keep its dev edge under frictions and on BYBIT prices (S5)?
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_d1bybit/` and `tests/test_oc_d1bybit.py`.
Print progress every 10 minutes. Engine via heavy_slot (RAM tight: one engine job at a time). Long jobs: nohup + log under tmp/.

## Context
research/tournament/oc_downshare: D1 (dip rung size x1.25 / x0.75 on the outer quintiles of the trailing-6d downside-RV share, per-anchor fits
fits.json, no pretraining anywhere) is the dev4 robust pick (mean 5.776 / WORST 2.921 / DD 16.09 vs G2 5.601 / 2.588 / 16.91) but the
post-release year was -0.057 vs G2. research/tournament/oc_c2bybit did exactly this friction check for C2 - copy its harness and swap the
multipliers (D1 frozen from oc_downshare).

## Rows
Reproduce oc_downshare's REF and D1 numbers to the digit first. Then REF and D1 under: base, S1 cost stress, S2 latency 15, S3 latency 30,
S4 stop slip, S5 Bybit prices (exactly as oc_c2bybit). Report dev4, the post-release year (diagnostic re-score under frictions; labelled)
and the 5y path with full-path DD, with C2's numbers from oc_c2bybit side by side. Also the Spearman correlation of the D1 and C2 multipliers
per year (are they different signals?). Verdict (Vietnamese 3 lines): D1 - REF > 0 under every friction and on Bybit prices?
