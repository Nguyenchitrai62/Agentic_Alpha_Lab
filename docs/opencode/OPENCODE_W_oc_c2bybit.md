# OpenCode task oc_c2bybit - does the Chronos C2 dip tilt keep its edge under frictions and on BYBIT prices (S5)?
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_c2bybit/` and `tests/test_oc_c2bybit.py`.
Print progress every 10 minutes. Engine runs via heavy_slot (RAM is tight on this host: one engine job at a time).

## Context
research/tournament/oc_chronos (C2 = dip rung size x1.25 / x0.75 on the outer quintiles of risk = -ch_q10, per-anchor fits fits.json; engine
mechanism run_engine.py / tilt_rule.py) is the dev4 robust pick. research/tournament/oc_k2bybit did exactly this check for K2 - copy its harness
(compute_k2bybit_engine.py, analyze_k2bybit.py) and swap the multipliers.

## Rows
Reproduce oc_chronos's REF and C2 numbers to the digit first. Then REF and C2 under: base, S1 cost stress, S2 latency 15, S3 latency 30,
S4 stop slip, S5 Bybit prices (exactly as oc_k2bybit). Report dev4, the post-release year (diagnostic re-score under frictions; labelled) and
the 5y path with full-path DD, plus K2's numbers from oc_k2bybit side by side. Verdict (Vietnamese 3 lines): C2 - REF > 0 under every
friction and on Bybit prices, full-path DD <= 20?
