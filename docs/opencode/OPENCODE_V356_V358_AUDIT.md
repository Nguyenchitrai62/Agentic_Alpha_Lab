# v356-v358 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Three versions in research/parallel/rounds/parallel-20260906-r2/ (docstrings = pre-registration), all variants of the deployed MANUAL pipeline M3
with the kpack inputs (KPACK=artifacts/kaggle/kpack/pack347; wiring = the audited v347 run_genome with the CB seed; reference dev4 6.233):
v356 = rungs (3, 4, 5) with size_mult 4.375 / 2.92 and per-rung agent tables at each depth; v357 = dip-agent tables refitted with four extra state
features (v357_ux_tables.py -> artifacts/research/engine_real/v357_ux_tables.parquet; refit ONE anchor yourself and compare predictions; check that
x7..x10 use only bars closed before the holding bar, both in the training fills and in the bar-open table rows); v358 = engine target 0.27 / 0.29.
Note v357's process note: its first scoring run read the wrong table file and crashed before any row; the corrected script is the one to audit.
Part A (blind, before opening result JSONs / run logs): replicate every row (dev4, per-year, F), fold choices, transfer flags and finals; check that
no most-recent-year number enters any choice. Save replication.json FIRST. Part B: compare (monthly > 0.01 pp, DD > 0.05 pp, F > 0.001, win > 0.001,
predictions > 1e-9 = mismatch, report all); COMPARISON.md with "## Verdict" PASS/FAIL per version.
Write only under `research/parallel/rounds/parallel-20260906-r2/v356_v358_audit/` and `tests/test_v356_v358_audit.py`; relative paths without quoting.
Do not edit leader files.
