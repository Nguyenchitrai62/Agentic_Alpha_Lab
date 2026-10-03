# v343-v344 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Two versions in research/parallel/rounds/parallel-20260906-r2/ (docstrings = pre-registration), wired exactly as the audited v342
(see research/parallel/rounds/parallel-20260906-r2/v340_v342_audit/) except that the books are CB = (2A + 2B + D)/5 with
B = v310.W["grp"]["wB"] (member_B_tv + member_Bq_tv)/2: v343 depth pairs (3.0, 4.0) / (3.0, 5.0) / (2.5, 4.0); v344 book_mult 0.75 / 0.50 / 1.00
(book_mult 1.0 leaves the trade dict unchanged). Fitness = v310.fitness with the all-trade win rate; folds k = 2, 3; final on dev4; most recent
year once; stress row sleeve_start 31.
Write only under `research/parallel/rounds/parallel-20260906-r2/v343_v344_audit/` and `tests/test_v343_v344_audit.py`; relative paths without quoting;
do NOT open the two result JSONs or run logs before replication.json is saved.
Part A: replicate every row (dev4, per-year, F), fold choices, transfer flags, final and stress rows with your own wiring; check that the reference
L2 reproduces the backend replay of the paper pipeline M3 (backend/history_tm.py pipeline "v342", dev4 6.233), that each rung uses the agent table
at its own depth, and that no most-recent-year number enters any choice. Save replication.json FIRST. Part B: compare (monthly > 0.01 pp,
DD > 0.05 pp, F > 0.001, win > 0.001 = mismatch, report all); COMPARISON.md with "## Verdict" PASS/FAIL per version. Do not edit leader files.
