# v423 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v423 runs R2B1D17BF (B1 dip size x 1/(1+n), dips x1.7, budget 0.26 x 1.7, bear-regime book longs x0.5; reference = v411 cache) on the
5-year 4-phase harness (see the version docstring = pre-registration). Rows set the size of dip rungs at the dropped depths (5.0; 4.0 and 5.0) to 0 through the sleeve_fill_size wrapper (rung index -> depth via kw rungs); X45G2 also sets sleeve_gross_cap 2.0

Part A (blind, before opening the v423 result JSON, run logs or pkls): reproduce R2B1D17BFX45 on phase 2 and R2B1D17BFX5 on phase 0 with your own
wiring (v411/v388 code paths); save replication.json. Part B: compare (final equity relative > 1e-6 = mismatch); recompute rows / folds /
finals / full-path DD from the pkls. COMPARISON.md with "## Verdict" and a line "v423: PASS" or "v423: FAIL".
At most 1 heavy process. Write only under `research/parallel/rounds/parallel-20260906-r2/v423_audit/` and `tests/test_v423_audit.py`.
