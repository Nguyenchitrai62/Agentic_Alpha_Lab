# v415 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v415 runs R2B1D17BF (B1 dip size x 1/(1+n), dips x1.7, budget 0.26 x 1.7, bear-regime book longs x0.5; reference = v411 cache) on the
5-year 4-phase harness (see the version docstring = pre-registration). Rows R2B1D17BFS5 / S6 change ONLY the dip close-stop distance
(engine `m_sleeve_sl`) from 4 to 5 / 6 sigma; native backstop stays 8 sigma; the dip budget counts the close-stop distance (v388 convention).
Also check the disclosed process deviation (v415/process_note.txt: run before registration): confirm prereg_sha256.txt matches the
docstring hash of v415_stop_dist.py and that the script contains no result-dependent choice.
Part A (blind, before opening the v415 result JSON, run logs or pkls): reproduce R2B1D17BFS5 on phase 1 and R2B1D17BFS6 on phase 3 with your own
wiring (v411/v388 code paths); save replication.json. Part B: compare (final equity relative > 1e-6 = mismatch); recompute rows / folds /
finals / full-path DD from the pkls. COMPARISON.md with "## Verdict" and a line "v415: PASS" or "v415: FAIL".
At most 1 heavy process. Write only under `research/parallel/rounds/parallel-20260906-r2/v415_audit/` and `tests/test_v415_audit.py`.
