# v126 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v126_audit/` and `tests/test_v126_audit.py`.
Base: your audited v123_v125 replication (v125 un-subsampled weight formulas and phase helper). Do NOT open v126/ until
part A is saved (`replication.json`).
A: for phase p in 0..5, all three v115 books keep rows with position % 6 == p (ffill), own vol scales, v115 primary
portfolio (0.25/0.25/0.5, target 0.15, ungoverned, v110 engine). Report per phase monthly/full-path DD per scenario,
yearly normal nets, and the phase mean/min/max (phase 0 must equal v115).
Save `replication.json`, compare with v126/v126_result.json (explain return diff > 1pp or DD diff > 0.5pp), audit
v126_phase_dispersion.py, write COMPARISON.md. Do not edit leader files.
