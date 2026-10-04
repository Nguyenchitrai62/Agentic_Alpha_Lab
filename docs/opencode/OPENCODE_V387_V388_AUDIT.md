# v387-v388 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Versions in research/parallel/rounds/parallel-20260906-r2/ (docstrings = pre-registration), on the audited multi-phase BOT harness (v376 / v380).
v387 = rows R2_4P (shifts 0..3 h) / R2_8P (shifts 0, 0.5, ..., 3.5 h, 1/8 capital each) with half-hour agent tables
research/diagnostics/phase_agents_half/tables_half (check: build_half.py reproduces v376/tables_hidden at s = 0 and 1; 30 random half-hour rows'
state recomputed from raw 1m at the shifted bar open); sub-books summed on a 30-minute grid. v388 = rows R2_4P / R2S5_4P / R2S6_4P (engine
m_sleeve_sl 5 / 6 instead of 4; close5 stops, 8-sigma backstop unchanged). BOT fitness, folds k = 2, 3; neither transferred.
Part A (blind, before opening v387_result.json / v388_result.json / run logs / pkl caches): recompute every row, fold, transfer flag and final;
save replication.json FIRST. Part B: compare (monthly > 0.01 pp, DD > 0.05 pp, F > 0.001 = mismatch); COMPARISON.md with "## Verdict" PASS/FAIL
per version. At most 1-2 processes (another long job runs).
Write only under `research/parallel/rounds/parallel-20260906-r2/v387_v388_audit/` and `tests/test_v387_v388_audit.py`; relative paths without
quoting. Do not edit leader files.
