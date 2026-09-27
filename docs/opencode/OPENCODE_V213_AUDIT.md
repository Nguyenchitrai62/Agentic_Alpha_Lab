# v213 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v213_audit/` and `tests/test_v213_audit.py`. Use relative
paths without quoting. Do NOT open v213/ until part A is saved (`replication.json`). Base: your independent v212 replication (S3).
A: extend S3 with (E1) a FULL-exit slot order: at a decision while in a position and with no add issued, if the signal is not on
the position's side (|target| < 0.05 or opposite) send a limit to close 100% at open * (1 + side*off) (off = max(0.001, 0.25
sigma_4h)), valid 2 bars, minute-5 rule on the issuing bar, strict trade-through, maker; this check comes BEFORE the 50% reduce
rule. (E2) allow up to 3 successive 50% reduces. (E3) both. The full exit ends the position (SL/TP cancelled) and is logged as a
limit exit. Report ref_v205, v212_S3, E1..E3 (dev4, worst first-four monthly, gate DD, fills, stops, tps, adds, reduces, limit
exits). Robust selection over E1..E3; most recent year only for the selected row. Check causality. Save `replication.json`.
B: compare with `v213/v213_result.json` (return > 0.01pp/month, DD > 0.05pp, counts exact or explain). COMPARISON.md with
PASS/FAIL. Do not report the most recent year of non-selected rows. Do not edit leader files.
