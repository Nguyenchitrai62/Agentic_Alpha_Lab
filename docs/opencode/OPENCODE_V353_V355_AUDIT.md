# v353-v355 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Three versions in research/parallel/rounds/parallel-20260906-r2/ (docstrings = pre-registration), all with the kpack inputs
(KPACK=artifacts/kaggle/kpack/pack347; the packed engine_standalone.py must equal engine_user.py with the kpack header replacement):
v353 = exhaustive capital-weight blends of six member pipelines as monthly-rebalanced sub-accounts (member paths from engine_user path_out);
v354 = M3 with engine_user gov (0.20, 0.10) / (0.25, 0.15) / (0.16, 0.08); v355 = R2 with the new engine_user sleeve_hedge hook (BTC short of
h x the rung notional, opened at the fill minute close, closed at the exit minute close / next open, taker both legs; BTC rungs unhedged).
Part A (blind, before opening result JSONs / run logs): replicate the member rows (R2 7.079, M3 6.233), recompute 20 random v353 blends and the fold
choices / final with your own combine() (month-start reset, conservative sum of minima), replicate every v354 / v355 row, fold choice, transfer flag
and final; for v355 hand-check the hedge arithmetic on 5 random hedged rungs from the 1m data; check that the hook is default-neutral (R2 unchanged
with sleeve_hedge None) and that no most-recent-year number enters any choice. Save replication.json FIRST.
Part B: compare (monthly > 0.01 pp, DD > 0.05 pp, F > 0.001, win > 0.001 = mismatch, report all); COMPARISON.md with "## Verdict" PASS/FAIL per
version. Write only under `research/parallel/rounds/parallel-20260906-r2/v353_v355_audit/` and `tests/test_v353_v355_audit.py`; relative paths
without quoting. Do not edit leader files.
