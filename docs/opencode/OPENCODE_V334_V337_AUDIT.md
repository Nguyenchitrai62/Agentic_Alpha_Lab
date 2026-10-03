# v334-v337 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Four versions in research/parallel/rounds/parallel-20260906-r2/ (docstrings = pre-registration): v334 R2 with tighter governors (engine gov hook),
v335 MANUAL daily decision cadence at 60-minute latency, v336 MANUAL breadth test (pooled member predicting 15 coins; 1m cubes for 10 alts; books
member_PTX_ext15 / PTXq cached), v337 options member added to the MANUAL / BOT mixes.
Write only under `research/parallel/rounds/parallel-20260906-r2/v334_v337_audit/` and `tests/test_v334_v337_audit.py`; relative paths without quoting;
do NOT open the four result JSONs or run logs before replication.json is saved.
Part A: replicate every row, fold choice, transfer flag and final row with your own wiring of the engine calls (for v336 rebuild ONE alt's 1m cube and
refit ONE anchor of PTX, compare with the cache; check that alt books are zero where the alt has no price); check feature timing, label / fit windows,
fill timing (win_start), and that no most-recent-year number enters any choice. Save replication.json FIRST. Part B: compare (monthly > 0.01 pp,
DD > 0.05 pp, F > 0.001, books > 1e-9 = mismatch, report all); COMPARISON.md with "## Verdict" PASS/FAIL per version. Do not edit leader files.
