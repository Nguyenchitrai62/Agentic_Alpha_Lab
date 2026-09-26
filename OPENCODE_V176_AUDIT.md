# v176 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v176_audit/` and `tests/test_v176_audit.py`.
Do NOT open v176/ until part A is saved (`replication.json`). Base: your v175 audit replication (limit dip sleeve,
same walk-forward k) and the audited engine_real + v170 execution.
A: sleeve_unit = v175 sleeve (size 0.25 per event, per-bar sum) / 1.657. realized_total[i] = 0.8 * sum_j books[i-2,j] *
(o[i,j]/o[i-1,j] - 1) + 0.6 * carry[i-1] + sleeve_unit[i-1]; vol = rolling std 360 (min 120) * sqrt(2190);
s = min(0.25/vol, 2) (1 if NaN). Loop exactly as engine_real (governor, budget, min notional, v170 60-minute execution,
funding, carry) with net[i] += s[i] * g[i] * sleeve_unit[i] on live bars. Report monthly, yearly net/DD, full-path DD,
mean s. Save `replication.json`.
Also (diagnostic): (a) a cost-stress row: book maker fee 0.0004, taker 0.0007, +5 bps on every taker fill, sleeve maker
0.0004 / taker exit 0.0007 + 5 bps; (b) full-path DD marked on 1m closes (books positions and open sleeve positions
marked every minute) for the primary row.
B: compare with `v176/v176_result.json`, check look-ahead (sleeve_unit[i-1] known at decision i), write COMPARISON.md.
Do not edit leader files.
