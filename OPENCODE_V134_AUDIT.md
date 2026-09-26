# v134 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v134_audit/` and `tests/test_v134_audit.py`.
Base: your v133 replication (v132_v133_audit if finished; otherwise build it from OPENCODE_V132_V133_AUDIT.md A2). Do NOT
open v134/ until part A is saved (`replication.json`).
A: identical to v133 except in the long/short weight formula used for the v94 LS and v103 LS books the short leg is
((-pred).clip(0)/0.5).clip(upper=1) only where rib == -1 (0 elsewhere) instead of where rib != 1; long legs unchanged.
Report three scenarios with full-path DD and the hidden year with the v104 strict fill rule.
Save `replication.json`, compare with v134/v134_result.json (explain return diff > 1pp or DD diff > 0.5pp), audit
v134_bear_only_shorts.py for look-ahead, write COMPARISON.md. Do not edit leader files.
