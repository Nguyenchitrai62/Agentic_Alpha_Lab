# v424 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v424 runs R2B1D17BF (B1 dip size x 1/(1+n), dips x1.7, budget 0.26 x 1.7, bear-regime book longs x0.5; reference = v411 cache) on the
5-year 4-phase harness (see the version docstring = pre-registration). Rows change the dip multiplier kd (1.3 / 1.4 / 1.7, budget 0.26 x kd), drop the 5.0 sigma rung (size 0) and set the B1 flush threshold F 2.0 as the docstring lists

Part A (blind, before opening the v424 result JSON, run logs or pkls): reproduce R2B1D13BF on phase 1 and F20K17BFX5 on phase 3 with your own
wiring (v411/v388 code paths); save replication.json. Part B: compare (final equity relative > 1e-6 = mismatch); recompute rows / folds /
finals / full-path DD from the pkls. COMPARISON.md with "## Verdict" and a line "v424: PASS" or "v424: FAIL".
At most 1 heavy process. Write only under `research/parallel/rounds/parallel-20260906-r2/v424_audit/` and `tests/test_v424_audit.py`.
