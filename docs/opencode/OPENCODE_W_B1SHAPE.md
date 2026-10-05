# OpenCode task oc_b1shape: rung-level screen of correlation-aware sizing shapes
Read AGENTS.md, docs/opencode/OPENCODE_VF_COMMON.md and research/tournament/RULES.md. Write ONLY under the folder named below (+ tests/test_<folder>.py); no commits; no edits of leader files or other folders; market data up to 2026-09-24 00:00 UTC may be read (all years are research data; findings need prospective validation). Load 1m data one coin at a time in float32; RAM < 1.5 GB; one process. Write PLAN.md (hypothesis, exact definitions, decision rule) BEFORE computing outcomes; then scripts, results.json, REPORT.md with tables and a one-line verdict. Folder: research/tournament/oc_b1shape/.
Context: the BOT shrinks each dip rung at its fill minute f by 1/(1+n), n = number of OTHER majors whose 1m close at minute f-1 is <= their own
4h bar open x (1 - 2.5 sigma_4h) (registry v399: max yearly DD 25 -> 14). Data: research/tournament/ext/fills_U_ext.parquet (majors rows: sym,
j, r, f, t_fill, y0.5/y1.0/y1.5, x1 = rung depth; T = t_fill - f minutes = bar open) and the majors' 1m files (data/raw/btc_intraday_20260924,
data/raw/majors_intraday_20260924). sigma_4h = std of 4h open-to-open returns over 360 bars (min 120), bar opens on the standard grid.
Task: compute n for every majors R2-rung fill (k in 2.5/3/3.5/4/5) exactly as defined; check: share of fills with n = 0..4 per year. Then
evaluate at equal exposure (sizes rescaled so their mean equals 1 per year) with research/tournament/ext/harness5.py-style yearly sums of
size * y1.0 and the worst-day sum and max drawdown of the cumulative daily sum: S0 flat size 1, S1 1/(1+n), plus at most 3 pre-registered
shapes (e.g. 1/(1+n)^2, 1/(1+n_w) with BTC counted twice, a 2.0-sigma detection threshold). Decision: report which shape has the best
worst-day and max-DD with yearly sums >= S1's in >= 4 of 5 years.
