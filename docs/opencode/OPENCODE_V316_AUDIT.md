# v316 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v316 = controlled A/B of the book signal model: v94 horizon ensemble (y18 / y42 / y84) on v92 features + BTC cross features, trained on the 5 majors
only (CTRL) or on the majors + the 72 U2020 alts (POOL), predictions for the majors. Script and docstring: research/parallel/rounds/parallel-20260906-r2/
v316/v316_pooled_universe_book_member.py. Alt 4h bars are cached in artifacts/research/engine_real/v316_alt4h/ (rebuild a few yourself from the 1m
klines to verify the resampling: open first / high max / low min / close last / volumes summed, bars with < 200 minutes dropped).
Write only under `research/parallel/rounds/parallel-20260906-r2/v316_audit/` and `tests/test_v316_audit.py`; relative paths without quoting;
do NOT open v316/v316_result.json or v316/run*.log before replication.json is saved.
Part A: independently rebuild the panel (majors from the v113 extended loader as the script does, alts from the cache + your own spot-check), the
targets, the per-anchor training windows (cutoff = anchor - (84 + 60) bars, labels ending before the cutoff), the CTRL and POOL fits (HGB
max_depth 4, lr 0.03, 400 iterations, min_samples_leaf 300, l2 1.0, random_state 0), the per-year Spearman IC (majors, pred vs y42) for the four
dev anchors, and the MANUAL blend rows (books = 0.8 x (2A + 2B + D)/5 + 0.2 x member, G2 manual rules, sleeve off; v310 robust fitness on dev4).
CHECK LEAKAGE explicitly: feature timing (features use bars up to the bar's close; daily bars known at the 4h close; funding as v92), label windows,
fit windows (no alt row with a label ending after the cutoff), the alt universe is fixed from Dec-2020 volumes (no future listing information).
Save replication.json FIRST. Part B: compare (IC > 0.01, monthly > 0.05 pp, DD > 0.1 pp = mismatch); COMPARISON.md with "## Verdict" PASS/FAIL.
Do not edit leader files.
