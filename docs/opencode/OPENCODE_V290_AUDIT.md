# v290 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v290 screens six information sets as 20% satellites on CB (v285 D2): K Korean premium (v230), E DVOL (v156), F US macro (v157),
G Fear & Greed (v159), H CFTC COT (v160), Dc per-coin Coinbase premium (NEW data: data/raw/coinbase_alts_20260930 SOL-USD / XRP-USD 1h,
scripts/fetch_coinbase_alts.py). Write only under `research/parallel/rounds/parallel-20260906-r2/v290_audit/` and
`tests/test_v290_audit.py`. Use relative paths without quoting. Do NOT open v290/v290_result.json, v290/run.log or
`artifacts/research/engine_real/member_sat_*.parquet` until part A is saved (`replication.json`).
A (audit): read `v290/v290_satellite_screen.py` and the feature modules. LEAKAGE is the main risk - check every source's publication
timing explicitly against the bar close t + 4h: Korean premium (Upbit hourly + USD/KRW lagged), DVOL hourly availability, macro daily
closes (US market close vs the 4h bar), Fear & Greed (published 00:00 UTC, used from 01:00), COT (Tuesday data used from Saturday),
and the new per-coin Coinbase premium (Coinbase hour [t+3h, t+4h) close vs Binance spot 4h close; rolling stats causal; XRP listing gap
-> NaN, not forward-filled across the gap). Confirm the satellites never enter the vol models, label windows / fit windows / embargo of
both schedules (annual, v202 quarterly), fill timing (minute-5, trade-through). Rebuild at least three satellites independently (Dc
and two others) and all accepted ones, replicate CB_ref (5.864), every CB_X row, the acceptance rule (v286.dev_select over {CB_ref,
CB_X}, DD filter 2021-2024), and SAT; the most recent year only for SAT. B: compare with the result JSON (return > 1pp or DD > 0.5pp =
mismatch); COMPARISON.md with a "## Verdict" PASS/FAIL covering feature timing per source, label windows, fit windows and fill timing.
Do not edit leader files.
