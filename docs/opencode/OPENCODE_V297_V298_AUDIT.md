# v297 + v298 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Both run on top of v296 J1 (CB books, C4 rules, v295 size agent + v294 X4 take-profit agent, pooled 35-coin dip experience).
v297 moves risk from the book to the dip sleeve (book vol target 0.25/0.20/0.15, sleeve risk budget 0.18/0.24) with a new-goal selection
rule (tier 1 dev DD <= 15, tier 2 <= 16, worst dev year >= 3.0, else nothing replaces J1). v298 adds partial take-profits to the book
(partial_k 2/3, partial_frac 0.5/0.33) with a win-rate selection rule (worst dev year >= 0.95 J1, dev DD <= J1 + 0.5, win rate + 0.03).
Write only under `research/parallel/rounds/parallel-20260906-r2/v297_v298_audit/` and `tests/test_v297_v298_audit.py`; relative paths
without quoting; do NOT open the v297 / v298 result JSONs or run logs before `replication.json`.
A: reuse your v296 audit replica of the J1 agents; replicate J1_ref (6.268) and every row of both versions (dev4, worst dev year, dev DD,
dev book-trade and dip-rung win rates, partial counts), the two selection rules exactly as written (both select nothing), and confirm no
most-recent-year value was computed for a non-selected row. Check that the target / budget / partial parameters are the only changes and
that partial take-profits fill as limit orders after minute 5 with the stop moved to break-even. B: compare with the JSONs (return > 1pp
or DD > 0.5pp = mismatch); COMPARISON.md with "## Verdict" PASS/FAIL per version. Do not edit leader files.
