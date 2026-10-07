# OpenCode task audit_vrpstraddle - BLIND replication of the weekly short-straddle sleeve (V2) and its G2 overlay
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/audit_vrpstraddle/` and
`tests/test_audit_vrpstraddle.py`.

## Blind protocol (mandatory order)
1. Read ONLY `research/tournament/oc_vrpstraddle/PLAN.md` (the frozen spec) - NOT vrp.py, run_vrp.py, REPORT.md, results.json, trades_*.parquet
   or tmp/ of that folder, and not research/tournament/oc_vrprobust/ (another worker builds on it right now).
2. Implement from the spec, independently: V2 (1-week unhedged short ATM straddle, BTC + ETH, sold Friday 08:05 UTC at 0.97 x latest known
   DVOL, SL / TP / settlement exactly as PLAN.md) standalone for the four dev years, and the G2 overlay at f = 0.25 (combo account
   A(t) = A(t-1) (1 + r_bot(t)) + dSleeve(t), r_bot from the stored 4-phase G2 hourly mix R2B1D17BFG2 in
   research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl; you may read research/tournament/oc_carrycompound/analyze_carrycompound.py
   for how to load G2 and the reset metric / full-path DD conventions; reproduce G2 5.41 / 16.91 / 16.82 first).
   Do NOT compute anything on the most recent year 2025-09-24 .. 2026-09-23 except the overlay's 5-year row if your code needs it for the
   full-path DD - report it but do not use it for anything.
3. SAVE part A = `replication.json` (per dev year: standalone V2 %/month, DD, trades, TP / SL / expiry counts; overlay f = 0.25 per year R /
   yearly DD; 5y overlay R / worst / maxDD / full-path DD) BEFORE opening anything else in oc_vrpstraddle.
4. Only then open oc_vrpstraddle's REPORT.md / results.json / code and compare. Mismatch thresholds: %/month > 0.10 pp, DD > 0.5 pp, trade
   counts > 2 per year. For every mismatch find the cause (spec ambiguity vs bug on either side); quote the exact lines.
5. Look-ahead and accounting checks, each with a test: DVOL candle as-of (close <= decision), S at 08:04, settlement window 07:30..07:59,
   SL check order and marks, TP check on 4h closes with TP-first, fees, the overlay compounding (premium cash is received at entry: is it
   counted as equity BEFORE the position is marked, i.e. could the combo DD be understated because the open short-option liability is not
   marked at the hourly points?), the boundary-week skip, and the post-hoc fix #3 in their REPORT (overlay M path) - is the final formula right?

## Deliverable
`COMPARISON.md`: part-A numbers vs theirs, mismatches with causes, the accounting verdict (especially whether the overlay's DD and return are
computed with the open straddle liability marked at every hourly point), and a final line PASS / FAIL / PASS-WITH-NOTES. Vietnamese 3-line
summary.
