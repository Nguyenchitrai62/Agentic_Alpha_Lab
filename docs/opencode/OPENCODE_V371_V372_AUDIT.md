# v371-v372 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Two versions in research/parallel/rounds/parallel-20260906-r2/ (docstrings = pre-registration), kpack inputs (KPACK=artifacts/kaggle/kpack/pack347):
v371 = exhaustive 648-row BOT trader grid on R2 (book_mult, book SL/TP, tighten rule and distance, dip budget, dip close5 stop; v306 BOT fitness,
flat choice, folds k = 1, 2, 3) - do NOT rerun the grid: recompute the R2 row, the three fold choices, the final and 20 random rows from
eval_cache.jsonl with your own wiring and compare; v372 = CNN dip size agent: data builder v372_seq_data.py (check the bar-open timing of the
sequences: the previous closed bar only; the state at minute 0; the 7-day embargo on t_exit in v372_cnn_train.py; the cross-fit halves), the Kaggle
predictions artifacts/kaggle/v372/output/v372_cnn_preds.parquet (do not retrain on GPU; you may retrain ONE anchor / half on CPU for a shape and
order-of-magnitude check) and the evaluation v372_cnn_agent_eval.py (replicate every row, fold choice, transfer flag and final).
Part A (blind, before opening result JSONs / run logs): save replication.json FIRST; check that no most-recent-year number enters any choice. Part B:
compare (monthly > 0.01 pp, DD > 0.05 pp, F > 0.001, win > 0.001 = mismatch, report all); COMPARISON.md with "## Verdict" PASS/FAIL per version.
Write only under `research/parallel/rounds/parallel-20260906-r2/v371_v372_audit/` and `tests/test_v371_v372_audit.py`; relative paths without quoting.
Do not edit leader files.
