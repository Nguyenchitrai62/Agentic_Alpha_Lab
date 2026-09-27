# v169 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v169_audit/` and `tests/test_v169_audit.py`.
Do NOT open v169/ until part A is saved (`replication.json`). Base: the audited engine_real (your own
`engine_real_audit/audit_engine.py` replication may be imported, or import `engine_real/engine_real.py` for
`v154_books`, `context`, constants). Books = cached v154 books, target 0.25, governor on, all realism on.
A: for every bar i with weights w (after budget and min notional), holding bar T = t_i + 4h. Binance 1m klines
(`data/raw/btc_intraday_20260924/klines_1m_20*.parquet` for BTCUSDT, `data/raw/majors_intraday_20260924/<SYM>_1m_20*.parquet`
otherwise), minute offsets 0..239 inside T (forward-fill missing minutes inside the bar). Base price o_j = the engine's
4h open of bar T (opens parquet shifted -1). R(m) = sum_j w_j (close_j(m)/o_j - 1).
S_i = rolling covariance (360 bars, min 120) of 4h open-to-open returns of the 5 assets, row at bar i. L = k sqrt(w'S w).
Stop: first m in 16..238 with R(m) <= -L -> gross = sum_j w_j (open_j(m+1)/o_j - 1), extra cost sum|w| * 0.001, no
funding for that bar, and the next bar starts from zero weights (re-entry pays normal execution). Otherwise the bar is
exactly engine_real. 1m DD: eq_min[i] = eq[i-1] * (1 + min(0, min over the used path R(0..exit m, or 0..239)) - exec);
DD = max over the live span of 1 - min(eq, eq_min)/running max(eq), both normalised to the first live bar.
Rows: no stop (must equal engine_real 3.708 / 18.87), k = 3, 2, 4: monthly, yearly, full-path DD, 1m DD, stop counts
per anchor year. Save `replication.json`.
B: compare with `v169/v169_result.json` (return > 1pp, DD > 0.5pp must be explained), review
`v169/v169_intrabar_stop.py` for look-ahead (threshold from data known at the decision, exit strictly after the trigger
minute), write COMPARISON.md with a verdict. Do not edit leader files.
