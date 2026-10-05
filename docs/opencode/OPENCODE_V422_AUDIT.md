# v422 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v422 runs R2B1D17BF (B1 dip size x 1/(1+n), dips x1.7, budget 0.26 x 1.7, bear-regime book longs x0.5; reference = v411 cache) on the
5-year 4-phase harness (see the version docstring = pre-registration). Rows add the engine hook sleeve_gross_cap G (2.0 or 1.5) with dip multiplier kd 2.0 (size and budget 0.26 x kd) and B1 flush threshold F (2.5 or 2.0); R2B1D17BFG2 is the v421 cache

Part A (blind, before opening the v422 result JSON, run logs or pkls): reproduce G2K20 on phase 2 and G2F20K20 on phase 0 with your own
wiring (v411/v388 code paths); save replication.json. Part B: compare (final equity relative > 1e-6 = mismatch); recompute rows / folds /
finals / full-path DD from the pkls. COMPARISON.md with "## Verdict" and a line "v422: PASS" or "v422: FAIL".
At most 1 heavy process. Write only under `research/parallel/rounds/parallel-20260906-r2/v422_audit/` and `tests/test_v422_audit.py`.
