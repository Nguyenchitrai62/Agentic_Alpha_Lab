# v420 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v420 runs R2B1D17BF (B1 dip size x 1/(1+n), dips x1.7, budget 0.26 x 1.7, bear-regime book longs x0.5; reference = v411 cache) on the
5-year 4-phase harness (see the version docstring = pre-registration). Rows change the B1 flush threshold F (1 - F sigma4 instead of 2.5) and the dip multiplier kd (size and budget 0.26 x kd); R2B1F20K17 is taken from research/diagnostics/oc_plateau/oc_plateau_runs.pkl (check it equals a fresh F 2.0 / kd 1.7 run on one phase)

Part A (blind, before opening the v420 result JSON, run logs or pkls): reproduce R2B1F15K23 on phase 3 and R2B1F20K17 on phase 1 with your own
wiring (v411/v388 code paths); save replication.json. Part B: compare (final equity relative > 1e-6 = mismatch); recompute rows / folds /
finals / full-path DD from the pkls. COMPARISON.md with "## Verdict" and a line "v420: PASS" or "v420: FAIL".
At most 1 heavy process. Write only under `research/parallel/rounds/parallel-20260906-r2/v420_audit/` and `tests/test_v420_audit.py`.
