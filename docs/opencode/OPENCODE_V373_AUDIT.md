# v373 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Version in research/parallel/rounds/parallel-20260906-r2/v373/ (docstring = pre-registration), kpack inputs (KPACK=artifacts/kaggle/kpack/pack347):
v373 = MANUAL M2 structure (ONE bracket dip limit at 3.0 sigma, touch stop 8 sigma, R2 agents' size / TP, book x0.75, pullback entry 0.75 sigma,
orders valid 3 bars) with three rows: M2 (reference), M2S (book SL 5 / TP 10 sigma_d), M2ST (M2S + loss_act "tighten"), judged with the goal-1
fitness v310.fitness (book win rate); dev folds k = 2, 3 choose on years [:k]; TRANSFER only if a non-reference row is chosen and beats M2 on the
unseen dev year in both folds; final = dev4 choice; most recent year computed once for the final. The run wires v347.run_genome (CB seed) with an
outer simulate wrapper that sets rungs=(3.0,) and m_sl / m_tp. Reference check: the M2 row must reproduce dev4 5.23 (backend/history_tm v340).
Process note to verify: the first run crashed after the folds at a report-only stop_slip row (run_first_crash.log); the row was made optional and the
script re-run - confirm the fold rows of both logs are identical.
Part A (blind, before opening v373_result.json / run.log): with your own wiring (you may import v347 / v310 / engine modules, not v373's main),
recompute the three rows' dev4 and per-year metrics, both fold choices, the transfer flag and the final (incl. its most recent year); save
replication.json FIRST; check that no most-recent-year number enters any choice and that rungs=(3.0,) maps rung index 0 to the R2 table's
3.0-sigma rung. Part B: compare with v373_result.json (monthly > 0.01 pp, DD > 0.05 pp, F > 0.001, win > 0.001 = mismatch, report all);
COMPARISON.md with "## Verdict" PASS/FAIL.
Write only under `research/parallel/rounds/parallel-20260906-r2/v373_audit/` and `tests/test_v373_audit.py`; relative paths without quoting.
Do not edit leader files.
