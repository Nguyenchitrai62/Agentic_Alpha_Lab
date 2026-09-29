# v277 + v278 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v277_v278_audit/` and `tests/test_v277_v278_audit.py`. Use relative paths
without quoting. Do NOT open v277/v278 result JSONs or logs until part A is saved (`replication.json`). Read `v277/v277_align_close4.py`
(aligned dip sizing (1.75, 0.25) / (1.25, 0.75) on v269 M1, reference 6.026) and `v278/v278_subaccount_blend.py` (50/50 mixes of full
engine runs rebalanced every bar; the mix's intrabar minimum = sum of the components' minima; metrics through the engine's summarize()).
Check that the mix never uses a component's bar return before that bar ends. Report dev4, worst first-four monthly, gate DD; robust
selection; most recent year only for each selected row. Save `replication.json`. B: compare with both result JSONs. COMPARISON.md with a
"## Verdict" PASS/FAIL. Do not edit leader files.
