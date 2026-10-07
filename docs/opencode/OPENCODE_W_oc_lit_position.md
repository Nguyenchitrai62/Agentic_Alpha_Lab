# OpenCode task oc_lit_position - literature book gates: H6 (open-interest level throttle; its dip leg O2 must first pass the dip replica + placebo gate of research/tournament/oc_placebo_dip before any engine run) and H8 (MVRV-z timing gate; skip anchor years without history, disclosed)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md and docs/opencode/OPENCODE_W_TEMPLATE_BOOKGATE_20261007.md first (the engine protocol,
controls and selection rule are there). Write ONLY `research/tournament/oc_lit_position/` and `tests/test_oc_lit_position.py`.
Implement exactly the variants of H6 (open-interest level throttle; its dip leg O2 must first pass the dip replica + placebo gate of research/tournament/oc_placebo_dip before any engine run) and H8 (MVRV-z timing gate; skip anchor years without history, disclosed) as written in docs/opencode/IDEAS4_20261007.md section C (data sources, windows, thresholds and
leakage notes listed there are binding; if a listed data source does not cover 2021-09-24 .. 2025-09-23, say so and skip that variant).
Write PLAN.md (variants, controls, fixed settings) BEFORE any engine run.
