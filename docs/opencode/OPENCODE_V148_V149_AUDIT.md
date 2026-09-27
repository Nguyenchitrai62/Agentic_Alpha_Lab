# v148 + v149 audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v148_v149_audit/` and `tests/test_v148_v149_audit.py`.
Base: your v144 replication (v141_v142_audit A2, v146/v147 audits). Do NOT open v148/ or v149/ until part A is saved.
A1 (v148): from your v144 net series (three rows), daily net = prod(1 + 4h nets of the UTC day) - 1 over the live span;
stationary block bootstrap: 5000 paths x 365 days, numpy default_rng(0); each block: start = rng.integers(n), length =
min(rng.geometric(1/30), remaining), indices wrap around; per path total return and max drawdown of the compounded path.
Report quantiles 5/25/50/75/95 (%), P(maxDD > 0.20), P(return < 0), P((1+ret)^(1/12)-1 >= 0.05).
A2 (v149): v144 with the two vol-forecast models given extra xs_/xr_ features (deviation from the majors' mean at t and
pct rank at t) for vol42 vol180 vol_ratio volz (v114 panel) and additionally rng6 ntr_z (v103 panel); return models/books/
engine unchanged. Report the three rows.
Save `replication.json`, compare with v148/v149 result JSONs (explain return diff > 1pp, DD diff > 0.5pp, probability
diff > 0.02), audit both scripts for look-ahead, write COMPARISON.md. Do not edit leader files.
