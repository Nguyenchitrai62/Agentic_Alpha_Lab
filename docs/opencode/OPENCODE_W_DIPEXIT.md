# OpenCode task oc_dipexit: dip-rung exit structures at the rung level
Read AGENTS.md, docs/opencode/OPENCODE_VF_COMMON.md and research/tournament/RULES.md. Write ONLY under the folder named below (+ tests/test_<folder>.py); no commits; no edits of leader files or other folders; market data up to 2026-09-24 00:00 UTC may be read (all years are research data; findings need prospective validation). Load 1m data one coin at a time in float32; RAM < 1.5 GB; one process. Write PLAN.md (hypothesis, exact definitions, decision rule) BEFORE computing outcomes; then scripts, results.json, REPORT.md with tables and a one-line verdict. Folder: research/tournament/oc_dipexit/.
Replica: research/parallel/rounds/parallel-20260906-r2/v293/v293_pooled_exit_agent.py (Asset, outcomes: rungs k sigma_4h below the 4h bar
open, fills from minute 16 on a strict trade-through, close5 stop 4 sigma, 8-sigma backstop, TP limit, exit at the next bar open; maker 0.0002 /
taker 0.00055). Majors only, rungs 2.5/3/3.5/4/5, standard grid, 2021-09-24..2026-09-23. Pre-register at most 4 alternative exits and compute
the exact net return of every rung under each: e.g. E1 split TP (half at 0.5 sigma, half at 1.5 sigma), E2 TP 1 sigma + time exit 120 min
after the fill, E3 trailing exit (after +0.5 sigma, stop moves to the fill level), E4 TP at the bar open (full reversion) capped at 2 sigma.
Report per year the mean, win rate, sum, worst day and max DD of the daily sum vs the deployed TP 1 sigma; decision: an exit is PROMISING if its
yearly sum >= the deployed one in >= 4 of 5 years and its worst day is not worse.
