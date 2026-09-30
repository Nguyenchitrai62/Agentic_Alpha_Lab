# v286 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v286 upgrades the Coinbase-premium member D of CB (v285 D2 = 0.8 x C4 books + 0.2 x (D + Dq)/2) with the audited TradingView
indicators (E1: D_tv / Dq_tv) and additionally the order-level whale flow (E2: D_tvo / Dq_tvo).
Write only under `research/parallel/rounds/parallel-20260906-r2/v286_audit/` and `tests/test_v286_audit.py`. Use relative paths without
quoting. Do NOT open v286/v286_result.json, v286/run.log or the new member caches (`artifacts/research/engine_real/member_D*_tv*.parquet`)
until part A is saved (`replication.json`).
A (audit): read `v286/v286_coinbase_member_upgrade.py`, `v154/v154_ensemble_coinbase.py` (books_coinbase), `v206/*.py`
(member_d_quarterly), `v202` (quarterly wrapper), `v111` (Coinbase premium features), `v231/tv_indicators.py`, `v236/flow_features.py`
and `v240` (order-level archive). Rebuild the four members INDEPENDENTLY into your own folder (do not reuse the cached member_D*_tv*
files) and replicate CB_ref (must be dev4 5.864), E1 and E2 with the same engine arguments (C4 rules: close5, backstop 8,
m_sleeve_sl 4, budget 0.18, v221.KW, G2 grid policy, win_start 5). Check LEAKAGE explicitly: feature timing of all three feature groups
(Coinbase premium on t, TV and flow on (t, sym): only data available at the close of bar t), that the new features are excluded from the
vol models, label windows and fit windows of both schedules (annual anchors, v202 quarterly; embargo >= horizon), fill timing (minute-5
rule, trade-through). Selection: dev_select = v204 robust criterion with the drawdown filter = max yearly dd_1m of 2021-2024 (not the
full path); among E1 / E2 only; `replaces_cb` = dev_select over {CB_ref, selected}. Most recent year only for the selected row.
B: compare with the result JSON (return > 1pp or DD > 0.5pp = mismatch); COMPARISON.md with a "## Verdict" PASS/FAIL covering feature
timing, label windows, fit windows and fill timing. Do not edit leader files.
