# v299 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v299 trains the v296 J1 dip agents (size + take-profit, pooled experience) on the WHOLE December-2020 perp market (77 coins: the five majors + the 72
non-major USDT perps listed >= 28 days in 2020-12, delisted ones included; `data/raw/um_universe_20260930/volume_2020_12.csv`,
`data/raw/alts2020_intraday_20260930`, `data/raw/alts_intraday_20260926`) with the current model size (K1) and a larger HGB (K2), and compares with J1
trained on the 35-coin pool. Write only under `research/parallel/rounds/parallel-20260906-r2/v299_audit/` and `tests/test_v299_audit.py`; relative paths
without quoting; do NOT open v299/v299_result.json or v299/run.log before `replication.json`.
A: reuse your v294 / v296 audit replicas; confirm the universe is the 72 + 5 coins computed from 2020-12 volume only (no later information), the
experience rows (pool35 37741, pool77 76453 fills) are built with the same replica, state features at minute f-1, training rows = fills that EXITED before
anchor - 7 days, alts training-only; replicate J1_ref (6.268), K1, K2 (dev4, worst dev year, dev DD, dev win rates), the selection rule (v286.dev_select
among K1 / K2, replaces_j1 against J1_ref) and the final score of the selected row only. B: compare with the JSON (return > 1pp or DD > 0.5pp = mismatch);
COMPARISON.md with "## Verdict" PASS/FAIL (feature timing, label windows, fit windows, fill timing, universe causality). Do not edit leader files.
