# v324-v333 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Ten small versions in research/parallel/rounds/parallel-20260906-r2/ (read each docstring = pre-registration): v324 pooled efficiency-ratio
overlay, v325 R2 with 77-coin dip agents, v326 pooled GRU member (Kaggle output artifacts/kaggle/v326/out/v326_pd_preds.parquet; audit the local
scoring v326_score.py and the kernel's walk-forward masks by reading v326_pooled_gru_kaggle.py), v327 BOT sub-account ensemble, v328 R2 fill-time
agents, v329 pooled member with alt spot prefix, v330 R2 native backstop, v331 MANUAL break-even grid, v332 pooled short / big members, v333
consistent-gene selection from the v309 / v310 eval caches.
Write only under `research/parallel/rounds/parallel-20260906-r2/v324_v333_audit/` and `tests/test_v324_v333_audit.py`; relative paths without
quoting; do NOT open any vNNN_result.json or run log of these versions before replication.json is saved.
Part A: for every version replicate the reported rows that need no refit (engine rows from cached member books / tables, fold choices, transfer
flags, final rows); for v324 / v329 / v332 refit ONE anchor of ONE member and compare the books with the cache; for v325 rebuild the U77 table for
one anchor and one symbol; check explicitly in every version: features at bar close, label windows, fit windows (labels end before cutoff), no
most-recent-year number in any choice, fill timing as engine_user. Save replication.json FIRST. Part B: compare (monthly > 0.01 pp, DD > 0.05 pp,
F > 0.001, books > 1e-9 = mismatch, report all); COMPARISON.md with "## Verdict" PASS/FAIL per version. Do not edit leader files.
