# v238 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v238_audit/` and `tests/test_v238_audit.py`. Use relative paths without
quoting. Do NOT open v238/v238_result.json or its logs until part A is saved (`replication.json`); read `v238/v238_market_flow.py` and
`v236/flow_features.py`.
A: re-implement the market-wide features (BTC fl_big_imb6 / fl_big_imb42, cross-asset means of fl_big_imb6 and fl_div6 per bar) and check
that the value at bar t uses only per-asset rows at t (truncation tests); verify at least one anchor of member_A_M1_add_market and
member_A_M2_market_only against rebuilds; run the v218 D2 trade mode on v236_W2 (must be 5.774), M1, M2; report dev4, worst first-four
monthly, gate DD; robust selection; most recent year only for the selected row. Save `replication.json`. B: compare with the result
JSON (return > 0.01pp/month, DD > 0.05pp). COMPARISON.md with a "## Verdict" PASS/FAIL, explicitly checking feature timing, label
windows, fit windows and fill timing. Do not edit leader files.
