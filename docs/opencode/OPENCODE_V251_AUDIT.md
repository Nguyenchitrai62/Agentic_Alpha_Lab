# v251 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v251_audit/` and `tests/test_v251_audit.py`. Use relative paths without
quoting. Do NOT open v251/v251_result.json or its logs until part A is saved (`replication.json`); read `v251/v251_strategy_vol_target.py`
and the `strat_vt` hook in `engine_user/engine_user.py`.
A: confirm strat_vt None reproduces v247 B18 (dev4 5.777, DD 19.65). Re-implement the hook independently: at bar i (live, i >= 2, j = i-2)
V_i = std of the 4h log changes of the equity path over the last 30 days up to j, annualised with sqrt(6 * 365); keep every V; after 90
live days the DD governor g[i] is multiplied by clip((median of all EARLIER V / V_i) ** power, lo, hi). Check that the multiplier uses only
equity up to bar i-2 (no same-bar or future equity). Run V1 (0.5, 1.5), V2 (0.7, 1.3), V3 (0.5, 1.0). Report dev4, worst first-four
monthly, gate DD; robust selection; most recent year only for the selected row. Save `replication.json`. B: compare with the result JSON
(return > 0.01pp/month, DD > 0.05pp). COMPARISON.md with a "## Verdict" PASS/FAIL, explicitly checking feature timing, fit windows (none
fitted: expanding median) and fill timing. Do not edit leader files.
