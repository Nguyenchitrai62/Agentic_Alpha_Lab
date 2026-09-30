# v293 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v293 learns the take-profit multiple (0.5 / 1.0 / 1.5 sigma_4h) of every filled dip rung on CB from exact counterfactuals, with training
data from the five majors (X1) or from 11 coins (X2: + ADA, AVAX, DOGE, LINK, LTC, TRX 1m history in data/raw/alts_intraday_20260926),
trading the majors only. Write only under `research/parallel/rounds/parallel-20260906-r2/v293_audit/` and `tests/test_v293_audit.py`;
relative paths without quoting; do NOT open v293/v293_result.json or v293/run.log before `replication.json`.
A: write your OWN dip-rung replica from the engine_user code (rungs 2.5/3/3.5/4 sigma_4h below the holding-bar open, trade-through from
minute 16 to 238, close5 stop at 4 sigma, 8-sigma backstop first on ties, TP limit maker, stop exit at the next minute open, timeout at the
next 4h open with adverse funding at settlements) and compare with v293's replica and with the engine (float32 cube tolerance as the
docstring). LEAKAGE checks (explicit): every state feature uses data up to minute f-1 only (sp30, sigma_1m window, 24h high, BTC sp30),
sigma_4h and trend use opens up to the decision bar, training rows are fills that EXITED before anchor - 7 days, alts are training data only
(never traded), the hook changes only the TP of majors' rungs. Replicate CB_ref (5.864), X1, X2 (agent stats included), selection
(v286.dev_select, DD filter 2021-2024) and replaces_cb; most recent year only for the selected row. B: compare with the JSON (return >
1pp or DD > 0.5pp = mismatch); COMPARISON.md with "## Verdict" PASS/FAIL (feature timing, label windows, fit windows, fill timing).
Do not edit leader files.
