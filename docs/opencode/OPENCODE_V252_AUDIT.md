# v252 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v252_audit/` and `tests/test_v252_audit.py`. Use relative paths without
quoting. Do NOT open v252/v252_result.json or its logs until part A is saved (`replication.json`); read `v252/intrabar_flow.py`,
`v252/v252_intrabar_flow.py` and `v240/v240_order_level_flow.py`.
A: (1) Data: the 4h tier table `data/raw/aggflow_20260929_orders/{SYM}_flow_4h.parquet` must equal the audited O1 table
`data/raw/aggflow_20260928_orders/{SYM}_flow_4h.parquet`; the per-bar totals of the 1m store `data/raw/aggflow_20260929_orders_1m/{SYM}/`
must equal the 4h table totals (float32 tolerance). (2) Features: re-implement the four fi_* features independently from the 1m store and
the 1m klines (bar t = minutes t .. t+239; last hour = minutes 180..239; >= 100k bins = 100k_300k, 300k_1m, 1m_3m, ge3m; absorption uses
the sign of the minute close-to-close return; burst = max one-minute notional of the >= 300k bins over the bar's mean one-minute total,
log1p, z-score 540 bars min 270) and check truncation (features at t unchanged when data after t + 4h is removed). (3) Members: the cached
members `member_{A,Aq}_{I1_intrabar_all,I2_intrabar_core}.parquet` in the engine_real cache must be replayable; rebuild at least one
anchor of member A for I2 and compare. (4) Run the reference (O1 members at sleeve budget 0.18, must give dev4 5.777) and I1 / I2; report
dev4, worst first-four monthly, gate DD; robust selection; most recent year only for the selected row. Save `replication.json`. B: compare
with the result JSON (return > 0.01pp/month, DD > 0.05pp). COMPARISON.md with a "## Verdict" PASS/FAIL, explicitly checking feature timing,
label windows, fit windows and fill timing. Do not edit leader files.
