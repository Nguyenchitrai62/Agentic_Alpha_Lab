# v172 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v172_audit/` and `tests/test_v172_audit.py`.
Do NOT open v172/ until part A is saved (`replication.json`). Base: your v171 audit replication (`v171_audit/`, if it
exists; otherwise implement the v171 sleeve per OPENCODE_V171_AUDIT.md) and your v170 audit replication (60-minute
execution) on the audited engine_real.
A: identical to the v171 sleeve except the fill cost: slippage per side = max(0.0002, 0.25 * (high - low) / open) of the
fill minute (entry: minute m+1 of the holding bar T; exit: minute 0 of the next 4h bar T + 4h); entry = open(m+1) *
(1 + s_in), exit = open(T + 4h) * (1 - s_out); r = exit/entry - 1 - 0.001 - funding settled at T + 4h. k per anchor
from (2, 2.5, 3, 3.5, 4) by pre-anchor Sharpe of 0.25 * sum_sym r, with THIS cost. Books: engine_real (all realism),
execution W = 60 minutes (v170), target 0.25, governor; net[i] += g[i] * size/0.25 * sleeve[i] on live bars.
Rows: books alone (must be 3.802 / 18.93), size 0.25, 0.20, 0.15; sleeve alone per anchor (k, net, DD, events).
Save `replication.json`.
B: compare with `v172/v172_result.json` (return > 1pp, DD > 0.5pp explained), review `v172/v172_sleeve_realistic.py`
for look-ahead and for the exit-minute alignment (cube row i+1, minute 0 must be the minute starting at T + 4h), write
COMPARISON.md with a verdict. Do not edit leader files.
