# OpenCode task oc_b7c2pre - B7 x C2 on the clean pre-sample years 2017-2020
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_b7c2pre/` and `tests/test_oc_b7c2pre.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) before any outcome. Heavy work via scripts/heavy_slot.py (RAM tight: one job at a time).
Long jobs: nohup + log under tmp/; never inspect /proc or folders outside the workspace.

## Method
research/tournament/oc_cboostpre (B7 on the pre-sample replica) and oc_presampletilt (C2 on the pre-sample with the frozen anchor-2021 fit) already
built every piece. Combine them exactly as research/tournament/oc_b7c2 does (product of the B7 and C2 multipliers; and the product capped at
1.5): per pre-sample year n fills, normalised gain vs no tilt and vs B7 alone and vs C2 alone, timing pct, boosted stop rate, the COVID leg
separately. Verdict (Vietnamese 3 lines): does the stack help on unseen years and does C2 reduce B7's crash-leg damage there?
