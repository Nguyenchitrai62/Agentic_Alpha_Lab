# v155 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v155_audit/` and `tests/test_v155_audit.py`.
Base: your v154 replication (v154_audit; if unfinished build it from OPENCODE_V154_AUDIT.md). Do NOT open v155/ until part
A is saved (`replication.json`).
A: v154 books ((A + B + D)/3) in the v144 engine with the unchanged 20% governor at targets 0.25, 0.28, 0.30 (cap 2, 10 bps
1m execution). Report monthly, yearly, full-path DD per target (0.25 must equal your v154 primary row).
Save `replication.json`, compare with v155/v155_result.json (explain return diff > 1pp or DD diff > 0.5pp), audit
v155_ensemble_frontier.py for look-ahead, write COMPARISON.md. Do not edit leader files.
