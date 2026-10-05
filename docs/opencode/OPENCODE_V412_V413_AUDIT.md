# v412 + v413 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Both run the correlation-aware BOT R2B1D18BF (B1 dip size x 1/(1+n), dips x1.8, budget 0.26 x 1.8, bear-regime book longs x0.5; reference
= v410 cache) on the 5-year 4-phase harness (see the version docstrings = pre-registration). v412 row R2B1D18BFS adds: book SHORT targets x0.5
where BTC 4h open < its 1200-bar mean AND the std of the last 180 4h log returns > its trailing 2190-bar median. v413 rows R2B1D18BFH /
R2B1D12BFH add engine_user hourly=True with prep["sig1h"] computed exactly as engine_user.prepare (dips x1.8 / x1.2).
Part A (blind, before opening the v412 / v413 result JSONs, run logs or pkls): check both masks / sigma_1h are causal (truncation test on 10
rows); reproduce R2B1D18BFS on phase 2 and R2B1D12BFH on phase 0 with your own wiring; save replication.json. Part B: compare (final equity
relative > 1e-6 = mismatch); recompute rows / folds / finals / full-path DD from the pkls. COMPARISON.md with "## Verdict" per version.
At most 1 heavy process. Write only under `research/parallel/rounds/parallel-20260906-r2/v412_v413_audit/` and `tests/test_v412_v413_audit.py`.
