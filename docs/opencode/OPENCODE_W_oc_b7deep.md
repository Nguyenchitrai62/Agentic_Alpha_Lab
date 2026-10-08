# OpenCode task oc_b7deep - IDEAS7 #2: Deep-rung-only boost
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_b7deep/` and `tests/test_oc_b7deep.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) BEFORE any outcome. Engine / 1m work via scripts/heavy_slot.py (RAM tight: one job at a
time, one coin at a time, float32). Long jobs: nohup + log under tmp/; never inspect /proc or folders outside the workspace.

## Task
Implement idea #2 of docs/opencode/IDEAS7_20261008.md EXACTLY as written (rule, the two pre-registered variants and frozen constants, data,
leakage notes). Base = B7 of research/tournament/oc_cascadeboost (dip budget x1.5 for 7 days after a cascade bar, oc_cascadedelay definition).
CONTAMINATION PROTOCOL: anything derived from the cascade results is contaminated for 2021-2026. The PRIMARY, clean test is the pre-sample
replica 2017 .. 2020-09-23 (research/tournament/oc_presampletilt + oc_cboostpre machinery: cascade flags on pre-sample 4h closes, D0+B1
ledger): per year normalised gain vs B7 AND vs no boost, timing placebo pct, boosted-fill stop rate, and the COVID leg (2020p) separately.
SECONDARY: the 2021-2026 replica gate and, for variants that beat B7 on the pre-sample test, the 4-phase engine vs REF and B7 (dev4 robust pick,
5y, full-path DD; post-release year labelled diagnostic). Report which variant (if any) beats plain B7 on the clean pre-sample years without
losing the 2021-2024 gains. Vietnamese 3-line verdict.
