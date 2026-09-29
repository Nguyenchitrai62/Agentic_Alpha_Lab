# v279 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v279_audit/` and `tests/test_v279_audit.py`. Use relative paths without
quoting. Do NOT open v279/v279_result.json or its logs until part A is saved (`replication.json`). Read `v279/v279_fill_speed_sizing.py` and
the engine hook sleeve_fill_size (multiplier decided at the fill, applied before the risk-budget check). Check: the speed uses 1m closes up to
minute f-1 only (truncation probes), the terciles per anchor use only fills whose bar ended before anchor - 7 days, 2021 uses 1.0; the
recording run reproduces v269 M1 (6.026). Run F1 / F2; robust selection; most recent year only for the selected row. Save
`replication.json`. B: compare with the result JSON. COMPARISON.md with a "## Verdict" PASS/FAIL. Do not edit leader files.
