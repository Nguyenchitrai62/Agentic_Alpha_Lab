# v120 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v120_audit/` and `tests/test_v120_audit.py`.
Base: your audited v118 replication (v115 books + per-asset no-trade band in the sequential engine). Do NOT open v120/
until part A is saved (`replication.json`).
A: band 0.05, ungoverned, portfolio vol target in (0.10, 0.12, 0.15, 0.18, 0.20, 0.22, 0.25): the target enters only
s = min(target/vol, 2) (vol from the ungated books + carry as v115). Report monthly, worst-year DD and full-path DD per
target and scenario (0.15 must equal your v118 band-0.05 row).
Save `replication.json`, compare with v120/v120_result.json (explain return diff > 1pp or DD diff > 0.5pp), audit
v120_risk_frontier.py for look-ahead, write COMPARISON.md. Do not edit leader files.
