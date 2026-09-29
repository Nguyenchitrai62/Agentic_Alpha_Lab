# v262 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v262_audit/` and `tests/test_v262_audit.py`. Use relative paths without
quoting. Do NOT open v262/v262_result.json or its logs until part A is saved (`replication.json`); read `v262/v262_spot_order_flow.py`,
`v244/v244_cross_venue_flow.py` (same design) and `v236/flow_features.py`.
A: (1) Data: rebuild the spot ORDER table for one sampled month of two symbols from the public archive (data/spot/monthly/aggTrades,
consecutive rows with the same transact time and side = one order; tiers <10k / 10k-100k / 100k-1M / >=1M USDT) and compare with
`data/raw/aggflow_spot_20260929_orders/{SYM}_flow_4h.parquet`; check the manifests list every month. (2) Features: the six v236 formulas on
the spot table and on the perp+spot sum; truncation probes (features at t unchanged when data after t + 4h is removed). (3) Members:
cached `member_{A,Aq}_{Z1_add_spot,Z2_venue_sum_spot}.parquet` replayable; rebuild one anchor of member A for Z2 and compare. (4) Reference
(O1 members, budget 0.18) must give dev4 5.777; run Z1 / Z2; robust selection; most recent year only for the selected row.
Save `replication.json`. B: compare with the result JSON (return > 0.01pp/month, DD > 0.05pp). COMPARISON.md with a "## Verdict" PASS/FAIL,
explicitly checking feature timing, label windows, fit windows and fill timing. Do not edit leader files.
