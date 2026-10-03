# v374-v375 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Two versions in research/parallel/rounds/parallel-20260906-r2/ (docstrings = pre-registration). Both evaluate on 4h grids shifted by s = 0..3 h:
the phase-shifted engine inputs come from research/diagnostics/phase_offset_dips/phase_offset_dips.py::prep_grid (v374) and
research/diagnostics/phase_offset_full/phase_offset_full.py::prep_idx / pipe_setup (v375). FIRST verify those builders: at s = 0 they must equal
engine_user.prepare (minute cube, sig4, o1, o2) - and for s > 0 check on 20 random (bar, symbol, minute) cells against the raw 1m klines that cube
row i minute m is the kline opening at idx[i] + 4h + m minutes, that opens are the first 1m open of each shifted bar, and that books on shifted grids are
the latest standard-grid book row r <= the shifted decision time (no look-ahead). Check that no date after 2025-09-23 is simulated or reported.
v374 = dip-only sleeve, 18 rule rows (rungs x TP x stop), rung_scale_fixed 1.0, 4-phase-mean fitness F, folds k = 2, 3, final dev4, pre-research
validation 2020-10-01 .. 2021-09-23 report only. Process note: the first run crashed at import (ROOT path) before any simulation
(run_first_crash.log) - confirm. Recompute every row's 4-phase mean (R, DD, F), both fold choices, transfer flag, final and the pre-period rows.
v375 = whole deployed pipelines M2 M3 M4 M5 / R2 G2 CS on the four phases (agents off), phase-mean metrics (R, DD, W, pooled book / all-trade win),
MANUAL v310 goal-1 fitness and BOT v306 fitness, folds k = 2, 3 per product, references M5 / R2. Recompute every row, fold, transfer flag and final.
Part A (blind, before opening v374_result.json / v375_result.json / run logs): save replication.json FIRST. Part B: compare (monthly > 0.01 pp,
DD > 0.05 pp, F > 0.001, win > 0.001 = mismatch, report all); COMPARISON.md with "## Verdict" PASS/FAIL per version.
These runs are long (v374: 144 dip-only simulations; v375: 28 pipeline simulations): you may parallelise (<= 4 processes, 16 GB RAM).
Write only under `research/parallel/rounds/parallel-20260906-r2/v374_v375_audit/` and `tests/test_v374_v375_audit.py`; relative paths without quoting.
Do not edit leader files.
