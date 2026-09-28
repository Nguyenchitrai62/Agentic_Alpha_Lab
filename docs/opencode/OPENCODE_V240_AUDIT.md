# v240 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v240_audit/` and `tests/test_v240_audit.py`. Use relative paths without
quoting. Do NOT open v240/v240_result.json or its logs until part A is saved (`replication.json`); read `v240/v240_order_level_flow.py`,
`scripts/fetch_aggtrades_flow.py` (--orders, _orders) and `v236/flow_features.py`.
A: (1) Data: for 2 random months (BTC, XRP) download the raw USD-M aggTrades zip, rebuild taker orders independently (consecutive rows
with the same transact_time and is_buyer_maker = one order; notional = sum of price*qty) and aggregate per UTC 4h bar and tier; compare
with data/raw/aggflow_20260928_orders/{SYM}_flow_4h.parquet; confirm the total notional per bar equals the fill-level table
(data/raw/aggflow_20260928); check the per-symbol manifests. Note whether an order can span two chunks of the reader (2,000,000 rows)
and estimate the effect. (2) Features: truncation tests on the order-level flow features (>= 5 cuts per symbol). (3) Verify one anchor of
member_A_O1_orders against a rebuild; run the v218 D2 trade mode on v236_W2 (must be 5.774), O1, O2; report dev4, worst first-four
monthly, gate DD; robust selection; most recent year only for the selected row. Save `replication.json`. B: compare with the result JSON
(return > 0.01pp/month, DD > 0.05pp). COMPARISON.md with a "## Verdict" PASS/FAIL, explicitly checking feature timing, label windows, fit
windows and fill timing. Do not edit leader files.
