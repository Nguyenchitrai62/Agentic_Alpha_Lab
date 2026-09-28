# v218 + v219 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v218_v219_audit/` and `tests/test_v218_v219_audit.py`. Use relative
paths without quoting. Do NOT open v218/v218_result.json, v219/v219_result.json or their logs until part A is saved
(`replication.json`); read the pre-registrations `v218/v218_grid_risk_dial.py`, `v219/v219_sleeve_shift.py`.
A: using your independent v216 grid-trader replication (G2), run the configurations (book size multiplier M on every book position
of the trade mode - trade["book_mult"], the signal threshold uses the unscaled target; dip-sleeve stop-risk budget B; rung size x R
via size_mult): grid_G2 (1.0, 0.12, 1.5); v218 D1 (1.10, 0.12, 1.5), D2 (1.0, 0.15, 1.75), D3 (1.05, 0.135, 1.6); v219 H1 (0.90, 0.18,
2.0), H2 (1.0, 0.18, 2.0), H3 (0.80, 0.21, 2.25). Report dev4, worst first-four monthly, gate DD per row; robust selection within each
version's candidates; most recent year only for each version's selected row. Check that the book multiplier and sleeve settings
change nothing else. Save `replication.json`.
B: compare with the result JSONs (return > 0.01pp/month, DD > 0.05pp). COMPARISON.md with PASS/FAIL. Do not report the most recent
year of non-selected rows. Do not edit leader files.
