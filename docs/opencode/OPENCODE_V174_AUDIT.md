# v174 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v174_audit/` and `tests/test_v174_audit.py`.
Do NOT open v174/ until part A is saved (`replication.json`). Base: your v172 audit replication (`v172_audit/`).
A: mirror of the v172 dip sleeve: trigger = first minute m in 16..238 of holding bar T with 1m close / open(T) - 1 >=
+k sigma; short entry = open(m+1) * (1 - s_in); cover = open(T + 4h) * (1 + s_out) (s as v172 from the fill minutes);
r = entry/cover - 1 - 0.001 + funding settled at T + 4h. k per anchor from (2, 2.5, 3, 3.5, 4) by pre-anchor Sharpe of
0.25 * sum_sym r. Rows (engine_real, v170 60-minute execution, target 0.25, governor): books + dip + spike, books +
spike, books + dip (must equal v172 4.597 / 22.42); spike sleeve alone per anchor (k, net, DD, events); correlation of
daily dip vs spike sleeve returns. Save `replication.json`.
B: compare with `v174/v174_result.json`, check look-ahead and the short-side funding sign, write COMPARISON.md.
Do not edit leader files.
