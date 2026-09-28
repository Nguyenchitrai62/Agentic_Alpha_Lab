# v217 blind audit - evolution-strategy policy search (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v217_audit/` and `tests/test_v217_audit.py`. Use relative paths
without quoting. Do NOT open v217/v217_result.json or v217 logs until part A is saved (`replication.json`); read the pre-registration
`v217/v217_policy_search.py`.
A (leakage first): verify that the objective for anchor j reads only the yearly results of anchors 0..j-1 (full simulated years that
end before anchor j), that nothing of year j or later can influence theta_j (the simulation of later years is computed but not read),
that year 0 uses theta0 and that the final evaluation switches theta by the anchor year of each decision (params_at + policy). Verify
theta0 everywhere reproduces v216 G2 (dev4 4.836). Re-run the deterministic search (seeds 217+j) or an equivalent independent
driver and report per anchor the best J and theta, then dev4, worst first-four monthly, gate DD for grid_G2, ES1_robust, ES2_shrunk,
ES3_worst; robust selection over ES1..ES3; most recent year only for the selected row. Save `replication.json`.
B: compare with `v217/v217_result.json` (return > 0.01pp/month, DD > 0.05pp; theta exact). COMPARISON.md with PASS/FAIL and any
leakage finding. Do not report the most recent year of non-selected rows. Do not edit leader files.
