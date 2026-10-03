# v368-v370 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Three versions in research/parallel/rounds/parallel-20260906-r2/ (docstrings = pre-registration), kpack inputs (KPACK=artifacts/kaggle/kpack/pack347):
v368 = BOT R2 (v306 seed) with the tighten rule (signal flat + position under water -> "tighten") and with tighten + book SL 5 / TP 10 (v306 BOT
fitness, folds k = 1, 2, 3); v369 = exhaustive sub-account blends of R2, M5 and M4 (monthly rebalance; v353 combine(); member paths from engine
path_out; M5 = M4 + loss_act tighten, M4 = M3 + book SL 5 / TP 10, references 6.015 / 6.392); v370 = M5 with trade "tighten" 1.0 / 1.5 / 2.0 judged
with the v310 (book win) fitness.
Part A (blind, before opening result JSONs / run logs): replicate every row (dev4, per-year, F), fold choices, transfer flags and finals with your own
wiring; for v369 recompute 10 random blends; check that no most-recent-year number enters any choice. Save replication.json FIRST. Part B: compare
(monthly > 0.01 pp, DD > 0.05 pp, F > 0.001, win > 0.001 = mismatch, report all); COMPARISON.md with "## Verdict" PASS/FAIL per version.
Write only under `research/parallel/rounds/parallel-20260906-r2/v368_v370_audit/` and `tests/test_v368_v370_audit.py`; relative paths without quoting.
Do not edit leader files.
