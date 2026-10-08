# OpenCode task ops_fmeval2 - extend scripts/fm_paper_eval.py to the new paper runners (C2, B7, B7xC2)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `scripts/fm_paper_eval.py` (extend, keep every existing CLI behaviour),
`tests/test_fm_paper_eval.py` (extend) and append <= 10 lines to `docs/BOT_RUNBOOK_VI.md`. artifacts/* READ-ONLY; never touch running processes.
## Task
Add --feed choices: chronos (runner paper_d17bfg2ch, feed artifacts/research/chronos_shadow/chronos_features_live.parquet, column k2_mult),
b7 (paper_d17bfg2b7, artifacts/research/cascade_shadow/b7_live.parquet), b7c2 (paper_d17bfg2b7c2, artifacts/research/cascade_shadow/b7c2_live.parquet),
all vs the twin paper_d17bfg2. Respect each runner's start time (common uptime only) and the leader_note restart markers in stdout.log
(2026-10-08 04:50 UTC restart on bot fix 83a466a: compare only after it). Add an --all flag printing one summary line per feed. Tests on
synthetic fixtures. Vietnamese runbook lines: how and when (weekly) to run it, what result would justify switching.
