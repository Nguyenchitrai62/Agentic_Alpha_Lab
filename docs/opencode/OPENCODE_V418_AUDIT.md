# v418 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v418 runs R2B1D17BF (B1 dip size x 1/(1+n), dips x1.7, budget 0.26 x 1.7, bear-regime book longs x0.5; reference = v411 cache) on the
5-year 4-phase harness (see the version docstring = pre-registration). Row R2B1D17BFDS adds ONLY the DVOL short gate (docstring rule: gate set from research/tournament/oc_dvolshort/panel.parquet; ALSO verify that gate set causally by recomputing z90 and the walk-forward q67 for 20 random gated and 20 ungated short rows from research/tournament/oc_dvol/dvol_hourly.parquet with the oc_dvolbook definition)

Part A (blind, before opening the v418 result JSON, run logs or pkls): reproduce R2B1D17BFDS on phase 0 and phase 2 with your own
wiring (v411/v388 code paths); save replication.json. Part B: compare (final equity relative > 1e-6 = mismatch); recompute rows / folds /
finals / full-path DD from the pkls. COMPARISON.md with "## Verdict" and a line "v418: PASS" or "v418: FAIL".
At most 1 heavy process. Write only under `research/parallel/rounds/parallel-20260906-r2/v418_audit/` and `tests/test_v418_audit.py`.
