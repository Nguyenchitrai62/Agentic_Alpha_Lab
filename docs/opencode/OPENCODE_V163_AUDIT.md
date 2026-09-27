# v163 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v163_audit/` and `tests/test_v163_audit.py`.
Base: your v154 replication. Do NOT open v163/ until part A is saved (`replication.json`).
A: v154 exactly, except in all three members every OOS prediction frame (v92 LO, v94 LS, v103 LS) is smoothed before the
weight formulas: per asset, time-ordered, pred := pred.ewm(span=6, adjust=False).mean(). Books (A+B+D)/3, v144 engine rows.
Save `replication.json`, compare with v163/v163_result.json (explain return diff > 1pp or DD diff > 0.5pp), audit
v163_prediction_smoothing.py for look-ahead, write COMPARISON.md. Do not edit leader files.
