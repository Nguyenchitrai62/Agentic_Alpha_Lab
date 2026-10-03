# v338-v339 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Two versions in research/parallel/rounds/parallel-20260906-r2/ (docstrings = pre-registration): v338 MANUAL book M2 + ONE human-placeable dip
limit per coin (rows M2 / MD30 / MD35), v339 intensity of that single dip (rows MD30 / MD25 / MD30x2).
Exact computation (as the code does it): MANUAL M2 run = v310.run_genome(encode(target 0.25, cap 2, n_valid 3)) with books (2A + 2PT + D)/5 and
v315.with_entry(0.75); the dip rows call engine_user.simulate with sleeve=True, rungs=(k,), sleeve_stop_mode "touch", m_sleeve_sl 8.0,
sleeve_risk_budget 0.26 (sleeve_budget_sl None -> the 8-sigma stop is counted), size_mult 1.75 (3.5 for MD30x2), align (1.5, 0.5), sleeve_start 16,
sleeve_fill_size / sleeve_tp read from v306._tables(fit "U", up_th 2.0, up_mult 1.5, dn_th 0.0, dn_mult 0.5, tp_margin 0.001) at the U index of
k (U = 2.0 .. 5.0 step 0.5). Dip-rung trades (v306._trade_rows kind "rung") are counted per anchor year; fitness = v310.fitness with the book win
rate replaced by the all-trade win rate (book + rung counts summed). Folds k = 2, 3 choose on years [:k]; final on dev4; most recent year once;
stress row sleeve_start 31 for the final.
Write only under `research/parallel/rounds/parallel-20260906-r2/v338_v339_audit/` and `tests/test_v338_v339_audit.py`; relative paths without quoting;
do NOT open the two result JSONs or run logs before replication.json is saved.
Part A: replicate every row (dev4 metrics, per-year metrics, F), fold choices, transfer flags, the final rows and the stress row with your own wiring of
the engine calls; check (1) the dip agents' size / TP tables are bar-OPEN predictions (state at minute 0, agents fitted only on fills exited before
anchor - 7 days; read v306_gene_tables.py), (2) a dip rung cannot fill before minute 16 and the touch stop is at fill level x (1 - 8 sigma),
(3) a rung open at the bar end exits at the next 4h open with taker fee, (4) no most-recent-year number enters any choice. Save replication.json FIRST.
Part B: compare (monthly > 0.01 pp, DD > 0.05 pp, F > 0.001, win > 0.001 = mismatch, report all); COMPARISON.md with "## Verdict" PASS/FAIL per
version. Do not edit leader files.
