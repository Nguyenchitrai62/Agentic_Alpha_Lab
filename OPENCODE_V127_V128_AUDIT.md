# v127 + v128 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v127_v128_audit/` and `tests/test_v127_v128_audit.py`.
Base: your audited v123_v125 (tranching), v126 (phase runs) and v115 replications. Do NOT open v127/ or v128/ until
part A is saved (`replication.json`).
A1 (v127): v125 tranched books, v115 primary portfolio: three scenarios (v110 engine) and the hidden year with the v104
strict fill rule and vectorised v104 cost path on the tranched weights. Report scenarios, full-path DDs and hidden-year
net/DD/maker rate/orders.
A2 (v128): add to the v114 panel hv_days = (t - last halving)/1461 days (halvings 2012-11-28, 2016-07-09, 2020-05-11,
2024-04-20 UTC; last halving <= t), hv_sin/hv_cos = sin/cos(2*pi*hv_days); retrain v92/v94 with all non-target columns;
v115 portfolio with unchanged v103, evaluated per rebalance phase 0..5 (v126 method); report per-anchor v92 IC and phase
mean monthly / worst full-path DD, with and without the features.
Save `replication.json`, compare with v127/v127_result.json and v128/v128_result.json (explain return diff > 1pp, DD
diff > 0.5pp, IC diff > 0.01), audit both scripts for look-ahead, write COMPARISON.md. Do not edit leader files.
