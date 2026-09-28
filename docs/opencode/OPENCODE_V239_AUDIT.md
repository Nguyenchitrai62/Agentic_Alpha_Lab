# v239 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v239_audit/` and `tests/test_v239_audit.py`. Use relative paths without
quoting. Do NOT open v239/v239_result.json or its logs until part A is saved (`replication.json`); read `v239/v239_bagged_members.py`.
A: check that the BagHGB patch replaces only the v92 / v94 / v103 return models (the v129 vol models unchanged) and that the member
features / targets / anchors / embargo equal those of the v236 W2 members; verify at least one anchor of member_A_bag and member_B_bag
(artifacts/research/engine_real/) against rebuilds; run the v218 D2 trade mode on v236_W2 (must be 5.774), G1, G2; report dev4, worst
first-four monthly, gate DD; robust selection; most recent year only for the selected row. Save `replication.json`. B: compare with the
result JSON (return > 0.01pp/month, DD > 0.05pp). COMPARISON.md with a "## Verdict" PASS/FAIL, explicitly checking feature timing, label
windows, fit windows and fill timing. Do not edit leader files.
