# v147 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v147_audit/` and `tests/test_v147_audit.py`.
Base: your v144 replication (v141_v142_audit A2). Do NOT open v147/ until part A is saved (`replication.json`).
A: v144 exactly, except the v103 model uses horizons (3, 6, 18): extra target y3 = clip(log(open[t+4]/open[t+1]) /
(vol42*sqrt(3)), -4, 4), rows need t + 4*4h < cutoff; v103 prediction = mean of the three HGBs; embargo 78 unchanged. Rows
0.15 ungoverned, 0.20 and 0.25 governed with 10 bps 1m execution. Report monthly, yearly and full-path DD.
Save `replication.json`, compare with v147/v147_result.json (explain return diff > 1pp or DD diff > 0.5pp), audit
v147_v103_12h_horizon.py for look-ahead, write COMPARISON.md. Do not edit leader files.
