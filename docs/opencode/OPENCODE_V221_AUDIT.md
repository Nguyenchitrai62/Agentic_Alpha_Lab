# v221 blind audit - exit hysteresis (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v221_audit/` and `tests/test_v221_audit.py`. Use relative paths
without quoting. Do NOT open v221/v221_result.json or v221 logs until part A is saved (`replication.json`); read the pre-registration
`v221/v221_grid_hysteresis.py`.
A: on your independent v218 D2 replication (G2 grid trader, sleeve budget 0.15, rung x1.75; dev4 5.261), replace the in-position exit
rule: with v = target along the position, v <= -0.05 -> tighten + limit close; v < C -> limit close (Y1 C 0.025, Y2 C 0.010, Y3 C 0.025
on an EMA with alpha 0.5 of v per coin, reset when flat); otherwise the G2 grid adjustments toward max(v, 0) with band max(0.03,
0.40*target) and a 6-bar cooldown. Report dev4, worst first-four monthly, gate DD, dev trades for v218_D2, Y1, Y2, Y3; robust
selection over Y1..Y3; most recent year only for the selected row. Check causality. Save `replication.json`.
B: compare with `v221/v221_result.json` (return > 0.01pp/month, DD > 0.05pp). COMPARISON.md with PASS/FAIL. Do not report the most
recent year of non-selected rows. Do not edit leader files.
