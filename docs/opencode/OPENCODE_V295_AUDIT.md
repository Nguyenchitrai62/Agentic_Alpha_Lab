# v295 blind audit + S1 robustness (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v295 S1 is the FIRST learned trader decision that beats the rule pipeline CB (worst dev year 3.384 vs 3.005, DD 17.50 vs 18.39, most
recent year 5.326 vs 5.167). Audit it with extra care. Write only under `research/parallel/rounds/parallel-20260906-r2/v295_audit/`,
`research/diagnostics/s1_robustness/` and `tests/test_v295_audit.py`; relative paths without quoting. Do NOT open v295/v295_result.json,
v295/run.log before part A is saved (`replication.json`).
A (audit): read v295/v295_pooled_size_agent.py, v294 (universe, loader), v293 (replica, Asset, fills_of, state features) and the engine
hook `sleeve_fill_size` (applied before the risk-budget check, exits unchanged). Write your OWN replica of the dip rung outcome and of
the seven state features; LEAKAGE checks (explicit): every feature uses data up to minute f-1 (sp30, sigma_1m window, 24h high, BTC sp30),
sigma_4h / trend use opens up to the decision bar, the training set for anchor Y holds only fills that EXITED before Y - 7 days (incl.
mu_Y), the U2020 universe uses only 2020-12 volume (delisted symbols kept), alts are training-only. Replicate CB_ref (5.864), S1, S2
(agent up/down counts), selection (v286.dev_select, DD filter 2021-2024), replaces_cb, and the final score of S1. B: compare with the
JSON (return > 1pp or DD > 0.5pp = mismatch); COMPARISON.md with "## Verdict" PASS/FAIL (feature timing, label windows, fit windows,
fill timing, universe causality).
C (robustness, after B): research/diagnostics/s1_robustness/s1_robustness.py (template research/diagnostics/p1_robustness/) - CB vs S1,
same engine arguments, rows: base, cost stress, latency 15 / 30 / 60, band / cool / sleeve 0.16 / 0.20 / offset shifts, outage (backstop
only), bootstrap (P(>=5%/month), P(loss year), P(DD>20)), 2000-USDT placeability, AND executability rows for the size decision:
  decision_lag_5 / decision_lag_15: the agent's state is computed at minute f-1-5 / f-1-15 (a bot that amends resting order sizes a
  few minutes late); placement_time: the size of each rung is decided once when the ladder is placed (state at minute 15 of the bar,
  same models) - the human-followable form.
Write the json and a SUMMARY.md (<= 25 lines) with a plain verdict: is S1 at least as robust as CB, and does it keep its edge when the
size is decided late or at placement? Do not edit leader files.
