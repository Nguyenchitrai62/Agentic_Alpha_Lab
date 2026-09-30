# v294 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v294 = the v293 dip take-profit agent trained on the majors + the causal alt universe U2020 (top-30 non-major USD-M perps by December-2020
quote volume, delisted included: data/raw/um_universe_20260930, data/raw/alts2020_intraday_20260930, data/raw/alts_intraday_20260926).
Write only under `research/parallel/rounds/parallel-20260906-r2/v294_audit/` and `tests/test_v294_audit.py`; relative paths without
quoting; do NOT open v294/v294_result.json or v294/run.log before `replication.json`.
A: check that the universe is computed only from 2020-12 data (volume_2020_12.csv from the archive's 1d monthly zips; later-delisted
symbols not dropped) and that no symbol was chosen with later information; reuse your v293 audit replica if available, otherwise write
one; confirm the state features use data up to minute f-1, training rows exited before anchor - 7 days, alts are training-only, the hook
changes only the majors' TP; replicate CB_ref (5.864), X2_11coins_ref, X3_wide, X4_wide_strict (agent stats), selection
(v286.dev_select, DD filter 2021-2024), replaces_cb, and the most recent year only for the selected row. B: compare with the JSON (return
> 1pp or DD > 0.5pp = mismatch); COMPARISON.md with "## Verdict" PASS/FAIL (feature timing, label windows, fit windows, fill timing,
universe causality). Do not edit leader files.
