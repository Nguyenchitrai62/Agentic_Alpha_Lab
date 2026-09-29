# v273 + v274 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v273_v274_audit/` and `tests/test_v273_v274_audit.py`. Use relative paths
without quoting. Do NOT open v273/v274 result JSONs or logs until part A is saved (`replication.json`). Read `v273/v273_target_on_close4.py`
and `v274/v274_close_stop_tp.py` (both on v269 M1: dip stops on 5m closes at 4 sigma + 8-sigma native backstop, budget 0.18).
A: confirm the reference v269 M1 (dev4 6.026, DD 18.27); v273 book vol target 0.27 / 0.29 (engine argument target); v274 dip TP m_sleeve_tp
1.25 / 1.5. Report dev4, worst first-four monthly, gate DD, rung TP / SL counts; robust selection; most recent year only for each selected
row. Save `replication.json`. B: compare with both result JSONs. COMPARISON.md with a "## Verdict" PASS/FAIL, explicitly checking fill /
exit timing. Both were run after their pre-registration commits (c223d5a, the v274 commit) but before the registry rotation - confirm the
committed scripts equal the run scripts. Do not edit leader files.
