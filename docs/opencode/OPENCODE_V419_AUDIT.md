# v419 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v419 runs R2B1D17BF (B1 dip size x 1/(1+n), dips x1.7, budget 0.26 x 1.7, bear-regime book longs x0.5; reference = v411 cache) on the
5-year 4-phase harness (see the version docstring = pre-registration). Rows R2B1D17BFBRK05 / BRK08 set engine sleeve_breaker 0.05 / 0.08; R2B1D17BFBUD13 sets the dip risk budget to 0.26 x 1.3 while sizes stay x1.7 (docstring)

Part A (blind, before opening the v419 result JSON, run logs or pkls): reproduce R2B1D17BFBRK05 on phase 2 and R2B1D17BFBUD13 on phase 1; also explain from the phase-2 events why neither cap binds in the 2024-01-03 crash bar with your own
wiring (v411/v388 code paths); save replication.json. Part B: compare (final equity relative > 1e-6 = mismatch); recompute rows / folds /
finals / full-path DD from the pkls. COMPARISON.md with "## Verdict" and a line "v419: PASS" or "v419: FAIL".
At most 1 heavy process. Write only under `research/parallel/rounds/parallel-20260906-r2/v419_audit/` and `tests/test_v419_audit.py`.
