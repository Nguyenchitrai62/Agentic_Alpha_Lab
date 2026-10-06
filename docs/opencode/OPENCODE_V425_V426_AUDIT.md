# v425_v426 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v425_v426 runs R2B1D17BF (B1 dip size x 1/(1+n), dips x1.7, budget 0.26 x 1.7, bear-regime book longs x0.5; reference = v411 cache) on the
5-year 4-phase harness (see the version docstring = pre-registration). Two versions: v425 rows (kd 1.3/1.4/1.5 with sleeve_gross_cap 2.0, optional 5.0 sigma rung drop; v425/v425_cap_conservative.py) and v426 rows (per-coin book brake gate set from research/tournament/oc_bookcoinbrake/panel.parquet applied to bear-filtered standard book long weights x0.5; v426/v426_book_brake.py; also check the brake gate is causal by recomputing it for 20 random rows)

Part A (blind, before opening the v425_v426 result JSON, run logs or pkls): reproduce v425 D14BFG2 on phase 1 and v426 G2BRK on phase 2 with your own
wiring (v411/v388 code paths); save replication.json. Part B: compare (final equity relative > 1e-6 = mismatch); recompute rows / folds /
finals / full-path DD from the pkls. COMPARISON.md with "## Verdict" and a line "v425: PASS" or "v425: FAIL" and a line "v426: PASS" or "v426: FAIL".
At most 1 heavy process. Write only under `research/parallel/rounds/parallel-20260906-r2/v425_v426_audit/` and `tests/test_v425_v426_audit.py`.
