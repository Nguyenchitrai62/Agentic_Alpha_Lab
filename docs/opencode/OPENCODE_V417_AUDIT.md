# v417 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v417 runs R2B1D17BF (B1 dip size x 1/(1+n), dips x1.7, budget 0.26 x 1.7, bear-regime book longs x0.5; reference = v411 cache) on the
5-year 4-phase harness (see the version docstring = pre-registration). Rows R2B1D17BFC / X / CX add the docstring rules: C = per-coin 24h dip cooldown after a rung_sl exit (s < B <= s+24h, B = holding bar open, own sub-book), X = engine hook sleeve_sl_coin with XRPUSDT 5.5 sigma, others 4 (stop level AND budget cost), CX = both

Part A (blind, before opening the v417 result JSON, run logs or pkls): reproduce R2B1D17BFC on phase 2 and R2B1D17BFX on phase 1; also check the engine diff (git diff of engine_user.py: sleeve_sl_coin None must be bit-for-bit the old code) with your own
wiring (v411/v388 code paths); save replication.json. Part B: compare (final equity relative > 1e-6 = mismatch); recompute rows / folds /
finals / full-path DD from the pkls. COMPARISON.md with "## Verdict" and a line "v417: PASS" or "v417: FAIL".
At most 1 heavy process. Write only under `research/parallel/rounds/parallel-20260906-r2/v417_audit/` and `tests/test_v417_audit.py`.
