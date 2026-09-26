# v117 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v117_audit/` and `tests/test_v117_audit.py`.
Base: your audited v115 replication. Do NOT open v117/ until part A is saved (`replication.json`).
A: identical to v115 primary (target 0.15, ungoverned, v110 engine) except the v92 long-only and v94 long/short weight
frames keep every k-th row of their own index (k = 12 primary, 42 secondary; 6 = v115 reference) and forward-fill; the
v103 LS book stays at k = 6. Vol scales of each book are computed on the k-rebalanced weights as in v115. Report yearly
net/DD/fills and full-path DD for k = 12, 42, 6 in the three scenarios.
Save `replication.json`, compare with v117/v117_result.json (explain return diff > 1pp or DD diff > 0.5pp), audit
v117_slow_rebalance.py for look-ahead, write COMPARISON.md. Do not edit leader files.
