# OpenCode task oc_k2bybit - does the Kronos K2 dip tilt keep its edge on BYBIT prices (S5) and under the other frictions?
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_k2bybit/` and `tests/test_oc_k2bybit.py`.
Print progress every 10 minutes. Engine runs via heavy_slot.

## Context
research/tournament/oc_kronoshidden (K2 = dip rung size x1.25 / x0.75 on the outer quintiles of -low1, per-anchor fits in fits.json; engine
mechanism copied from v414) and oc_k2placebo (post-release timing percentile 97.2). A paper runner with K2 runs now (paper_d17bfg2k2).
research/tournament/oc_amihudrobust showed a book tilt can vanish on Bybit prices (S5); check K2 the same way.

## Rows (reproduce oc_kronoshidden's REF and K2 numbers to the digit first; then the frictions exactly as robust_v421.py / oc_amihudrobust)
REF and K2 under: base, S1 cost stress, S2 latency 15, S3 latency 30, S4 stop slip, S5 Bybit prices. Report dev4 (upper bound - Kronos
pretraining), the post-release year (clean; it was already scored once by oc_kronoshidden for base - this re-scores it under frictions,
labelled diagnostic) and the 5y path with full-path DD. Verdict (Vietnamese 3 lines): K2 - REF > 0 under every friction and on Bybit prices,
with full-path DD <= 20?
