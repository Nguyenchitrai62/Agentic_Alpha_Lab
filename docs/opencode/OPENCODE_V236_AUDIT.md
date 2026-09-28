# v236 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v236_audit/` and `tests/test_v236_audit.py`. Use relative paths without
quoting. Do NOT open v236/v236_result.json or its logs until part A is saved (`replication.json`); read `v236/v236_whale_flow.py`,
`v236/flow_features.py`, `scripts/fetch_aggtrades_flow.py`.
A: (1) Data: for at least 3 random months (one each for BTC, SOL, XRP) download the raw aggTrades zip from data.binance.vision and
independently aggregate taker buy / sell notional and counts per UTC 4h bar and tier (<10k, 10k-100k, 100k-1M, >=1M USDT; seller-initiated
when is_buyer_maker is true); compare with data/raw/aggflow_20260928/{SYM}_flow_4h.parquet (max abs diff). Check the per-symbol
manifests for gaps / double counting (months in the parquet == months in the manifest). (2) Features: re-implement flow_features and
check that a value at bar t uses only bars <= t (truncation test on >= 5 cut points per symbol). (3) Rebuild at least one anchor of
member_A_whale and member_Aq_whale (artifacts/research/engine_real/) and compare with the caches; run the v218 D2 trade mode on v233_T3
(must be 5.485), W1, W2; report dev4, worst first-four monthly, gate DD; robust selection; most recent year only for the selected row.
Save `replication.json`. B: compare with the result JSON (return > 0.01pp/month, DD > 0.05pp). COMPARISON.md with a "## Verdict"
PASS/FAIL, explicitly checking feature timing, label windows, fit windows and fill timing. Do not edit leader files.
