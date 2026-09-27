# v145 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v145_audit/` and `tests/test_v145_audit.py`.
Base: your audited v141_v142 replication. Do NOT open v145/ until part A is saved (`replication.json`).
A: v142 with the cross-sectional list extended: on the v114 panel xs_c/xr_c for every model feature c except asset, rib
and btc_*; on the v103 panel additionally for every v103 feature not in that list (again excluding asset, rib, btc_* and
targets). Everything else exactly v142 in the literal v133 pipeline: flat-fee scenarios, target 0.15, ungoverned (NOT the
v141 wrapper). Report ICs and three scenarios with full-path DD.
Save `replication.json`, compare with v145/v145_result.json (explain IC diff > 0.01, return diff > 1pp, DD diff > 0.5pp),
audit v145_xs_all_features.py for look-ahead, write COMPARISON.md. Do not edit leader files.
