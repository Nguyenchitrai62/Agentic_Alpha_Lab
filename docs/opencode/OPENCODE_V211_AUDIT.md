# v211 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v211_audit/` and `tests/test_v211_audit.py`. Use relative
paths without quoting. Do NOT open v211/ until part A is saved (`replication.json`). Base: your v210 trade-mode replication
(docs/opencode/OPENCODE_V210_AUDIT.md, variant T2).
A: T2 trade mode with risk sizing at order issue: weight = min(risk * governor[i] / (4 * sigma_d[i]), max_w), where the
governor is the engine's drawdown governor of the decision bar; R1 risk 0.01 max_w 1.0; R2 risk 0.02 max_w 1.5; R3 = R2 plus:
skip issuing when the reserved risk (sum over assets of risk*governor of resting orders and open positions whose stop is not
yet at break-even; released on cancel, expiry, exit or the break-even move) plus the new risk exceeds 0.05. The min-notional
check uses the new weight. Report ref_v205, v210_T2 and R1..R3: dev4, worst first-four-year monthly, gate DD, fills, stops,
tps, issued/cancelled/expired/risk_skipped, dev trade stats. Robust selection over R1..R3; most recent year only for the
selected row. Check causality. Save `replication.json`.
B: compare with `v211/v211_result.json` (return > 0.01pp/month, DD > 0.05pp, counts exact or explain). COMPARISON.md with
PASS/FAIL. Do not report the most recent year of non-selected rows. Do not edit leader files.
