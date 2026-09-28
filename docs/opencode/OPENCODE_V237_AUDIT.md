# v237 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v237_audit/` and `tests/test_v237_audit.py`. Use relative paths without
quoting. Do NOT open v237/v237_result.json or its logs until part A is saved (`replication.json`); read `v237/v237_spot_flow.py`,
`v237/spot_flow_features.py`, `v236/flow_features.py`, `scripts/fetch_aggtrades_flow.py`.
A: (1) Data: for 2 random months (BTC, XRP) re-aggregate the raw SPOT aggTrades zip from data.binance.vision (data/spot/monthly/aggTrades)
per UTC 4h bar and tier and compare with data/raw/aggflow_spot_20260928/{SYM}_flow_4h.parquet; check the per-symbol spot manifests
(months in parquet == months in manifest). (2) Features: re-implement spot_flow_features and run truncation tests (>= 5 cuts per symbol).
(3) Verify at least one anchor of member_A_X2_spot_div / member_Aq_X2_spot_div against rebuilds; run the v218 D2 trade mode on
v236_W2 (must be 5.774), X1, X2; report dev4, worst first-four monthly, gate DD; robust selection; most recent year only for the
selected row. Save `replication.json`. B: compare with the result JSON (return > 0.01pp/month, DD > 0.05pp). COMPARISON.md with a
"## Verdict" PASS/FAIL, explicitly checking feature timing, label windows, fit windows and fill timing. Do not edit leader files.
