# v359-v361 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Three variants of the deployed MANUAL pipeline M3 in research/parallel/rounds/parallel-20260906-r2/ (docstrings = pre-registration), kpack inputs
(KPACK=artifacts/kaggle/kpack/pack347; wiring = the audited v347 run_genome with the CB seed; reference dev4 6.233):
v359 = engine cap 2.5 / 3.0; v360 = negative book weights scaled by 0.5 / 0.0 before the simulation; v361 = book pullback entry depth 0.5 / 1.0 sigma
(v315.with_entry). Part A (blind, before opening result JSONs / run logs): replicate every row (dev4, per-year, F), fold choices, transfer flags and
finals with your own wiring; check that no most-recent-year number enters any choice. Save replication.json FIRST. Part B: compare (monthly > 0.01 pp,
DD > 0.05 pp, F > 0.001, win > 0.001 = mismatch, report all); COMPARISON.md with "## Verdict" PASS/FAIL per version.
Write only under `research/parallel/rounds/parallel-20260906-r2/v359_v361_audit/` and `tests/test_v359_v361_audit.py`; relative paths without quoting.
Do not edit leader files.
