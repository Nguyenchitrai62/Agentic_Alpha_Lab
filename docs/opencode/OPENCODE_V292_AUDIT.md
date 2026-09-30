# v292 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v292 chooses CB's risk level (sleeve budget 0.18 / 0.16 / 0.14, book target 0.25 / 0.23) by dev DD under base, cost stress (maker 0.0004,
taker 0.0012) and 15-minute latency (win_start 15). Write only under `research/parallel/rounds/parallel-20260906-r2/v292_audit/` and
`tests/test_v292_audit.py`; relative paths without quoting; do NOT open v292/v292_result.json or v292/run.log before `replication.json`.
A: replicate all 16 rows (4 levels x base / cost_stress / latency_15 / latency_30) with the CB books and C4 engine arguments, the stress
pool (dev DD = max yearly dd_1m 2021-2024 <= 20 and no losing dev year in base, cost_stress, latency_15), the robust criterion on the base
rows, and the final score of the selected row only; check that the stress rows change only costs / the first fill minute and that no
most-recent-year value feeds the selection. B: compare with the JSON (return > 1pp or DD > 0.5pp = mismatch); COMPARISON.md with
"## Verdict" PASS/FAIL (feature timing, label windows, fit windows, fill timing). Do not edit leader files.
