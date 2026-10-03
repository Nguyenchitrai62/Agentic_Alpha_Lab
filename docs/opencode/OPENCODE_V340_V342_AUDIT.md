# v340-v342 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Three versions in research/parallel/rounds/parallel-20260906-r2/ (docstrings = pre-registration), all built on the audited v338 wiring
(see research/parallel/rounds/parallel-20260906-r2/v338_v339_audit/ for the replication of v338 / v339; reuse your understanding, not its numbers):
v340 risk allocation (book_mult 0.75 via the trade dict, dip size_mult 3.5 / 4.375), v341 risk level (engine target 0.25 / 0.28 / 0.31, cap 2),
v342 two-rung ladder (rungs (3.0,) vs (3.0, 4.0); per-rung agent tables at each rung's own U index; size_mult 4.375 / 2.9).
Exact computation: as v338 (MANUAL M2 run = v310.run_genome(encode(target 0.25, cap 2, n_valid 3)) with books (2A + 2PT + D)/5 and v315.with_entry(0.75);
dip rows call engine_user.simulate with sleeve=True, the version's rungs, sleeve_stop_mode "touch", m_sleeve_sl 8.0, sleeve_risk_budget 0.26,
the version's size_mult, align (1.5, 0.5), sleeve_start 16, sleeve_fill_size / sleeve_tp from v306._tables(fit "U", up_th 2.0, up_mult 1.5,
dn_th 0.0, dn_mult 0.5, tp_margin 0.001); v340 / v342 set trade["book_mult"] 0.75; v341 overrides the simulate target). Fitness = v310.fitness with
the all-trade win rate; folds k = 2, 3; final on dev4; most recent year once; stress row sleeve_start 31.
Write only under `research/parallel/rounds/parallel-20260906-r2/v340_v342_audit/` and `tests/test_v340_v342_audit.py`; relative paths without quoting;
do NOT open the three result JSONs or run logs before replication.json is saved.
Part A: replicate every row (dev4, per-year, F), fold choices, transfer flags, final rows and stress rows with your own wiring; check (1) book_mult
scales only the book position (the signal threshold keeps the unscaled target) and leaves dip sizes unchanged, (2) in v342 rung r uses the agent
table at its own depth, (3) the 4.0-sigma rung can only fill after the price passed 3.0 sigma in the same bar (same 1m path), (4) no most-recent-year
number enters any choice, (5) feature / label / fit timing of the agent tables (bar-open state, fills exited before anchor - 7 days).
Save replication.json FIRST. Part B: compare (monthly > 0.01 pp, DD > 0.05 pp, F > 0.001, win > 0.001 = mismatch, report all); COMPARISON.md with
"## Verdict" PASS/FAIL per version. Do not edit leader files.
