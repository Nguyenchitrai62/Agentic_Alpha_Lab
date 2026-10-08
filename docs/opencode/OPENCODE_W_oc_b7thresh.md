# OpenCode task oc_b7thresh - robustness surface of the cascade boost B7 (trigger threshold x window length) - REPORT ONLY, B7 stays 4 sigma / 7 days
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_b7thresh/` and `tests/test_oc_b7thresh.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) before any outcome. Heavy work via scripts/heavy_slot.py (RAM tight: one job at a time).
Long jobs: nohup + log under tmp/; never inspect /proc or folders outside the workspace.

## Why
B7 (research/tournament/oc_cascadeboost: x1.5 for 7 days after a > 4 sigma 4h move) is the biggest gain found, but a knife-edge optimum would
be a red flag. This is a robustness check, NOT a selection: nothing here changes B7.
## Grid (fixed)
trigger threshold k in {3.5, 4.0, 4.5} sigma x window W in {3, 5, 7, 10} days, multiplier 1.5, cascade definition otherwise exactly
oc_cascadedelay. Evaluate on (a) the clean pre-sample replica 2017-2020 (research/tournament/oc_cboostpre / oc_presampletilt ledger) and
(b) the 2021-2026 replica (oc_cascadeboost ledger, contaminated, labelled): per cell the normalised gain vs no boost per year, timing pct,
boosted stop rate. Engine only for the 4 corner cells (3.5/3, 3.5/10, 4.5/3, 4.5/10) on dev4 + 5y + full-path DD.
## Report
Heat tables per evaluation set; is the 4.0 / 7 cell in a broad plateau or an isolated peak? Vietnamese 3-line verdict.
