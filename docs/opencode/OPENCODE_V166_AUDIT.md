# v166 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v166_audit/` and `tests/test_v166_audit.py`.
Base: your v154 replication (member books A, B, D). Do NOT open v166/ until part A is saved (`replication.json`).
A: align A, B, D on the union 4h index and the v144 asset columns (missing -> 0). Per bar and asset, signs s = sign(weight)
of the three members; nz = number of non-zero signs, pos/neg = counts of positive/negative signs. Multiplier m = 1.3 if
nz >= 2 and all non-zero signs equal; 0.6 if pos > 0 and neg > 0; else 1.0. Books = m * (A + B + D)/3. v144 engine rows
(0.15 ungoverned, 0.20/0.25 governed, 10 bps 1m execution). Report the multiplier shares and monthly/yearly/full-path DD.
Save `replication.json`, compare with v166/v166_result.json (explain return diff > 1pp or DD diff > 0.5pp), audit
v166_agreement_confidence.py for look-ahead, write COMPARISON.md. Do not edit leader files.
