# v280 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v280_audit/` and `tests/test_v280_audit.py`. Use relative paths without
quoting. Do NOT open v280/v280_result.json or its logs until part A is saved (`replication.json`). Read `v280/v280_monthly_flow_member.py`,
`v202/v202_quarterly_retrain.py` (the wrapper with monthly anchors 2021-09-24 + k months, each model predicting only its own month) and
`v240/v240_order_level_flow.py`. Check the monthly member's fit windows (per-target cutoffs and embargoes relative to each monthly anchor,
no prediction outside its month), that the cached `member_Am_O1_monthly.parquet` is replayable, rebuild at least two monthly anchors and
compare; confirm the reference reproduces v269 M1 (6.026) with the C4 rules; run V1 / V2; robust selection; most recent year only for the
selected row. Save `replication.json`. B: compare with the result JSON. COMPARISON.md with a "## Verdict" PASS/FAIL, explicitly checking
feature timing, label windows and fit windows. Do not edit leader files.
