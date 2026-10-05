# v416 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v416 runs R2B1D17BF (B1 dip size x 1/(1+n), dips x1.7, budget 0.26 x 1.7, bear-regime book longs x0.5; reference = v411 cache) on the
5-year 4-phase harness (see the version docstring = pre-registration). Row R2B1D17BFD adds ONLY a BTC-dominance book tilt (docstring rule: dom30, expanding terciles on rows < t, x1.25 top / x0.75 bottom, after the bear-book filter, before the shifted-clock ffill)

Part A (blind, before opening the v416 result JSON, run logs or pkls): reproduce R2B1D17BFD on phase 1 and phase 3 with your own
wiring (v411/v388 code paths); save replication.json. Part B: compare (final equity relative > 1e-6 = mismatch); recompute rows / folds /
finals / full-path DD from the pkls. COMPARISON.md with "## Verdict" and a line "v416: PASS" or "v416: FAIL".
At most 1 heavy process. Write only under `research/parallel/rounds/parallel-20260906-r2/v416_audit/` and `tests/test_v416_audit.py`.
